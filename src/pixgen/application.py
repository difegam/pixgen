"""Coordinate image generation across providers."""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pixgen.artifacts import OutputPlan, plan_output, write_atomic
from pixgen.core.errors import ErrorCode, PixgenError, ProviderError
from pixgen.core.models import MediaRole, ModelId
from pixgen.core.params import parse_params
from pixgen.core.requests import (
    ImageCreateIntent,
    ImageIntent,
    ValidatedImageRequest,
)
from pixgen.core.results import CommandResult, PublicError, TargetResult
from pixgen.images.inspect import load_image
from pixgen.images.models import ImageInputError, LocalImage
from pixgen.providers.base import ImageProvider, PreparedImageRequest, PreparedMedia

if TYPE_CHECKING:
    from pathlib import Path

    from pixgen.config.models import Settings
    from pixgen.providers.registry import ProviderRegistry

__all__: list[str] = [
    "ImageApplication",
    "RunOutcome",
]


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """Result of an image generation run."""

    result: CommandResult
    exit_code: int


class ImageApplication:
    """Coordinate image generation across providers."""

    def __init__(self, registry: ProviderRegistry, settings: Settings) -> None:
        self._registry = registry
        self._settings = settings

    async def run(
        self,
        intent: ImageIntent,
        *,
        models: list[str] | None = None,
        variants: int = 1,
        output: Path | None = None,
        output_dir: Path | None = None,
        mkdir: bool = False,
        force: bool = False,
        timeout_seconds: int | None = None,
        raw_params: list[str] | None = None,
    ) -> RunOutcome:
        """Run an image generation command."""
        run_id = secrets.token_hex(2)

        try:
            return await self._run_impl(
                intent,
                models=models,
                variants=variants,
                output=output,
                output_dir=output_dir,
                mkdir=mkdir,
                force=force,
                timeout_seconds=timeout_seconds,
                raw_params=raw_params,
                run_id=run_id,
            )
        except PixgenError as exc:
            result = CommandResult(
                run_id=run_id,
                error=PublicError(code=ErrorCode.INVALID_REQUEST, message=str(exc)),
            )
            return RunOutcome(result, 2)

    async def _run_impl(  # noqa: C901
        self,
        intent: ImageIntent,
        *,
        models: list[str] | None,
        variants: int,
        output: Path | None,
        output_dir: Path | None,
        mkdir: bool,
        force: bool,
        timeout_seconds: int | None,
        raw_params: list[str] | None,
        run_id: str,
    ) -> RunOutcome:
        model_ids = self._resolve_models(intent, models)
        selected_set: set[str] = set(model_ids)

        if variants < 1:
            raise PixgenError(ErrorCode.INVALID_REQUEST, "variants must be at least 1")
        if variants > self._settings.generation.max_variants:
            max_v = self._settings.generation.max_variants
            raise PixgenError(
                ErrorCode.INVALID_REQUEST,
                f"variants ({variants}) exceeds max_variants ({max_v})",
            )

        total_jobs = len(model_ids) * variants
        if total_jobs > self._settings.generation.max_jobs:
            max_j = self._settings.generation.max_jobs
            raise PixgenError(
                ErrorCode.INVALID_REQUEST,
                f"total jobs ({total_jobs}) exceeds max_jobs ({max_j})",
            )

        parsed_params = parse_params(raw_params or [], selected_set)

        providers = {mid: self._registry.provider_for(mid) for mid in model_ids}
        for mid, provider in providers.items():
            if not provider.available:
                raise PixgenError(
                    ErrorCode.CREDENTIAL_UNAVAILABLE,
                    f"credentials not configured for {mid}",
                )

        models_specs = {mid: self._registry.get_model(mid) for mid in model_ids}

        validated_requests = {}
        for mid in model_ids:
            spec = models_specs[mid]
            provider = providers[mid]
            scoped = parsed_params.get(mid, {})
            unscoped = parsed_params.get(None, {})
            merged_params = {**unscoped, **scoped}
            intent_with_params = intent.model_copy(update={"params": merged_params})
            validated_requests[mid] = provider.validate(intent=intent_with_params, model=spec)

        declared_media_types = {
            mid: providers[mid].declared_media_type(req) for mid, req in validated_requests.items()
        }

        plans, run_id = plan_output(
            model_ids=model_ids,
            variants=variants,
            output=output,
            output_dir=output_dir,
            settings_output_dir=self._settings.generation.output_dir,
            mkdir=mkdir,
            force=force,
            run_id=run_id,
            declared_media_types=declared_media_types,
        )

        input_paths = self._collect_input_paths(intent)
        loaded_images = {}
        for path in input_paths:
            try:
                loaded_images[path] = load_image(path)
            except ImageInputError as exc:
                raise PixgenError(ErrorCode.INVALID_REQUEST, str(exc)) from exc

        for mid in model_ids:
            spec = models_specs[mid]
            req = validated_requests[mid]
            self._validate_media_counts(req, spec, loaded_images)

        results = await self._execute_jobs(
            plans,
            validated_requests,
            providers,
            loaded_images,
            intent,
            timeout_seconds,
        )

        any_success = any(r.artifact_path is not None for r in results)
        any_failure = any(r.error is not None for r in results)

        command_result = CommandResult(run_id=run_id, results=tuple(results))

        if (not any_success and not any_failure) or (any_success and not any_failure):
            exit_code = 0
        elif not any_success and any_failure:
            exit_code = 3
        else:
            exit_code = 4

        return RunOutcome(command_result, exit_code)

    def _resolve_models(
        self,
        intent: ImageIntent,
        explicit: list[str] | None,
    ) -> list[str]:
        if explicit:
            return explicit
        if isinstance(intent, ImageCreateIntent):
            return list(self._settings.defaults.image_create_models)
        return list(self._settings.defaults.image_edit_models)

    def _collect_input_paths(self, intent: ImageIntent) -> list[Path]:
        if isinstance(intent, ImageCreateIntent):
            return list(intent.references)
        return list(intent.images)

    def _validate_media_counts(
        self,
        request: ValidatedImageRequest,
        spec,
        loaded_images: dict[Path, LocalImage],
    ) -> None:
        intent = request.intent
        if isinstance(intent, ImageCreateIntent):
            role = MediaRole.REFERENCE
            paths = intent.references
        else:
            role = MediaRole.IMAGE
            paths = intent.images

        if role not in spec.media:
            if len(paths) > 0:
                raise PixgenError(
                    ErrorCode.INVALID_REQUEST,
                    f"model {spec.id} does not accept {role.value} inputs",
                )
            return

        role_spec = spec.media[role]
        count = len(paths)

        if count < role_spec.minimum:
            raise PixgenError(
                ErrorCode.INVALID_REQUEST,
                f"model {spec.id} requires at least {role_spec.minimum} {role.value} inputs",
            )
        if count > role_spec.maximum:
            raise PixgenError(
                ErrorCode.INVALID_REQUEST,
                f"model {spec.id} accepts at most {role_spec.maximum} {role.value} inputs",
            )

        for path in paths:
            img = loaded_images[path]
            fmt = img.media_type.split("/")[-1]
            if fmt == "jpeg":
                fmt = "jpg"
            if fmt not in role_spec.formats and img.media_type not in [
                f"image/{f}" for f in role_spec.formats
            ]:
                raise PixgenError(
                    ErrorCode.INVALID_REQUEST,
                    f"model {spec.id} does not accept format {fmt!r} for {role.value}",
                )
            if role_spec.max_bytes and img.byte_size > role_spec.max_bytes:
                raise PixgenError(
                    ErrorCode.INVALID_REQUEST,
                    f"file {path} exceeds max_bytes ({role_spec.max_bytes}) for {spec.id}",
                )

    async def _execute_jobs(
        self,
        plans: list[OutputPlan],
        validated_requests: dict[ModelId, ValidatedImageRequest],
        providers: dict[ModelId, ImageProvider],
        loaded_images: dict[Path, LocalImage],
        intent: ImageIntent,
        timeout_seconds: int | None,
    ) -> list[TargetResult]:
        semaphore = asyncio.Semaphore(self._settings.generation.max_parallel_requests)
        request_timeout = self._settings.generation.request_timeout_seconds
        run_timeout = timeout_seconds or self._settings.generation.run_timeout_seconds

        results: list[TargetResult] = []
        tasks: list[asyncio.Task[TargetResult]] = []

        for plan in plans:
            task = asyncio.create_task(
                self._run_job(
                    plan,
                    validated_requests[plan.model_id],
                    providers[plan.model_id],
                    loaded_images,
                    intent,
                    semaphore,
                    request_timeout,
                    run_timeout,
                )
            )
            tasks.append(task)

        for task in tasks:
            result = await task
            results.append(result)

        return results

    async def _run_job(
        self,
        plan: OutputPlan,
        validated_request: ValidatedImageRequest,
        provider: ImageProvider,
        loaded_images: dict[Path, LocalImage],
        intent: ImageIntent,
        semaphore: asyncio.Semaphore,
        request_timeout: int,
        run_timeout: int | None,
    ) -> TargetResult:
        async with semaphore:
            try:
                input_paths = self._collect_input_paths(intent)
                media = tuple(
                    PreparedMedia(
                        role=MediaRole.REFERENCE
                        if isinstance(intent, ImageCreateIntent)
                        else MediaRole.IMAGE,
                        image=loaded_images[path],
                    )
                    for path in input_paths
                )
                prepared = PreparedImageRequest(request=validated_request, media=media)

                timeout_val = request_timeout
                if run_timeout:
                    timeout_val = min(request_timeout, run_timeout)

                image = await asyncio.wait_for(
                    provider.generate(prepared),
                    timeout=timeout_val,
                )

                write_atomic(plan.path, image.data)

                warnings = []
                if plan.path.suffix:
                    ext = plan.path.suffix.lstrip(".")
                    expected_ext = image.media_type.split("/")[-1]
                    if expected_ext == "jpeg":
                        expected_ext = "jpg"
                    if ext not in (expected_ext, ""):
                        warnings.append(
                            f"file extension .{ext} does not match media type {image.media_type}"
                        )

                return TargetResult(
                    model=plan.model_id,
                    variant=plan.variant,
                    artifact_path=plan.path,
                    media_type=image.media_type,
                    warnings=tuple(warnings),
                )
            except TimeoutError:
                return TargetResult(
                    model=plan.model_id,
                    variant=plan.variant,
                    error=PublicError(code=ErrorCode.TIMEOUT, message="request timed out"),
                )
            except ProviderError as exc:
                return TargetResult(
                    model=plan.model_id,
                    variant=plan.variant,
                    error=PublicError(code=exc.code, message=exc.message),
                )
            except Exception as exc:  # noqa: BLE001
                return TargetResult(
                    model=plan.model_id,
                    variant=plan.variant,
                    error=PublicError(
                        code=ErrorCode.PROVIDER_FAILURE,
                        message=f"unexpected error: {exc}",
                    ),
                )

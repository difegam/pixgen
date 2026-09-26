import asyncio
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pixgen.artifacts import OutputPlan, plan_output, write_atomic
from pixgen.core.errors import ErrorCode, PixgenError, ProviderError
from pixgen.core.params import parse_params
from pixgen.core.requests import ImageCreateIntent, ImageIntent, ValidatedImageRequest
from pixgen.core.results import CommandResult, PublicError, TargetResult
from pixgen.images.inspect import load_image
from pixgen.images.mime import MIME_TO_EXTENSION
from pixgen.images.models import ImageInputError, LocalImage
from pixgen.providers.base import ImageProvider, PreparedImageRequest, PreparedMedia, ProviderImage

if TYPE_CHECKING:
    from pathlib import Path

    from pixgen.config.models import Settings
    from pixgen.core.models import ModelId
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
            model_ids = self._resolve_models(intent, models)
            self._check_provider_availability(model_ids)
            self._validate_variant_limits(len(model_ids), variants)
            images = _load_images(intent.input_paths)
            prepared, providers = self._prepare(intent, model_ids, raw_params, images)
            plans = plan_output(
                model_ids=model_ids,
                variants=variants,
                output=output,
                output_dir=output_dir,
                settings_output_dir=self._settings.generation.output_dir,
                mkdir=mkdir,
                force=force,
                run_id=run_id,
                declared_media_types={
                    mid: providers[mid].declared_media_type(req.request)
                    for mid, req in prepared.items()
                },
            )
        except PixgenError as exc:
            result = CommandResult(
                run_id=run_id,
                error=PublicError(code=exc.code, message=exc.message),
            )
            return RunOutcome(result, 2)

        results = await self._execute_jobs(plans, prepared, providers, timeout_seconds)
        failures = sum(r.error is not None for r in results)
        if failures == 0:
            exit_code = 0
        elif failures == len(results):
            exit_code = 3
        else:
            exit_code = 4
        return RunOutcome(CommandResult(run_id=run_id, results=tuple(results)), exit_code)

    def _resolve_models(self, intent: ImageIntent, explicit: list[str] | None) -> list[str]:
        if explicit:
            return explicit
        if isinstance(intent, ImageCreateIntent):
            return list(self._settings.defaults.image_create_models)
        return list(self._settings.defaults.image_edit_models)

    def _check_provider_availability(self, model_ids: list[str]) -> None:
        for mid in model_ids:
            provider = self._registry.provider_for(mid)
            if not provider.available:
                raise PixgenError(
                    ErrorCode.CREDENTIAL_UNAVAILABLE,
                    f"credentials not configured for {mid}",
                )

    def _validate_variant_limits(self, model_count: int, variants: int) -> None:
        generation = self._settings.generation
        if variants < 1:
            raise PixgenError(ErrorCode.INVALID_REQUEST, "variants must be at least 1")
        if variants > generation.max_variants:
            raise PixgenError(
                ErrorCode.INVALID_REQUEST,
                f"variants ({variants}) exceeds max_variants ({generation.max_variants})",
            )
        total_jobs = model_count * variants
        if total_jobs > generation.max_jobs:
            raise PixgenError(
                ErrorCode.INVALID_REQUEST,
                f"total jobs ({total_jobs}) exceeds max_jobs ({generation.max_jobs})",
            )

    def _prepare(
        self,
        intent: ImageIntent,
        model_ids: list[str],
        raw_params: list[str] | None,
        images: tuple[LocalImage, ...],
    ) -> tuple[dict[ModelId, PreparedImageRequest], dict[ModelId, ImageProvider]]:
        parsed_params = parse_params(raw_params or [], set(model_ids))
        unscoped = parsed_params.get(None, {})
        media = tuple(PreparedMedia(role=intent.media_role, image=img) for img in images)

        providers = {mid: self._registry.provider_for(mid) for mid in model_ids}

        prepared: dict[ModelId, PreparedImageRequest] = {}
        for mid, provider in providers.items():
            params = {**unscoped, **parsed_params.get(mid, {})}
            request = provider.validate(
                intent=intent.model_copy(update={"params": params}),
                model=self._registry.get_model(mid),
            )
            _validate_media(request, images)
            prepared[mid] = PreparedImageRequest(request=request, media=media)
        return prepared, providers

    async def _execute_jobs(
        self,
        plans: list[OutputPlan],
        prepared: dict[ModelId, PreparedImageRequest],
        providers: dict[ModelId, ImageProvider],
        timeout_seconds: int | None,
    ) -> list[TargetResult]:
        generation = self._settings.generation
        semaphore = asyncio.Semaphore(generation.max_parallel_requests)
        request_timeout = generation.request_timeout_seconds
        run_timeout = (
            timeout_seconds if timeout_seconds is not None else generation.run_timeout_seconds
        )
        tasks: list[asyncio.Task[TargetResult]] = []
        try:
            async with asyncio.timeout(run_timeout):
                async with asyncio.TaskGroup() as group:
                    tasks = [
                        group.create_task(
                            _run_job(
                                plan,
                                prepared[plan.model_id],
                                providers[plan.model_id],
                                semaphore,
                                request_timeout,
                            )
                        )
                        for plan in plans
                    ]
        except TimeoutError:
            pass

        results: list[TargetResult] = []
        for plan, task in zip(plans, tasks, strict=True):
            if not task.cancelled():
                results.append(task.result())
            else:
                results.append(
                    TargetResult(
                        model=plan.model_id,
                        variant=plan.variant,
                        error=PublicError(
                            code=ErrorCode.TIMEOUT,
                            message="run deadline exceeded",
                        ),
                    )
                )
        return results


def _load_images(paths: tuple[Path, ...]) -> tuple[LocalImage, ...]:
    try:
        return tuple(load_image(path) for path in paths)
    except ImageInputError as exc:
        raise PixgenError(ErrorCode.INVALID_REQUEST, str(exc)) from exc


def _validate_media(request: ValidatedImageRequest, images: tuple[LocalImage, ...]) -> None:
    spec = request.model
    role = request.intent.media_role
    role_spec = spec.media.get(role)
    if role_spec is None:
        if images:
            raise PixgenError(
                ErrorCode.INVALID_REQUEST,
                f"model {spec.id} does not accept {role.value} inputs",
            )
        return

    if len(images) < role_spec.minimum:
        raise PixgenError(
            ErrorCode.INVALID_REQUEST,
            f"model {spec.id} requires at least {role_spec.minimum} {role.value} inputs",
        )
    if len(images) > role_spec.maximum:
        raise PixgenError(
            ErrorCode.INVALID_REQUEST,
            f"model {spec.id} accepts at most {role_spec.maximum} {role.value} inputs",
        )

    accepted = {f"image/{fmt}" for fmt in role_spec.formats}
    for img in images:
        if img.media_type not in accepted:
            raise PixgenError(
                ErrorCode.INVALID_REQUEST,
                f"model {spec.id} does not accept {img.media_type} for {role.value}",
            )
        if role_spec.max_bytes and img.byte_size > role_spec.max_bytes:
            raise PixgenError(
                ErrorCode.INVALID_REQUEST,
                f"file {img.source_path} exceeds max_bytes ({role_spec.max_bytes}) for {spec.id}",
            )


async def _run_job(
    plan: OutputPlan,
    prepared: PreparedImageRequest,
    provider: ImageProvider,
    semaphore: asyncio.Semaphore,
    request_timeout: int,
) -> TargetResult:
    async with semaphore:
        try:
            async with asyncio.timeout(request_timeout):
                image = await provider.generate(prepared)
            actual_path = _save_image_with_correct_format(plan, image)
        except TimeoutError:
            error = PublicError(code=ErrorCode.TIMEOUT, message="request timed out")
        except ProviderError as exc:
            error = PublicError(code=exc.code, message=exc.message)
        except Exception as exc:  # noqa: BLE001
            error = PublicError(
                code=ErrorCode.PROVIDER_FAILURE,
                message=f"unexpected error: {exc}",
            )
        else:
            return TargetResult(
                model=plan.model_id,
                variant=plan.variant,
                artifact_path=actual_path,
                media_type=image.media_type,
                warnings=(),
            )
    return TargetResult(model=plan.model_id, variant=plan.variant, error=error)


def _save_image_with_correct_format(plan: OutputPlan, image: ProviderImage) -> Path:
    ext = MIME_TO_EXTENSION.get(image.media_type, image.media_type.rsplit("/", maxsplit=1)[-1])
    if plan.path.suffix.lstrip(".") == ext:
        write_atomic(plan.path, image.data)
        return plan.path
    correct_path = plan.path.with_suffix(f".{ext}")
    write_atomic(correct_path, image.data)
    return correct_path

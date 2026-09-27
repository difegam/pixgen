import asyncio
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import ValidationError

from pixgen.artifacts import OutputPlan, plan_output, save_artifact
from pixgen.core.errors import ErrorCode, PixgenError, ProviderError, validation_message
from pixgen.core.parameters import ProviderParams, SharedImageParams
from pixgen.core.requests import (
    ImageCreateIntent,
    ImageIntent,
    NativeSelection,
    ParameterSelection,
    SharedSelection,
    ValidatedImageRequest,
)
from pixgen.core.results import CommandResult, PublicError, TargetResult
from pixgen.images.inspect import load_image
from pixgen.images.models import ImageInputError, LocalImage
from pixgen.providers.base import ImageProvider, PreparedImageRequest, PreparedMedia

if TYPE_CHECKING:
    from pathlib import Path

    from pixgen.config.models import Settings
    from pixgen.core.models import ImageOperation, JsonObject, ModelId
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
        selection: ParameterSelection | None = None,
        variants: int = 1,
        output: Path | None = None,
        output_dir: Path | None = None,
        mkdir: bool = False,
        force: bool = False,
        timeout_seconds: int | None = None,
    ) -> RunOutcome:
        """Run an image generation command."""
        run_id = uuid.uuid7()
        try:
            native_parameters = None
            shared_parameters = SharedImageParams()
            if isinstance(selection, SharedSelection):
                models = list(selection.models) if selection.models is not None else None
                shared_parameters = selection.parameters
            elif isinstance(selection, NativeSelection):
                models = [selection.model]
                native_parameters = selection.parameters
            else:
                models = None
            model_ids = self._resolve_models(intent, models)
            if not model_ids:
                raise PixgenError(ErrorCode.INVALID_REQUEST, "at least one model must be selected")
            if len(model_ids) != len(set(model_ids)):
                raise PixgenError(ErrorCode.INVALID_REQUEST, "model selections must be unique")
            if timeout_seconds is not None and timeout_seconds < 1:
                raise PixgenError(ErrorCode.INVALID_REQUEST, "timeout_seconds must be at least 1")
            self._check_provider_availability(model_ids)
            self._validate_variant_limits(len(model_ids), variants)
            images = _load_images(intent.input_paths)
            prepared, providers = self._prepare(
                intent,
                model_ids,
                images,
                shared_parameters=shared_parameters,
                native_parameters=native_parameters,
            )
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
        images: tuple[LocalImage, ...],
        *,
        shared_parameters: SharedImageParams | None = None,
        native_parameters: ProviderParams | None = None,
    ) -> tuple[dict[ModelId, PreparedImageRequest], dict[ModelId, ImageProvider]]:
        media = tuple(PreparedMedia(role=intent.media_role, image=img) for img in images)

        providers = {mid: self._registry.provider_for(mid) for mid in model_ids}

        prepared: dict[ModelId, PreparedImageRequest] = {}
        for mid, provider in providers.items():
            model_spec = self._registry.get_model(mid)
            if intent.operation not in model_spec.operations:
                raise PixgenError(
                    ErrorCode.INVALID_REQUEST,
                    f"model {mid} does not support {intent.operation.value}",
                )
            params: JsonObject = {}
            if native_parameters is not None:
                params = native_parameters.model_dump(exclude_none=True)
            elif shared_parameters is not None and shared_parameters.aspect_ratio is not None:
                params.update(
                    _resolve_shared_parameters(
                        provider,
                        model_spec.id,
                        intent.operation,
                        shared_parameters,
                    )
                )
            overlapping = set(intent.params).intersection(params)
            if overlapping:
                names = ", ".join(sorted(overlapping))
                raise PixgenError(
                    ErrorCode.INVALID_REQUEST,
                    f"parameter already supplied by intent: {names}",
                )
            resolved_params = {**intent.params, **params}
            intent_with_params = type(intent).model_validate(
                {**intent.model_dump(), "params": resolved_params}
            )
            try:
                request = provider.validate(
                    intent=intent_with_params,
                    model=model_spec,
                )
            except ValidationError as exc:
                raise PixgenError(ErrorCode.INVALID_REQUEST, validation_message(exc)) from exc
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


def _resolve_shared_parameters(
    provider: ImageProvider,
    model_id: ModelId,
    operation: ImageOperation,
    shared: SharedImageParams,
) -> JsonObject:
    """Resolve shared parameters through a provider-owned model definition."""
    definitions = getattr(provider, "definitions", None)
    if definitions is None:
        raise PixgenError(
            ErrorCode.INVALID_REQUEST,
            f"model {model_id} does not support shared aspect ratios",
        )
    definition = next((item for item in definitions() if item.spec.id == model_id), None)
    if definition is None:
        raise PixgenError(
            ErrorCode.MODEL_NOT_FOUND,
            f"model {model_id!r} is not in the provider catalogue",
        )
    operation_definition = definition.operations.get(operation)
    if operation_definition is None:
        raise PixgenError(
            ErrorCode.INVALID_REQUEST,
            f"model {model_id} does not support {operation.value}",
        )
    try:
        parameters = operation_definition.resolve(shared)
    except ValueError as exc:
        supported = ", ".join(sorted(operation_definition.aspect_ratios))
        raise PixgenError(
            ErrorCode.INVALID_REQUEST,
            f"model {model_id} does not support aspect ratio {shared.aspect_ratio}; "
            f"supported ratios: {supported}",
        ) from exc
    return parameters.model_dump(exclude_none=True)


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
            publication = save_artifact(plan, image.data, image.media_type)
        except TimeoutError:
            error = PublicError(code=ErrorCode.TIMEOUT, message="request timed out")
        except ProviderError as exc:
            error = PublicError(code=exc.code, message=exc.message)
        except OSError as exc:
            error = PublicError(
                code=ErrorCode.ARTIFACT_FAILURE,
                message=f"could not write artifact: {exc.strerror or 'filesystem error'}",
            )
        except Exception:  # noqa: BLE001
            error = PublicError(
                code=ErrorCode.PROVIDER_FAILURE,
                message="unexpected provider failure",
            )
        else:
            return TargetResult(
                model=plan.model_id,
                variant=plan.variant,
                artifact_path=publication.path,
                media_type=image.media_type,
                warnings=publication.warnings,
            )
    return TargetResult(model=plan.model_id, variant=plan.variant, error=error)

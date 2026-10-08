"""Test local optimisation execution and atomic publication."""

import zlib
from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from PIL import Image, ImageCms

from pixgen.cli.outcome import exit_status
from pixgen.config.models import GenerationSettings, Settings
from pixgen.core.errors import ErrorCode
from pixgen.core.results import VariantStatus
from pixgen.images.transform import ImageTransformError
from pixgen.optimization import application
from pixgen.optimization.application import OptimizeApplication
from pixgen.optimization.models import OptimizeRequest
from tests.factories import make_cmyk_profile

if TYPE_CHECKING:
    from pathlib import Path

    from pixgen.images.transform import DecodedImage


@pytest.fixture
def source(tmp_path) -> Path:
    path = tmp_path / "photo.png"
    with Image.new("RGB", (80, 40), "red") as image:
        image.save(path)
    return path


@pytest.fixture
def app() -> OptimizeApplication:
    return OptimizeApplication(Settings())


class TestExecution:
    @pytest.mark.parametrize(
        ("mode", "source_format", "output_format", "with_profile"),
        [
            ("CMYK", "JPEG", "webp", True),
            ("CMYK", "JPEG", "avif", True),
            ("CMYK", "JPEG", "png", False),
            ("I;16", "PNG", "jpeg", False),
        ],
        ids=["cmyk-icc-webp", "cmyk-icc-avif", "cmyk-png", "16-bit-jpeg"],
    )
    @pytest.mark.parametrize("dry_run", [False, True], ids=["execute", "plan"])
    def test_incompatible_mode_rejected_before_side_effects(
        self, tmp_path, app, mode, source_format, output_format, with_profile, dry_run
    ) -> None:
        source = tmp_path / "source"
        with Image.new(mode, (10, 10)) as image:
            image.save(
                source,
                format=source_format,
                icc_profile=make_cmyk_profile() if with_profile else None,
            )
        directory = tmp_path / "missing"
        result = app.run(
            OptimizeRequest(
                source=source,
                format=output_format,
                output_dir=directory,
                mkdir=True,
                dry_run=dry_run,
            )
        )
        assert result.error is not None
        assert result.error.code is ErrorCode.INVALID_REQUEST
        assert mode in result.error.message
        assert not directory.exists()
        assert list(tmp_path.iterdir()) == [source]

    def test_cmyk_jpeg_preserves_matching_profile(self, tmp_path, app) -> None:
        source = tmp_path / "source.jpg"
        profile = make_cmyk_profile()
        with BytesIO(profile) as buffer:
            assert ImageCms.ImageCmsProfile(buffer).profile.xcolor_space == "CMYK"
        with Image.new("CMYK", (10, 10)) as image:
            image.save(source, icc_profile=profile)
        destination = tmp_path / "out.jpg"
        result = app.run(OptimizeRequest(source=source, output=destination))
        assert result.variants[0].status is VariantStatus.COMPLETED
        with Image.open(destination) as output:
            assert output.mode == "CMYK"
            assert output.info["icc_profile"] == profile

    @pytest.mark.parametrize("profile_kind", ["mismatched", "invalid"], ids=str)
    def test_incompatible_profile_rejected_during_planning(
        self, tmp_path, app, profile_kind
    ) -> None:
        source = tmp_path / "source.png"
        profile = make_cmyk_profile() if profile_kind == "mismatched" else b"invalid ICC"
        with Image.new("RGB", (10, 10)) as image:
            image.save(source, icc_profile=profile)
        directory = tmp_path / "missing"
        result = app.run(OptimizeRequest(source=source, output_dir=directory, mkdir=True))
        assert result.error is not None
        assert result.error.code is ErrorCode.INVALID_REQUEST
        assert "profile" in result.error.message
        assert not directory.exists()

    @pytest.mark.parametrize(
        ("output_format", "encoder", "source_format"),
        [("jpeg", "jpeg_encoder", "PNG"), ("png", "zip_encoder", "JPEG")],
        ids=["jpeg", "png"],
    )
    def test_missing_native_encoder_rejected_before_side_effects(
        self, tmp_path, app, monkeypatch, output_format, encoder, source_format
    ) -> None:
        source = tmp_path / "source"
        with Image.new("RGB", (10, 10)) as image:
            image.save(source, format=source_format)
        Image.init()
        monkeypatch.delattr(Image.core, encoder)
        directory = tmp_path / "missing"
        result = app.run(
            OptimizeRequest(source=source, format=output_format, output_dir=directory, mkdir=True)
        )
        assert result.error is not None
        assert result.error.code is ErrorCode.INVALID_REQUEST
        assert "encoder unavailable" in result.error.message
        assert not directory.exists()
        assert list(tmp_path.iterdir()) == [source]

    @pytest.mark.parametrize(
        ("size", "bounds", "expected"),
        [((10, 45), "7x45", (7, 32)), ((45, 10), "45x7", (32, 7)), ((1000, 1), "1x1", (1, 1))],
        ids=["portrait-rounding", "landscape-rounding", "one-pixel-minimum"],
    )
    def test_fit_planned_and_written_dimensions_agree(
        self, tmp_path, app, size, bounds, expected
    ) -> None:
        source = tmp_path / "source.png"
        with Image.new("RGB", size) as image:
            image.save(source)
        request = OptimizeRequest(source=source, fit=(bounds,), output=tmp_path / "out.png")
        planned = app.run(request.model_copy(update={"dry_run": True}))
        result = app.run(request)
        assert result.variants[0].status is VariantStatus.COMPLETED
        assert (planned.variants[0].width, planned.variants[0].height) == expected
        with Image.open(request.output) as output:
            assert output.size == expected

    def test_publication_collision_after_planning_preserves_existing_file(
        self, source, tmp_path, app, monkeypatch
    ) -> None:
        destination = tmp_path / "out.png"
        encode = application.encode_clean

        def create_collision(image, **kwargs) -> bytes:
            destination.write_bytes(b"racing writer")
            return encode(image, **kwargs)

        monkeypatch.setattr(application, "encode_clean", create_collision)
        result = app.run(OptimizeRequest(source=source, output=destination))
        assert result.variants[0].error.code is ErrorCode.ARTIFACT_FAILURE
        assert destination.read_bytes() == b"racing writer"
        assert not list(tmp_path.glob("*.tmp"))

    def test_verification_loads_output_pixels_before_forced_replacement(
        self, source, tmp_path, app, monkeypatch
    ) -> None:
        content = source.read_bytes()
        offset = content.index(b"IDAT") - 4
        length = int.from_bytes(content[offset : offset + 4], "big")
        chunk = b"IDAT" + b"x" * length
        corrupt = (
            content[: offset + 4]
            + chunk
            + zlib.crc32(chunk).to_bytes(4, "big")
            + content[offset + length + 12 :]
        )
        with BytesIO(corrupt) as buffer, Image.open(buffer) as image:
            image.verify()
        destination = tmp_path / "existing.png"
        destination.write_bytes(b"original output")
        monkeypatch.setattr(application, "encode_clean", lambda *_args, **_kwargs: corrupt)
        result = app.run(OptimizeRequest(source=source, output=destination, force=True))
        assert result.variants[0].error.code is ErrorCode.OPTIMIZATION_FAILED
        assert destination.read_bytes() == b"original output"
        assert not list(tmp_path.glob("*.tmp"))

    def test_source_decode_failure_is_command_level(
        self, source, tmp_path, app, monkeypatch
    ) -> None:
        def fail_decode(*_args, **_kwargs) -> None:
            raise ImageTransformError("cannot decode source")

        monkeypatch.setattr(application, "load_normalized", fail_decode)
        directory = tmp_path / "new"
        result = app.run(OptimizeRequest(source=source, output_dir=directory, mkdir=True))
        assert result.error.code is ErrorCode.INVALID_REQUEST
        assert not result.variants
        assert not directory.exists()

    @pytest.mark.parametrize("output_format", ["png", "jpeg", "webp"], ids=str)
    def test_dimensions_format_and_metadata(self, tmp_path, app, output_format) -> None:
        path = tmp_path / f"source.{output_format}"
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        exif = Image.Exif()
        exif[274] = 6
        exif[315] = "Private author"
        exif[34853] = {1: "N", 2: (1, 2, 3)}
        with Image.new("RGB", (80, 40), "red") as image:
            image.save(path, format=output_format.upper(), exif=exif, icc_profile=profile)
        original = path.read_bytes()
        destination = tmp_path / f"clean.{output_format}"

        result = app.run(OptimizeRequest(source=path, width=(20,), output=destination))

        assert result.error is None
        variant = result.variants[0]
        assert variant.status is VariantStatus.COMPLETED
        assert (variant.width, variant.height, variant.format) == (20, 40, output_format.upper())
        assert variant.output_bytes == destination.stat().st_size
        with Image.open(destination) as output:
            output.load()
            assert output.size == (20, 40)
            assert output.format == output_format.upper()
            assert not output.getexif()
            assert output.info["icc_profile"] == profile
        assert path.read_bytes() == original

    def test_dry_run_does_not_decode_or_create_directories(
        self, source, tmp_path, app, monkeypatch
    ) -> None:
        def reject_decode(*_args, **_kwargs) -> None:
            raise AssertionError("dry run decoded pixels")

        monkeypatch.setattr(application, "load_normalized", reject_decode)
        directory = tmp_path / "new"
        result = app.run(
            OptimizeRequest(source=source, width=(20, 100), output_dir=directory, dry_run=True)
        )
        assert result.dry_run
        assert [v.status for v in result.variants] == [VariantStatus.PLANNED, VariantStatus.SKIPPED]
        assert not directory.exists()

    @pytest.mark.parametrize("mkdir", [False, True], ids=["missing", "create"])
    def test_explicit_directory_policy(self, source, tmp_path, app, mkdir) -> None:
        directory = tmp_path / "nested" / "out"
        result = app.run(OptimizeRequest(source=source, output_dir=directory, mkdir=mkdir))
        if mkdir:
            assert result.variants[0].status is VariantStatus.COMPLETED
            assert directory.is_dir()
        else:
            assert result.error.code is ErrorCode.INVALID_REQUEST
            assert not directory.exists()

    def test_configured_directory_default(self, source, tmp_path) -> None:
        directory = tmp_path / "configured"
        app = OptimizeApplication(Settings(generation=GenerationSettings(output_dir=directory)))
        result = app.run(OptimizeRequest(source=source, mkdir=True))
        assert result.variants[0].output_path == directory / "photo-optimized.png"

    def test_implicit_directory_created(self, source, tmp_path, app, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = app.run(OptimizeRequest(source=source))
        assert result.variants[0].output_path == tmp_path / "pixgen/photo-optimized.png"
        assert result.variants[0].output_path.is_file()

    def test_skip_only_leaves_directory_absent(self, source, tmp_path, app) -> None:
        directory = tmp_path / "new"
        result = app.run(OptimizeRequest(source=source, width=(100,), output_dir=directory))
        assert result.error is None
        assert result.variants[0].status is VariantStatus.SKIPPED
        assert exit_status(result) == 0
        assert not directory.exists()

    @pytest.mark.parametrize("force", [False, True], ids=["reject", "replace"])
    def test_overwrite_policy(self, source, tmp_path, app, force) -> None:
        destination = tmp_path / "existing.png"
        destination.write_bytes(b"old")
        result = app.run(OptimizeRequest(source=source, output=destination, force=force))
        if force:
            assert result.variants[0].status is VariantStatus.COMPLETED
            with Image.open(destination) as output:
                assert output.size == (80, 40)
        else:
            assert result.error.code is ErrorCode.INVALID_REQUEST
            assert destination.read_bytes() == b"old"
        assert not list(tmp_path.glob("*.tmp"))

    def test_sequential_results_decode_once(self, source, tmp_path, app, monkeypatch) -> None:
        events = []
        decode = application.load_normalized
        encode = application.encode_clean
        write = application.write_atomic

        def record_decode(*args, **kwargs) -> DecodedImage:
            events.append("decode")
            return decode(*args, **kwargs)

        def record_encode(image, **kwargs) -> bytes:
            events.append(f"encode-{image.width}")
            return encode(image, **kwargs)

        def record_write(path, data, **kwargs) -> None:
            events.append(f"write-{path.stem}")
            return write(path, data, **kwargs)

        monkeypatch.setattr(application, "load_normalized", record_decode)
        monkeypatch.setattr(application, "encode_clean", record_encode)
        monkeypatch.setattr(application, "write_atomic", record_write)
        result = app.run(OptimizeRequest(source=source, width=(20, 100, 10), output_dir=tmp_path))
        assert [v.name for v in result.variants] == ["width-20", "width-100", "width-10"]
        assert events == [
            "decode",
            "encode-20",
            "write-photo-width-20",
            "encode-10",
            "write-photo-width-10",
        ]

    @pytest.mark.parametrize("boundary", ["encode", "write"], ids=str)
    def test_sibling_failure_preserves_successes(
        self, source, tmp_path, app, monkeypatch, boundary
    ) -> None:
        original = application.encode_clean if boundary == "encode" else application.write_atomic
        calls = 0

        def fail_second(*args, **kwargs) -> bytes | None:
            nonlocal calls
            calls += 1
            if calls == 2:
                if boundary == "encode":
                    raise ImageTransformError("simulated encoder failure")
                raise OSError("simulated publication failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(
            application, "encode_clean" if boundary == "encode" else "write_atomic", fail_second
        )
        result = app.run(OptimizeRequest(source=source, width=(30, 20, 10), output_dir=tmp_path))
        assert [v.status for v in result.variants] == [
            VariantStatus.COMPLETED,
            VariantStatus.FAILED,
            VariantStatus.COMPLETED,
        ]
        expected = (
            ErrorCode.OPTIMIZATION_FAILED if boundary == "encode" else ErrorCode.ARTIFACT_FAILURE
        )
        assert result.variants[1].error.code is expected
        assert exit_status(result) == 4
        assert result.variants[1].output_path is None
        assert (tmp_path / "photo-width-30.png").is_file()
        assert not (tmp_path / "photo-width-20.png").exists()
        assert (tmp_path / "photo-width-10.png").is_file()

    def test_bad_encoded_bytes_never_published(self, source, tmp_path, app, monkeypatch) -> None:
        monkeypatch.setattr(application, "encode_clean", lambda *_args, **_kwargs: b"broken")
        destination = tmp_path / "out.png"
        result = app.run(OptimizeRequest(source=source, output=destination))
        assert result.variants[0].error.code is ErrorCode.OPTIMIZATION_FAILED
        assert exit_status(result) == 3
        assert not destination.exists()

    def test_wrong_encoded_dimensions_never_published(
        self, source, tmp_path, app, monkeypatch
    ) -> None:
        with BytesIO() as buffer, Image.new("RGB", (1, 1)) as image:
            image.save(buffer, format="PNG")
            content = buffer.getvalue()
        monkeypatch.setattr(application, "encode_clean", lambda *_args, **_kwargs: content)
        result = app.run(OptimizeRequest(source=source, output=tmp_path / "out.png"))
        assert result.variants[0].error.code is ErrorCode.OPTIMIZATION_FAILED
        assert not (tmp_path / "out.png").exists()

    def test_corrupt_pixel_payload_rejected_before_directory_creation(self, tmp_path, app) -> None:
        path = tmp_path / "corrupt.png"
        with Image.new("RGB", (80, 40)) as image:
            image.save(path)
        content = path.read_bytes()
        offset = content.index(b"IDAT") - 4
        length = int.from_bytes(content[offset : offset + 4], "big")
        chunk = b"IDAT" + b"x" * length
        path.write_bytes(
            content[: offset + 4]
            + chunk
            + zlib.crc32(chunk).to_bytes(4, "big")
            + content[offset + length + 12 :]
        )
        directory = tmp_path / "new"
        result = app.run(OptimizeRequest(source=path, output_dir=directory, mkdir=True))
        assert result.error.code is ErrorCode.INVALID_REQUEST
        assert not directory.exists()

    def test_unexpected_programming_error_propagates(
        self, source, tmp_path, app, monkeypatch
    ) -> None:
        def broken(*_args, **_kwargs) -> None:
            raise RuntimeError("programming mistake")

        monkeypatch.setattr(application, "encode_clean", broken)
        with pytest.raises(RuntimeError, match="programming mistake"):
            app.run(OptimizeRequest(source=source, output_dir=tmp_path))

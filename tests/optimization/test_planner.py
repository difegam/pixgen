"""Test pure optimisation planning and output preflight."""

from typing import TYPE_CHECKING

import pytest
from PIL import Image, ImageFile
from pydantic import ValidationError

from pixgen.core.errors import ErrorCode, PixgenError
from pixgen.images.models import ImageFormat
from pixgen.images.transform import ResizeOperation
from pixgen.optimization.models import OptimizeRequest, ResizeSpec
from pixgen.optimization.planner import build_plan

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def source(tmp_path) -> Path:
    path = tmp_path / "photo.png"
    Image.new("RGB", (2400, 1600)).save(path)
    return path


def _size(variant) -> tuple[int, int]:
    return variant.target.width, variant.target.height


class TestPlanning:
    def test_header_inspection_does_not_decode_pixels(self, source, monkeypatch) -> None:
        def reject_load(_image, *args, **kwargs) -> None:
            raise AssertionError("planning decoded source pixels")

        def reject_verify(_image) -> None:
            raise AssertionError("planning verified the whole source stream")

        monkeypatch.setattr(ImageFile.ImageFile, "load", reject_load)
        monkeypatch.setattr(Image.Image, "verify", reject_verify)
        build_plan(OptimizeRequest(source=source, dry_run=True))

    def test_default_same_dimensions(self, source, tmp_path) -> None:
        plan = build_plan(
            OptimizeRequest(source=source, mkdir=True), default_output_dir=tmp_path / "out"
        )
        assert (plan.format, plan.quality) == (ImageFormat.PNG, None)
        assert plan.source.content == source.read_bytes()
        assert [(v.spec.name, *_size(v), v.output_path) for v in plan.variants] == [
            ("optimized", 2400, 1600, tmp_path / "out/photo-optimized.png")
        ]

    def test_web_preset(self, source) -> None:
        plan = build_plan(OptimizeRequest(source=source, web=True))
        assert (plan.format, plan.quality) == (ImageFormat.WEBP, 82)
        assert [(v.spec.name, v.spec.operation, *_size(v)) for v in plan.variants] == [
            ("thumbnail", ResizeOperation.COVER, 400, 400),
            ("card", ResizeOperation.COVER, 1200, 630),
            ("content", ResizeOperation.WIDTH, 1280, 853),
            ("hero", ResizeOperation.COVER, 1920, 1080),
        ]

    def test_custom_order(self, source) -> None:
        plan = build_plan(
            OptimizeRequest(
                source=source,
                web=True,
                fit=("800x600", "400x400"),
                cover=("600x300", "300x300"),
                width=("500", "250"),
            )
        )
        assert [v.spec.name for v in plan.variants] == [
            "thumbnail",
            "card",
            "content",
            "hero",
            "fit-800x600",
            "fit-400x400",
            "cover-600x300",
            "cover-300x300",
            "width-500",
            "width-250",
        ]
        heights = build_plan(OptimizeRequest(source=source, height=("400", "200")))
        assert [v.spec.name for v in heights.variants] == ["height-400", "height-200"]

    def test_overrides(self, source) -> None:
        plan = build_plan(OptimizeRequest(source=source, web=True, format="jpeg", quality=90))
        assert (plan.format, plan.quality) == (ImageFormat.JPEG, 90)
        assert all(v.output_path.suffix == ".jpg" for v in plan.variants)

    def test_exif_orientation(self, tmp_path) -> None:
        path = tmp_path / "rotated.jpg"
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (100, 200)).save(path, exif=exif)
        plan = build_plan(OptimizeRequest(source=path))
        assert _size(plan.variants[0]) == (200, 100)

    def test_png_orientation_after_pixel_chunks(self, tmp_path, monkeypatch) -> None:
        path = tmp_path / "rotated.png"
        exif = Image.Exif()
        exif[274] = 8
        Image.new("RGB", (100, 200)).save(path, exif=exif)
        content = path.read_bytes()
        chunks = []
        offset = 8
        while offset < len(content):
            length = int.from_bytes(content[offset : offset + 4], "big")
            chunks.append(content[offset : offset + length + 12])
            offset += length + 12
        exif_chunk = next(chunk for chunk in chunks if chunk[4:8] == b"eXIf")
        reordered = [chunk for chunk in chunks if chunk != exif_chunk]
        reordered.insert(-1, exif_chunk)
        path.write_bytes(content[:8] + b"".join(reordered))

        def reject_load(_image, *args, **kwargs) -> None:
            raise AssertionError("planning decoded source pixels")

        monkeypatch.setattr(ImageFile.ImageFile, "load", reject_load)
        plan = build_plan(OptimizeRequest(source=path, dry_run=True))
        assert _size(plan.variants[0]) == (200, 100)

    def test_fit_clamps_without_upscale(self, source) -> None:
        plan = build_plan(OptimizeRequest(source=source, fit=("9000x9000", "1000x1000")))
        assert [(*_size(v), v.reason) for v in plan.variants] == [
            (2400, 1600, None),
            (1000, 667, None),
        ]

    @pytest.mark.parametrize(
        "sizes",
        [{"width": ("3000",)}, {"height": ("2000",)}, {"cover": ("2000x2000",)}],
        ids=["width", "height", "cover-aspect-ratio"],
    )
    def test_skip_only_is_valid(self, source, sizes) -> None:
        plan = build_plan(OptimizeRequest(source=source, **sizes))
        assert not plan.runnable
        assert [v.reason for v in plan.variants] == ["would upscale"]

    def test_large_positive_width_skips_without_numeric_overflow(self, source) -> None:
        plan = build_plan(OptimizeRequest(source=source, width=(str(10**400),)))
        assert plan.variants[0].spec.width == 10**400
        assert plan.variants[0].reason == "would upscale"

    def test_skipped_variant_ignores_existing_destination(self, source, tmp_path) -> None:
        (tmp_path / "photo-width-3000.png").write_bytes(b"keep")
        plan = build_plan(
            OptimizeRequest(source=source, width=("3000", "100"), output_dir=tmp_path)
        )
        assert [v.reason for v in plan.variants] == ["would upscale", None]
        assert (tmp_path / "photo-width-3000.png").read_bytes() == b"keep"

    def test_dry_run_has_no_writes(self, source, tmp_path) -> None:
        output_dir = tmp_path / "missing/nested"
        plan = build_plan(
            OptimizeRequest(source=source, output_dir=output_dir, dry_run=True, mkdir=True)
        )
        assert plan.variants[0].output_path.is_absolute()
        assert not output_dir.exists()
        assert list(tmp_path.iterdir()) == [source]

    def test_dry_run_rejects_missing_explicit_directory_without_mkdir(
        self, source, tmp_path
    ) -> None:
        directory = tmp_path / "missing"
        with pytest.raises(PixgenError, match="--mkdir") as exc_info:
            build_plan(OptimizeRequest(source=source, output_dir=directory, dry_run=True))
        assert exc_info.value.code is ErrorCode.INVALID_REQUEST
        assert not directory.exists()

    def test_default_and_explicit_paths(self, source, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        plan = build_plan(OptimizeRequest(source=source))
        assert plan.variants[0].output_path == tmp_path / "pixgen/photo-optimized.png"
        plan = build_plan(OptimizeRequest(source=source, output=tmp_path / "result.png"))
        assert plan.variants[0].output_path == tmp_path / "result.png"

    @pytest.mark.parametrize(
        ("output", "output_format", "expected"),
        [
            ("result", "webp", "result.webp"),
            ("result.webp", "webp", "result.webp"),
            ("result.jpeg", "jpeg", "result.jpeg"),
            ("result.JPG", "jpeg", "result.JPG"),
            ("result.png", "keep", "result.png"),
        ],
        ids=["add-suffix", "matching", "jpeg-alias", "case-insensitive", "keep-source-format"],
    )
    def test_explicit_output_extension_is_kept_or_added(
        self, source, tmp_path, output, output_format, expected
    ) -> None:
        plan = build_plan(
            OptimizeRequest(source=source, output=tmp_path / output, format=output_format)
        )

        assert plan.variants[0].output_path == tmp_path / expected

    @pytest.mark.parametrize(
        ("output", "output_format"),
        [("result.png", "webp"), ("result.png", "jpeg"), ("result.webp", "keep")],
        ids=["webp", "jpeg", "keep"],
    )
    def test_explicit_output_extension_conflict_is_rejected(
        self, source, tmp_path, output, output_format
    ) -> None:
        with pytest.raises(PixgenError, match="conflicts") as exc_info:
            build_plan(
                OptimizeRequest(source=source, output=tmp_path / output, format=output_format)
            )

        assert exc_info.value.code is ErrorCode.INVALID_REQUEST


class TestRejections:
    @pytest.mark.parametrize("output_format", ["", "gif"], ids=["empty", "gif"])
    def test_unknown_format_is_rejected_by_the_request(self, source, output_format) -> None:
        with pytest.raises(ValidationError):
            OptimizeRequest(source=source, format=output_format)

    @pytest.mark.parametrize("target_exists", [False, True], ids=["dangling", "existing"])
    @pytest.mark.parametrize("force", [False, True], ids=["no-force", "force"])
    @pytest.mark.parametrize("explicit", [False, True], ids=["named-output", "explicit-output"])
    def test_rejects_leaf_output_symlinks(
        self, source, tmp_path, target_exists, force, explicit
    ) -> None:
        target = tmp_path / "target.png"
        if target_exists:
            target.write_bytes(b"keep")
        output = tmp_path / ("out.png" if explicit else "photo-optimized.png")
        output.symlink_to(target)
        options = {"output": output} if explicit else {"output_dir": tmp_path}

        with pytest.raises(PixgenError, match="symbolic link") as exc_info:
            build_plan(OptimizeRequest(source=source, force=force, **options))

        assert exc_info.value.code is ErrorCode.INVALID_REQUEST
        assert output.is_symlink()
        assert target.exists() is target_exists
        if target_exists:
            assert target.read_bytes() == b"keep"

    def test_source_aliases_and_non_file_destinations(self, source, tmp_path) -> None:
        symlink = tmp_path / "alias.png"
        symlink.symlink_to(source)
        hardlink = tmp_path / "hardlink.png"
        hardlink.hardlink_to(source)
        for output in (symlink, hardlink, tmp_path, source / "child.png"):
            with pytest.raises(PixgenError) as exc_info:
                build_plan(OptimizeRequest(source=source, output=output, force=True))
            assert exc_info.value.code is ErrorCode.INVALID_REQUEST

    @pytest.mark.parametrize(
        "options",
        [
            {"fit": ("0x2",)},
            {"cover": ("1:2",)},
            {"fit": ("a=1x2:fit",)},
            {"width": ("-1",)},
            {"height": ("1.5",)},
            {"quality": 0},
            {"quality": 101},
            {"quality": 82},
            {"width": ("5",), "height": ("5",)},
            {"fit": ("400x400", "400x400")},
            {"web": True, "cover": ("400x400",)},
        ],
        ids=[
            "zero-fit",
            "colon-cover",
            "packed",
            "negative",
            "fraction",
            "quality-zero",
            "quality-high",
            "png-quality",
            "stretch",
            "duplicate",
            "preset-duplicate",
        ],
    )
    def test_invalid_request(self, source, options) -> None:
        with pytest.raises(PixgenError) as exc_info:
            build_plan(OptimizeRequest(source=source, **options))
        assert exc_info.value.code is ErrorCode.INVALID_REQUEST

    def test_runtime_capability(self, source, monkeypatch) -> None:
        monkeypatch.setattr(
            "pixgen.optimization.planner.has_codec", lambda _format, *, encode: not encode
        )
        with pytest.raises(PixgenError, match="encoder"):
            build_plan(OptimizeRequest(source=source))
        monkeypatch.setattr(
            "pixgen.optimization.planner.has_codec", lambda _format, *, encode: encode
        )
        with pytest.raises(PixgenError, match="decoder"):
            build_plan(OptimizeRequest(source=source))

    def test_animated(self, tmp_path) -> None:
        source = tmp_path / "animated.png"
        Image.new("RGB", (10, 10), "red").save(
            source, save_all=True, append_images=[Image.new("RGB", (10, 10), "blue")]
        )
        with pytest.raises(PixgenError, match="animated"):
            build_plan(OptimizeRequest(source=source))

    @pytest.mark.parametrize("mode", ["RGBA", "LA", "P"], ids=["rgba", "la", "palette"])
    def test_transparency_to_jpeg(self, tmp_path, mode) -> None:
        source = tmp_path / "alpha.png"
        image = Image.new(mode, (10, 10))
        image.save(source, **({"transparency": 0} if mode == "P" else {}))
        with pytest.raises(PixgenError, match="transparen"):
            build_plan(OptimizeRequest(source=source, format="jpeg"))

    def test_output_combinations(self, source, tmp_path) -> None:
        for options in (
            {"output": source},
            {"output": source.parent / "../" / source.parent.name / source.name},
            {"output": tmp_path / "out.png", "web": True},
            {"output": tmp_path / "out.png", "output_dir": tmp_path},
        ):
            with pytest.raises(PixgenError) as exc_info:
                build_plan(OptimizeRequest(source=source, **options))
            assert exc_info.value.code is ErrorCode.INVALID_REQUEST

    def test_collisions_and_force(self, source, tmp_path) -> None:
        output = tmp_path / "out.png"
        output.write_bytes(b"keep")
        with pytest.raises(PixgenError, match="exist"):
            build_plan(OptimizeRequest(source=source, output=output))
        build_plan(OptimizeRequest(source=source, output=output, force=True))
        assert output.read_bytes() == b"keep"

    def test_missing_source(self, tmp_path) -> None:
        with pytest.raises(PixgenError) as exc_info:
            build_plan(OptimizeRequest(source=tmp_path / "missing.png"))
        assert exc_info.value.code is ErrorCode.INVALID_REQUEST

    def test_resize_spec_invariants(self) -> None:
        for operation, width, height in (
            (ResizeOperation.FIT, 1, None),
            (ResizeOperation.COVER, None, 1),
            (ResizeOperation.WIDTH, 1, 1),
            (ResizeOperation.HEIGHT, None, None),
        ):
            with pytest.raises(ValidationError):
                ResizeSpec(name="size", operation=operation, width=width, height=height)

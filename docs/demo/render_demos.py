"""Render the animated README demos into ``docs/assets/demo``.

The terminal content mirrors real Pixgen output: the JSON envelope is built
from :class:`pixgen.core.results.CommandResult`, the model tree comes from the
installed CLI, and progress rows follow ``pixgen.cli.progress``. Generated
images are procedural stand-ins, so no credentials or network are needed.

Run with ``uv run python docs/demo/render_demos.py``. Requires ``ffmpeg``.
"""
# Standalone docs script: seeded `random` drives art, not security; the glyphs are
# deliberate terminal characters; subprocess argv is fixed; print is CLI output.
# ruff: noqa: INP001, S311, RUF001, S603, T201

from __future__ import annotations

import argparse
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from pixgen.core.errors import ErrorCode
from pixgen.core.results import CommandResult, PublicError, TargetResult

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

__all__: list[str] = ["get_cli", "main"]

_ROOT = Path(__file__).resolve().parents[2]
_OUT_DIR = _ROOT / "docs" / "assets" / "demo"
_FPS = 20
_W, _H = 1280, 800
_FONT_FILE = "/System/Library/Fonts/Menlo.ttc"
_RUN_ID = uuid.UUID("0199bf3e-6c1a-7d2e-9f40-3b5a1c2d7e88")
_STAMP = "20261007T091502Z"

_INK = (18, 19, 28)
_BAR = (24, 26, 38)
_EDGE = (40, 43, 62)
_FG = (226, 229, 240)
_DIM = (110, 115, 138)
_CYAN = (25, 184, 240)
_MAGENTA = (255, 62, 165)
_YELLOW = (255, 213, 0)
_GREEN = (52, 211, 110)
_CARD = (27, 29, 42)


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_FONT_FILE, size, index=1 if bold else 0)


_MONO = _font(17)
_MONO_BOLD = _font(17, bold=True)
_SMALL = _font(14)
_PILL = _font(15, bold=True)
_CW = _MONO.getlength("M")
_LH = 25
_X0, _Y0 = 36, 70
_COLS = int((_W - 2 * _X0) / _CW)


# ── easing and timing ────────────────────────────────────────────────────────


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp ``value`` into ``[low, high]``."""
    return max(low, min(high, value))


def _ease_out(value: float) -> float:
    """Cubic ease-out over ``[0, 1]``."""
    return 1 - (1 - _clamp(value)) ** 3


def _phase(t: float, start: float, length: float) -> float:
    """Return linear progress of ``t`` through a window."""
    return _clamp((t - start) / length)


# ── styled text ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Span:
    """A run of text with one colour and weight."""

    text: str
    fill: tuple[int, int, int] = _FG
    bold: bool = False


type _Line = list[_Span]

_COMMAND_TOKEN = re.compile(r'"[^"]*"?|\s+|\S+')
_SUBCOMMANDS = {"create", "edit", "model", "list", "group", "ls", "get"}


def _command_spans(line: str) -> _Line:
    """Colour a shell command line."""
    spans: _Line = []
    for part in _COMMAND_TOKEN.findall(line):
        if part.startswith('"'):
            spans.append(_Span(part, _YELLOW))
        elif part == "pixgen":
            spans.append(_Span(part, _GREEN, bold=True))
        elif part.startswith("--"):
            spans.append(_Span(part, _CYAN))
        elif part in {"\\", "|"}:
            spans.append(_Span(part, _DIM))
        elif part in _SUBCOMMANDS:
            spans.append(_Span(part, _FG, bold=True))
        else:
            spans.append(_Span(part))
    return spans


_JSON_LINE = re.compile(r'^(\s*)(?:("[^"]+")(: ))?(.*?)(,?)$')


def _json_spans(line: str) -> _Line:
    """Colour one line of indented JSON."""
    match = _JSON_LINE.match(line)
    if match is None:
        return [_Span(line)]
    indent, key, colon, value, comma = match.groups()
    spans: _Line = [_Span(indent)]
    if key:
        spans += [_Span(key, _CYAN), _Span(colon, _DIM)]
    if value.startswith('"'):
        spans.append(_Span(value, _GREEN))
    elif value in {"null", "true", "false"}:
        spans.append(_Span(value, _MAGENTA))
    elif value[:1].isdigit():
        spans.append(_Span(value, _YELLOW))
    else:
        spans.append(_Span(value, _DIM))
    spans.append(_Span(comma, _DIM))
    return spans


def _tree_spans(line: str) -> _Line:
    """Colour a Rich tree line from ``model list --tree`` or ``group ls``."""
    stripped = line.lstrip("│├└─ ")
    guides = line[: len(line) - len(stripped)]
    depth = len(guides) // 4
    if depth == 0:
        return [_Span(stripped, _GREEN)]
    if ": " in stripped:
        key, value = stripped.split(": ", 1)
        return [_Span(guides, _DIM), _Span(f"{key}: ", _DIM), _Span(value)]
    style = _CYAN if depth == 1 or "/" in stripped else _FG
    return [_Span(guides, _DIM), _Span(stripped, style)]


def _clip(spans: _Line, count: int) -> _Line:
    """Return the first ``count`` characters of a styled line."""
    out: _Line = []
    for span in spans:
        if count <= 0:
            break
        out.append(_Span(span.text[:count], span.fill, span.bold))
        count -= len(span.text)
    return out


_BRAILLE_DOTS = ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 3), (1, 3))


def _draw_braille(draw: ImageDraw.ImageDraw, x: float, y: float, char: str, fill: tuple) -> None:
    """Draw a braille glyph by hand, since Menlo lacks the block."""
    bits = ord(char) - 0x2800
    for index, (col, row) in enumerate(_BRAILLE_DOTS):
        if bits & (1 << index):
            cx, cy = x + 3 + col * 5, y + 5 + row * 4.2
            draw.ellipse((cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5), fill=fill)


def _draw_line(draw: ImageDraw.ImageDraw, x: float, y: float, spans: _Line) -> None:
    """Draw a styled line on the monospace grid."""
    for span in spans:
        for char in span.text:
            if "⠀" <= char <= "⣿":
                _draw_braille(draw, x, y, char, span.fill)
            elif not char.isspace():
                font = _MONO_BOLD if span.bold else _MONO
                draw.text((x, y), char, font=font, fill=span.fill)
            x += _CW


# ── chrome and overlays ──────────────────────────────────────────────────────


def _logo_pixels(name: str) -> list[tuple[int, int, str]]:
    """Parse the pixel-art logo SVG into ``(x, y, colour)`` cells."""
    svg = (_ROOT / "docs" / "assets" / name).read_text()
    cells: list[tuple[int, int, str]] = []
    for colour, data in re.findall(r'fill="(#[0-9A-Fa-f]{6})" d="([^"]+)"', svg):
        for x, y, run in re.findall(r"M(\d+) (\d+)h(\d+)", data):
            cells.extend((int(x) + i, int(y), colour) for i in range(int(run)))
    return cells


_LOGO = _logo_pixels("logo-dark.svg")
_MARK = _logo_pixels("mark.svg")


def _window(title: str) -> Image.Image:
    """Return an empty terminal window."""
    img = Image.new("RGB", (_W, _H), _INK)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, _W, 44), fill=_BAR)
    draw.line((0, 44, _W, 44), fill=_EDGE)
    draw.rectangle((0, 0, _W - 1, _H - 1), outline=_EDGE)
    for x, y, colour in _MARK:
        draw.rectangle((18 + x * 4, 9 + y * 4, 21 + x * 4, 12 + y * 4), fill=colour)
    draw.text((_W / 2, 22), title, font=_SMALL, fill=_DIM, anchor="mm")
    return img


def _cursor(draw: ImageDraw.ImageDraw, col: float, row_y: float, t: float, *, typing: bool) -> None:
    """Draw a block cursor that blinks while idle."""
    if typing or (t * 1.6) % 1 < 0.6:
        x = _X0 + col * _CW
        draw.rectangle((x, row_y + 2, x + _CW - 1, row_y + _LH - 3), fill=_MAGENTA)


def _pill(
    layer: Image.Image, right: float, y: float, text: str, fill: tuple, appear: float
) -> None:
    """Slide a callout pill in from the right, right-aligned at ``right``."""
    if appear <= 0:
        return
    eased = _ease_out(appear)
    draw = ImageDraw.Draw(layer)
    w = _PILL.getlength(text) + 28
    x = right - w + (1 - eased) * 48
    alpha = int(255 * eased)
    draw.rounded_rectangle((x, y, x + w, y + 30), radius=15, fill=(*fill, alpha))
    draw.text((x + 14, y + 15), text, font=_PILL, fill=(*_INK, alpha), anchor="lm")


def _composite(img: Image.Image, layer: Image.Image) -> Image.Image:
    """Alpha-composite an RGBA overlay onto an RGB frame."""
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def _rounded(img: Image.Image, radius: int = 10) -> Image.Image:
    """Return a rounded-corner mask for ``img``."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *img.size), radius=radius, fill=255)
    return mask


def _pixelate(img: Image.Image, progress: float) -> Image.Image:
    """Resolve an image from coarse blocks to full resolution."""
    if progress >= 1:
        return img
    steps = (48, 32, 20, 12, 8, 4, 2)
    block = steps[min(len(steps) - 1, int(progress * len(steps)))]
    w, h = img.size
    small = img.resize((max(1, w // block), max(1, h // block)), Image.Resampling.BOX)
    return small.resize((w, h), Image.Resampling.NEAREST)


_PIXEL_COLOURS = ((0, 166, 226), (236, 0, 140), (255, 213, 0), (0, 138, 0), (236, 0, 0))


def _pending(size: tuple[int, int], t: float, seed: int) -> Image.Image:
    """Render a card that is still generating: flickering brand pixels and a sheen."""
    w, h = size
    img = Image.new("RGB", size, _CARD)
    draw = ImageDraw.Draw(img)
    cell = 14
    tick = int(t * 10)
    for gy in range(h // cell + 1):
        for gx in range(w // cell + 1):
            rng = random.Random(hash((seed, gx, gy, tick)))
            if rng.random() < 0.07:
                r, g, b = rng.choice(_PIXEL_COLOURS)
                k = rng.uniform(0.18, 0.42)
                colour = tuple(
                    int(c * k + base * (1 - k)) for c, base in zip((r, g, b), _CARD, strict=True)
                )
                draw.rectangle(
                    (gx * cell + 1, gy * cell + 1, gx * cell + cell - 2, gy * cell + cell - 2),
                    fill=colour,
                )
    sheen = ((t * 0.7 + seed * 0.21) % 1.6 - 0.3) * w
    band = Image.new("L", size, 0)
    ImageDraw.Draw(band).polygon(
        [(sheen, 0), (sheen + 90, 0), (sheen + 30, h), (sheen - 60, h)], fill=36
    )
    band = band.filter(ImageFilter.GaussianBlur(18))
    return Image.composite(Image.new("RGB", size, (90, 96, 130)), img, band)


def _place_card(
    frame: Image.Image, card: Image.Image, x: int, y: int, label: str, colour: tuple
) -> None:
    """Paste a rounded image card with a caption underneath."""
    draw = ImageDraw.Draw(frame)
    draw.rounded_rectangle(
        (x - 1, y - 1, x + card.width, y + card.height), radius=11, outline=_EDGE
    )
    frame.paste(card, (x, y), _rounded(card))
    draw.text((x + 2, y + card.height + 10), label, font=_SMALL, fill=colour)


# ── procedural "generated" images ────────────────────────────────────────────


@dataclass(frozen=True)
class _Mood:
    """Palette for one procedural fjord scene."""

    sky: tuple[str, str]
    sun: str | None
    ridges: tuple[str, str, str]
    water: str
    land: str
    roof: str
    wall: str
    glow: str
    aurora: bool = False


_MOODS = {
    "dusk": _Mood(
        ("#1D1E4E", "#F47C5A"),
        "#FFC56B",
        ("#7A5594", "#4E3C78", "#2C2550"),
        "#3A2F5E",
        "#17142B",
        "#2B1F2E",
        "#8A2A33",
        "#FFD27A",
    ),
    "day": _Mood(
        ("#3E8EDB", "#D4EEF9"),
        "#FFF8E0",
        ("#A9C0D6", "#7393B1", "#3F5F7E"),
        "#2F6E9A",
        "#3D6B3A",
        "#40602C",
        "#A3301F",
        "#FFE9A8",
    ),
    "aurora": _Mood(
        ("#04060F", "#163A55"),
        None,
        ("#21394E", "#152838", "#0B1724"),
        "#0B2233",
        "#07101A",
        "#1A1A22",
        "#5A1F23",
        "#FFC24D",
        aurora=True,
    ),
}


def _gradient(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
    """Return a vertical gradient."""
    mask = Image.linear_gradient("L").resize(size)
    return Image.composite(Image.new("RGB", size, bottom), Image.new("RGB", size, top), mask)


def _shade(colour: str, factor: float = 0.72) -> tuple[int, int, int]:
    """Darken a hex colour."""
    r, g, b = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return int(r * factor), int(g * factor), int(b * factor)


def _draw_cabin(draw: ImageDraw.ImageDraw, w: int, h: int, mood: _Mood) -> None:
    """Draw the red Norwegian cabin with its sod roof."""
    cx, ground = 0.2 * w, 0.71 * h
    bw, bh = 0.17 * w, 0.11 * h
    draw.rectangle(
        (cx + 0.03 * w, ground - bh - 0.1 * h, cx + 0.05 * w, ground - bh), fill="#2A2224"
    )
    draw.rectangle((cx - bw / 2, ground - bh, cx + bw / 2, ground), fill=mood.wall)
    for i in range(1, 6):
        x = cx - bw / 2 + i * bw / 6
        draw.line((x, ground - bh, x, ground), fill=_shade(mood.wall), width=max(1, w // 400))
    draw.polygon(
        [
            (cx - bw / 2 - 0.02 * w, ground - bh + 2),
            (cx, ground - bh - 0.085 * h),
            (cx + bw / 2 + 0.02 * w, ground - bh + 2),
        ],
        fill=mood.roof,
    )
    draw.rectangle(
        (cx - 0.055 * w, ground - 0.07 * h, cx - 0.02 * w, ground - 0.035 * h), fill=mood.glow
    )
    draw.rectangle((cx + 0.015 * w, ground - 0.075 * h, cx + 0.045 * w, ground), fill="#2A1B1B")


def _fjord(size: tuple[int, int], mood_name: str, seed: int) -> tuple[Image.Image, Image.Image]:
    """Paint a cabin-beside-a-fjord scene and its background-free cutout."""
    mood = _MOODS[mood_name]
    w, h = size[0] * 2, size[1] * 2
    rng = random.Random(seed)
    img = _gradient((w, h), *mood.sky)
    draw = ImageDraw.Draw(img)
    horizon = int(h * 0.6)
    if mood.aurora:
        for _ in range(160):
            x, y = rng.uniform(0, w), rng.uniform(0, horizon * 0.8)
            r = rng.choice((1, 1, 2))
            draw.ellipse((x - r, y - r, x + r, y + r), fill="#DDE8FF")
        veil = Image.new("RGBA", (w, h))
        vdraw = ImageDraw.Draw(veil)
        for colour, base, amp in (
            ("#2BF59A70", 0.22, 0.07),
            ("#C04BFF55", 0.14, 0.05),
            ("#2BD8F560", 0.3, 0.05),
        ):
            points = [
                (x, h * (base + amp * math.sin(x / w * 7 + rng.uniform(0, 6))))
                for x in range(0, w + 20, 20)
            ]
            vdraw.line(points, fill=colour, width=int(h * 0.07))
        img.paste(
            veil.filter(ImageFilter.GaussianBlur(h * 0.03)),
            (0, 0),
            veil.filter(ImageFilter.GaussianBlur(h * 0.03)),
        )
    if mood.sun:
        sx, sy, sr = 0.72 * w, horizon - 0.13 * h, 0.07 * w
        glow = Image.new("L", (w, h), 0)
        ImageDraw.Draw(glow).ellipse(
            (sx - sr * 2.4, sy - sr * 2.4, sx + sr * 2.4, sy + sr * 2.4), fill=110
        )
        img = Image.composite(
            Image.new("RGB", (w, h), mood.sun), img, glow.filter(ImageFilter.GaussianBlur(sr))
        )
        draw = ImageDraw.Draw(img)
        draw.ellipse((sx - sr, sy - sr, sx + sr, sy + sr), fill=mood.sun)
    for index, colour in enumerate(mood.ridges):
        base = horizon - h * (0.26 - index * 0.085)
        phases = [rng.uniform(0, 6.28) for _ in range(3)]
        ridge = [
            (
                x,
                base
                + h
                * (
                    0.05 * math.sin(x / w * 5 + phases[0])
                    + 0.03 * math.sin(x / w * 13 + phases[1])
                    + 0.012 * math.sin(x / w * 31 + phases[2])
                ),
            )
            for x in range(0, w + 8, 8)
        ]
        draw.polygon([(0, horizon), *ridge, (w, horizon)], fill=colour)
    upper = img.crop((0, 2 * horizon - h, w, horizon)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    water = Image.blend(upper, Image.new("RGB", upper.size, mood.water), 0.5)
    rippled = water.copy()
    for y in range(water.height):
        shift = int(6 * math.sin(y * 0.3) * (y / water.height + 0.2))
        rippled.paste(water.crop((max(0, -shift), y, w - max(0, shift), y + 1)), (max(0, shift), y))
    img.paste(rippled, (0, horizon))
    draw = ImageDraw.Draw(img)
    draw.line((0, horizon, w, horizon), fill=mood.ridges[0], width=2)
    ground = 0.71 * h
    land = [
        (0, ground - 0.012 * h),
        (0.14 * w, ground - 0.016 * h),
        (0.31 * w, ground + 0.006 * h),
        (0.45 * w, ground + 0.045 * h),
        (0.58 * w, 0.88 * h),
        (0.66 * w, h),
        (0, h),
    ]
    draw.polygon(land, fill=mood.land)
    _draw_cabin(draw, w, h, mood)
    cutout = Image.new("RGBA", (w, h))
    cdraw = ImageDraw.Draw(cutout)
    cdraw.ellipse((0.06 * w, ground - 0.025 * h, 0.34 * w, ground + 0.05 * h), fill=mood.land)
    _draw_cabin(cdraw, w, h, mood)
    return img.resize(size, Image.Resampling.LANCZOS), cutout.resize(size, Image.Resampling.LANCZOS)


def _checkerboard(size: tuple[int, int]) -> Image.Image:
    """Return a dark transparency checkerboard."""
    img = Image.new("RGB", size, (34, 37, 52))
    draw = ImageDraw.Draw(img)
    for y in range(0, size[1], 14):
        for x in range(0, size[0], 14):
            if (x // 14 + y // 14) % 2:
                draw.rectangle((x, y, x + 13, y + 13), fill=(26, 28, 40))
    return img


# ── shared terminal pieces ───────────────────────────────────────────────────

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_PROMPT = _Span("❯ ", _MAGENTA, bold=True)


def _draw_command(
    draw: ImageDraw.ImageDraw,
    lines: Sequence[str],
    t: float,
    start: float,
    cps: float,
    y: float = _Y0,
) -> float:
    """Type a (possibly continued) command; return the time typing ends."""
    end = start + sum(len(line) for line in lines) / cps
    remaining = int(max(0.0, t - start) * cps)
    for row, line in enumerate(lines):
        if row and remaining <= 0:
            break
        shown = min(remaining, len(line))
        lead = [_PROMPT] if row == 0 else [_Span("  ")]
        _draw_line(draw, _X0, y + row * _LH, lead + _clip(_command_spans(line), shown))
        if remaining <= len(line) or row == len(lines) - 1:
            if t < end + 0.25:
                _cursor(draw, 2 + shown, y + row * _LH, t, typing=t < end)
            break
        remaining -= len(line)
    return end


def _idle_prompt(draw: ImageDraw.ImageDraw, y: float, t: float) -> None:
    """Draw a fresh prompt waiting for input."""
    _draw_line(draw, _X0, y, [_PROMPT])
    _cursor(draw, 2, y, t, typing=False)


def _elapsed(seconds: float) -> str:
    """Format like Rich's ``TimeElapsedColumn``."""
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _artifact(model: str, variant: int = 1, directory: str = "renders") -> str:
    """Return the artifact path Pixgen generates for a target."""
    return f"{directory}/{_STAMP}-{_RUN_ID}-{model.replace('/', '-')}-v{variant}.png"


def _ellipsis(text: str, limit: int) -> str:
    """Truncate with an ellipsis like Rich's ``overflow="ellipsis"``."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass(frozen=True)
class _Job:
    """One planned target and its simulated timing."""

    model: str
    start: float
    done: float


def _progress_rows(jobs: Sequence[_Job], t: float, speed: float) -> list[_Line]:
    """Render ``pixgen.cli.progress`` rows at time ``t``."""
    desc = max(len(f"{job.model} v1") for job in jobs)
    detail_cols = _COLS - (2 + 4 + desc + 1 + 11 + 8 + 1)
    rows: list[_Line] = []
    for index, job in enumerate(jobs, start=1):
        ordinal = f"{index}/{len(jobs)}"
        if t < job.start:
            marker, status, colour, detail, clock = _Span("·", _DIM), "Queued", _DIM, "", "-:--:--"
        elif t < job.done:
            frame = _SPINNER[int(t / 0.08) % len(_SPINNER)]
            marker, status, colour, detail = _Span(frame, _GREEN), "Generating", _CYAN, ""
            clock = _elapsed((t - job.start) * speed)
        else:
            marker, status, colour = _Span("✓"), "Saved", _GREEN
            detail = _ellipsis(_artifact(job.model), detail_cols)
            clock = _elapsed((job.done - job.start) * speed)
        rows.append(
            [
                marker,
                _Span(f" {ordinal} "),
                _Span(f"{job.model} v1".ljust(desc + 1)),
                _Span(status.ljust(11), colour),
                _Span(detail.ljust(detail_cols)),
                _Span(" " + clock, _DIM),
            ]
        )
    return rows


def _result_table(models: Sequence[str]) -> list[_Line]:
    """Render the interactive ``CommandResult`` table."""
    model_w = max(len("Model"), *(len(m) for m in models)) + 2
    out_w = _COLS - model_w - 10 - 8 - 4
    header = [
        _Span("  "),
        _Span("Model".ljust(model_w), bold=True),
        _Span("Variant".ljust(10), bold=True),
        _Span("Status".ljust(8), bold=True),
        _Span("Output", bold=True),
    ]
    rule = [_Span(" " + "─" * (model_w + 10 + 8 + out_w + 2), _DIM)]
    rows = [
        [
            _Span("  "),
            _Span(m.ljust(model_w)),
            _Span("1".ljust(10)),
            _Span("Saved".ljust(8), _GREEN),
            _Span(_ellipsis(_artifact(m), out_w)),
        ]
        for m in models
    ]
    caption = f"Interactive Command Result - Run ID: {_RUN_ID}"
    pad = (model_w + 10 + 8 + out_w + 4 - len(caption)) // 2
    return [header, rule, *rows, [], [_Span(" " * pad + caption, _DIM)]]


# ── demo 1: create across providers ──────────────────────────────────────────

_CREATE_MODELS = (
    "openai/gpt-image-2",
    "gemini/gemini-3.1-flash-image",
    "openrouter/openai/gpt-image-2.5-sunburst",
)
_CARD_W = (_W - 2 * _X0 - 2 * 24) // 3
_CARD_SIZE = (_CARD_W, _CARD_W * 9 // 16)
_SCENES = [
    _fjord(_CARD_SIZE, mood, seed)[0] for mood, seed in (("dusk", 3), ("day", 7), ("aurora", 11))
]


def _intro(t: float) -> Image.Image:
    """Assemble the pixel logo, then fade in the tagline."""
    img = Image.new("RGB", (_W, _H), _INK)
    layer = Image.new("RGBA", (_W, _H))
    draw = ImageDraw.Draw(layer)
    scale = 14
    ox, oy = (_W - 47 * scale) // 2, 250
    rng = random.Random(5)
    for x, y, colour in _LOGO:
        delay = rng.uniform(0, 0.9) * (0.4 + 0.6 * x / 47)
        p = _ease_out(_phase(t, 0.15 + delay, 0.4))
        if p <= 0:
            continue
        r, g, b = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
        top = oy + y * scale - (1 - p) * 40
        draw.rectangle(
            (ox + x * scale, top, ox + x * scale + scale - 1, top + scale - 1),
            fill=(r, g, b, int(255 * p)),
        )
    for text, font, fill, y, at in (
        ("One CLI. Every image model. Your keys.", _font(30, bold=True), _FG, 430, 1.25),
        ("OpenAI · Gemini · OpenRouter  —  local, typed, scriptable", _font(18), _DIM, 482, 1.55),
    ):
        a = _ease_out(_phase(t, at, 0.45))
        draw.text(
            (_W / 2, y + (1 - a) * 12), text, font=font, fill=(*fill, int(255 * a)), anchor="mm"
        )
    return _composite(img, layer)


def _create_demo(t: float) -> Image.Image:
    """Three providers, one command, concurrent generation."""
    if t < 2.4:
        return _intro(t)
    term = _create_terminal(t)
    if t < 2.9:
        return Image.blend(_intro(t), term, _ease_out(_phase(t, 2.4, 0.5)))
    return term


_CREATE_BASE = _window("pixgen — create")


def _create_terminal(t: float) -> Image.Image:
    """Render the terminal half of the create demo."""
    img = _CREATE_BASE.copy()
    draw = ImageDraw.Draw(img)
    lines = (
        'pixgen create "A modern cabin beside a Norwegian fjord" \\',
        "  --model openai/gpt-image-2 \\",
        "  --model gemini/gemini-3.1-flash-image \\",
        "  --model openrouter/openai/gpt-image-2.5-sunburst \\",
        "  --output-dir renders",
    )
    typed_end = _draw_command(draw, lines, t, 3.0, 78)
    jobs = (
        _Job(_CREATE_MODELS[0], 6.2, 9.7),
        _Job(_CREATE_MODELS[1], 6.2, 7.9),
        _Job(_CREATE_MODELS[2], 6.2, 8.8),
    )
    body_y = _Y0 + 6 * _LH
    finished = 10.1
    if typed_end + 0.3 < t < finished:
        for row, spans in enumerate(_progress_rows(jobs, t, 2.6)):
            _draw_line(draw, _X0, body_y + row * _LH, spans)
    elif t >= finished:
        table = _result_table(_CREATE_MODELS)
        shown = int((t - finished) * 40) + 1
        for row, spans in enumerate(table[:shown]):
            _draw_line(draw, _X0, body_y + row * _LH, spans)
        if shown >= len(table):
            _idle_prompt(draw, body_y + (len(table) + 1) * _LH, t)
    card_y = _H - _CARD_SIZE[1] - 64
    for index, (job, scene) in enumerate(zip(jobs, _SCENES, strict=True)):
        appear = _ease_out(_phase(t, typed_end + 0.3 + index * 0.08, 0.4))
        if appear <= 0:
            continue
        x = _X0 + index * (_CARD_W + 24)
        reveal = _phase(t, job.done, 0.9)
        card = _pixelate(scene, reveal) if t >= job.done else _pending(_CARD_SIZE, t, index)
        y = card_y + int((1 - appear) * 30)
        _place_card(img, card, x, y, job.model, _GREEN if t >= job.done else _DIM)
    layer = Image.new("RGBA", (_W, _H))
    right = _W - _X0
    for row, (text, colour, at) in enumerate(
        (
            ("3 providers · 1 command", _CYAN, 10.5),
            ("Concurrent, per-target progress", _MAGENTA, 10.8),
            ("Atomic local files", _YELLOW, 11.1),
        )
    ):
        _pill(layer, right, _Y0 + row * 40, text, colour, _phase(t, at, 0.4))
    return _composite(img, layer)


# ── demo 2: JSON for agents ──────────────────────────────────────────────────


def _json_payload() -> list[str]:
    """Build the real ``CommandResult`` JSON for a partly failed run."""
    result = CommandResult(
        run_id=_RUN_ID,
        results=(
            TargetResult(
                model="openai/gpt-image-2",
                variant=1,
                artifact_path=Path(_artifact("openai/gpt-image-2")),
                media_type="image/png",
            ),
            TargetResult(
                model="gemini/gemini-3.1-flash-image",
                variant=1,
                error=PublicError(
                    code=ErrorCode.RATE_LIMITED, message="Provider rate limit reached; retry later"
                ),
            ),
        ),
    )
    return result.model_dump_json(indent=2).splitlines()


_JSON_LINES = _json_payload()
_JSON_BASE = _window("pixgen — built for agents")


def _json_demo(t: float) -> Image.Image:
    """Show the versioned JSON envelope and annotate its contract."""
    img = _JSON_BASE.copy()
    draw = ImageDraw.Draw(img)
    command = (
        (
            'pixgen create "Studio shot of a ceramic mug" --group product-hero '
            "--output-dir renders --json"
        ),
    )
    typed_end = _draw_command(draw, command, t, 0.4, 70)
    out_at = typed_end + 0.9
    top = _Y0 + 2 * _LH
    layer = Image.new("RGBA", (_W, _H))
    marks = (
        ('"schema_version"', "Versioned contract", _CYAN),
        ('"run_id"', "One ID per run", _YELLOW),
        ('"results"', "One entry per model × variant", _GREEN),
        ('"code"', "Typed per-target errors — the run carries on", _MAGENTA),
    )
    hl = Image.new("RGBA", (_W, _H))
    hdraw = ImageDraw.Draw(hl)
    ldraw = ImageDraw.Draw(layer)
    for index, (key, text, colour) in enumerate(marks):
        at = out_at + 1.4 + index * 1.5
        row = next(i for i, line in enumerate(_JSON_LINES) if line.strip().startswith(key))
        y = top + row * _LH
        last = index == len(marks) - 1
        focus = _phase(t, at, 0.3) * (1 if last else 1 - _phase(t, at + 1.5, 0.3))
        if focus > 0:
            hdraw.rectangle(
                (_X0 - 12, y, _W - _X0 + 12, y + _LH - 1), fill=(*colour, int(34 * focus))
            )
            hdraw.rectangle((_X0 - 12, y, _X0 - 9, y + _LH - 1), fill=(*colour, int(255 * focus)))
        pill_y = y - 3 if last else _Y0 + 2 * _LH + index * 44
        shown = _ease_out(_phase(t, at, 0.4))
        if shown > 0:
            start = _X0 + len(_JSON_LINES[row]) * _CW + 14
            elbow = _W - _X0 - _PILL.getlength(text) - 28 - 18
            mid = y + _LH / 2
            ldraw.line(
                [(start, mid), (elbow, mid), (elbow, pill_y + 15), (elbow + 18, pill_y + 15)],
                fill=(*colour, int(200 * shown)),
                width=2,
            )
            ldraw.ellipse(
                (start - 3, mid - 3, start + 3, mid + 3), fill=(*colour, int(255 * shown))
            )
        _pill(layer, _W - _X0, pill_y, text, colour, _phase(t, at, 0.4))
    img = _composite(img, hl)
    draw = ImageDraw.Draw(img)
    shown = int(max(0.0, t - out_at) * 55)
    for row, line in enumerate(_JSON_LINES[:shown]):
        _draw_line(draw, _X0, top + row * _LH, _json_spans(line))
    if shown >= len(_JSON_LINES):
        _idle_prompt(draw, top + (len(_JSON_LINES) + 1) * _LH, t)
    return _composite(img, layer)


# ── demo 3: offline discovery and model groups ───────────────────────────────


def _model_tree() -> list[str]:
    """Capture the real ``pixgen model list --tree`` output."""
    output = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pixgen.cli.app import main; main()",
            "model",
            "list",
            "--tree",
        ],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "COLUMNS": "200", "NO_COLOR": "1"},
    )
    return output.stdout.rstrip().splitlines()


_TREE = _model_tree()
_GROUP_TREE = [
    "product-hero",
    "├── description: Models suited to product hero images",
    "└── models",
    "    ├── openai/gpt-image-2",
    "    └── gemini/gemini-3.1-flash-image",
]
_MODELS_BASE = _window("pixgen — offline model discovery")


def _models_demo(t: float) -> Image.Image:
    """List curated models offline, then create and list a model group."""
    img = _MODELS_BASE.copy()
    draw = ImageDraw.Draw(img)
    layer = Image.new("RGBA", (_W, _H))
    count = sum(1 for line in _TREE if "id: " in line)
    if t < 5.6:
        clear = _phase(t, 5.2, 0.4)
        shift = int(_ease_out(clear) * -_H)
        end = _draw_command(draw, ("pixgen model list --tree",), t, 0.4, 30, _Y0 + shift)
        shown = int(max(0.0, t - end - 0.3) * 40)
        for row, line in enumerate(_TREE[:shown]):
            _draw_line(draw, _X0, _Y0 + (row + 1) * _LH + shift, _tree_spans(line))
        _pill(
            layer, _W - _X0, _Y0, "Offline — no API keys needed", _CYAN, _phase(t, 2.6, 0.4) - clear
        )
        _pill(
            layer,
            _W - _X0,
            _Y0 + 40,
            f"{count} curated models · 3 providers",
            _GREEN,
            _phase(t, 2.9, 0.4) - clear,
        )
        return _composite(img, layer)
    create = (
        "pixgen group create product-hero \\",
        "  --model openai/gpt-image-2 \\",
        "  --model gemini/gemini-3.1-flash-image \\",
        '  --description "Models suited to product hero images"',
    )
    end = _draw_command(draw, create, t, 5.8, 70)
    y = _Y0 + len(create) * _LH
    if t > end + 0.4:
        _draw_line(
            draw,
            _X0,
            y,
            [
                _Span("Created model group 'product-hero' in "),
                _Span("~/Library/Application Support/pixgen/config.toml", _DIM),
            ],
        )
        _pill(
            layer,
            _W - _X0,
            _Y0 + 5 * _LH + 10,
            "Validated locally before any paid request",
            _YELLOW,
            _phase(t, end + 0.6, 0.4),
        )
    y += 2 * _LH
    if t > end + 1.4:
        list_end = _draw_command(draw, ("pixgen group ls",), t, end + 1.4, 30, y)
        shown = int(max(0.0, t - list_end - 0.3) * 30)
        for row, line in enumerate(_GROUP_TREE[:shown]):
            _draw_line(draw, _X0, y + (row + 1) * _LH, _tree_spans(line))
        if shown >= len(_GROUP_TREE):
            after = y + (len(_GROUP_TREE) + 2) * _LH
            _draw_command(
                draw,
                ('pixgen create "Hero shot of a trail shoe" --group product-hero',),
                t,
                list_end + 0.9,
                60,
                after,
            )
            _pill(
                layer,
                _W - _X0,
                after + _LH + 14,
                "Reuse a whole line-up with --group",
                _MAGENTA,
                _phase(t, list_end + 2.2, 0.4),
            )
    return _composite(img, layer)


# ── demo 4: edit ─────────────────────────────────────────────────────────────

_EDIT_SIZE = ((_W - 2 * _X0 - 80) // 2, (_W - 2 * _X0 - 80) // 2 * 9 // 16)
EDIT_SOURCE, EDIT_CUTOUT = _fjord(_EDIT_SIZE, "day", 7)
_EDIT_RESULT = _checkerboard(_EDIT_SIZE)
_EDIT_RESULT.paste(EDIT_CUTOUT, (0, 0), EDIT_CUTOUT)
_EDIT_BASE = _window("pixgen — edit")


def _edit_demo(t: float) -> Image.Image:
    """Edit an image and wipe the background away."""
    img = _EDIT_BASE.copy()
    draw = ImageDraw.Draw(img)
    lines = (
        'pixgen edit "Remove the background" --image cabin.png \\',
        "  --model openai/gpt-image-2 --output cabin-cutout.png",
    )
    end = _draw_command(draw, lines, t, 0.5, 72)
    job = _Job("openai/gpt-image-2", end + 0.4, end + 3.6)
    y = _Y0 + 3 * _LH
    if end + 0.2 < t < job.done + 0.3:
        _draw_line(draw, _X0, y, _progress_rows((job,), t, 3.5)[0])
    elif t >= job.done + 0.3:
        _draw_line(
            draw,
            _X0,
            y,
            [
                _Span("  "),
                _Span("Model".ljust(22), bold=True),
                _Span("Variant   ", bold=True),
                _Span("Status  ", bold=True),
                _Span("Output", bold=True),
            ],
        )
        _draw_line(draw, _X0, y + _LH, [_Span(" " + "─" * 72, _DIM)])
        _draw_line(
            draw,
            _X0,
            y + 2 * _LH,
            [
                _Span("  "),
                _Span("openai/gpt-image-2".ljust(22)),
                _Span("1".ljust(10)),
                _Span("Saved   ", _GREEN),
                _Span("cabin-cutout.png"),
            ],
        )
        _idle_prompt(draw, y + 4 * _LH, t)
    card_y = _H - _EDIT_SIZE[1] - 70
    left_x, right_x = _X0, _W - _X0 - _EDIT_SIZE[0]
    appear = _ease_out(_phase(t, 0.2, 0.5))
    _place_card(
        img, EDIT_SOURCE, left_x, card_y + int((1 - appear) * 24), "cabin.png  · input", _DIM
    )
    arrow_x, arrow_y = left_x + _EDIT_SIZE[0] + 40, card_y + _EDIT_SIZE[1] // 2
    draw.text(
        (arrow_x, arrow_y),
        "→",
        font=_font(34, bold=True),
        fill=_MAGENTA if t > job.start else _EDGE,
        anchor="mm",
    )
    if t > end + 0.2:
        wipe = _ease_out(_phase(t, job.done, 1.2))
        card = _pending(_EDIT_SIZE, t, 4)
        if wipe > 0:
            edge = int(_EDIT_SIZE[0] * wipe)
            card.paste(_EDIT_RESULT.crop((0, 0, edge, _EDIT_SIZE[1])), (0, 0))
            if wipe < 1:
                ImageDraw.Draw(card).rectangle(
                    (edge - 2, 0, edge + 1, _EDIT_SIZE[1]), fill=_MAGENTA
                )
        done = t >= job.done + 1.2
        _place_card(
            img, card, right_x, card_y, "cabin-cutout.png  · output", _GREEN if done else _DIM
        )
    layer = Image.new("RGBA", (_W, _H))
    _pill(
        layer,
        _W - _X0,
        _Y0 + 3 * _LH,
        "Edit with reference images",
        _CYAN,
        _phase(t, job.done + 1.4, 0.4),
    )
    _pill(
        layer,
        _W - _X0,
        _Y0 + 3 * _LH + 40,
        "Never a half-written file",
        _YELLOW,
        _phase(t, job.done + 1.7, 0.4),
    )
    return _composite(img, layer)


# ── encoding ─────────────────────────────────────────────────────────────────


def _encode(ffmpeg: str, name: str, scene: Callable[[float], Image.Image], duration: float) -> Path:
    """Render ``scene`` to PNG frames and encode an optimised looping GIF."""
    target = _OUT_DIR / f"{name}.gif"
    with tempfile.TemporaryDirectory() as tmp:
        for index in range(int(duration * _FPS)):
            scene(index / _FPS).save(Path(tmp) / f"{index:05d}.png", compress_level=1)
        palette = (
            "[a]palettegen=max_colors=256:stats_mode=full[p];"
            "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle"
        )
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-framerate",
                str(_FPS),
                "-i",
                f"{tmp}/%05d.png",
                "-vf",
                f"split[a][b];{palette}",
                "-loop",
                "0",
                str(target),
            ],
            check=True,
        )
    return target


_DEMOS: dict[str, tuple[Callable[[float], Image.Image], float]] = {
    "create": (_create_demo, 14.5),
    "json": (_json_demo, 14.0),
    "models": (_models_demo, 15.0),
    "edit": (_edit_demo, 11.0),
}


def get_cli() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="render_demos",
        description="Render Pixgen's animated README demos into docs/assets/demo.",
        epilog="Example: uv run python docs/demo/render_demos.py create json",
    )
    parser.add_argument(
        "demos",
        nargs="*",
        choices=sorted(_DEMOS),
        default=list(_DEMOS),
        help="demos to render (default: all)",
    )
    return parser


def main(demos: Sequence[str]) -> None:
    """Render the named demos.

    Args:
        demos: Names of the demos to render.

    Raises:
        SystemExit: If ``ffmpeg`` is not installed.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg is required to encode the demos")
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in demos:
        scene, duration = _DEMOS[name]
        path = _encode(ffmpeg, name, scene, duration)
        print(f"{path.relative_to(_ROOT)}  {path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main(get_cli().parse_args().demos)

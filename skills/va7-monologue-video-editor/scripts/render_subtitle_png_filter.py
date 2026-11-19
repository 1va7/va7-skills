#!/usr/bin/env python3
"""Render ASS subtitle events to transparent PNG overlays and an ffmpeg filter graph."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PRESETS = {
    "classic": {
        "font_size": 110,
        "bottom": 178,
        "leading": 20,
        "stroke_width": 2,
        "stroke_gray": 216,
        "single_line": False,
        "box": False,
        "highlight": False,
    },
    "va7-e3-single-line-highlight": {
        "font_size": 176,
        "bottom": 224,
        "leading": 0,
        "stroke_width": 4,
        "stroke_gray": 0,
        "stroke_alpha": 230,
        "single_line": True,
        "box": True,
        "box_alpha": 168,
        "box_pad_x": 76,
        "box_pad_y": 44,
        "box_radius": 44,
        "highlight": True,
        "highlight_fill": "#FFEA00",
        "highlight_words": [
            "10 亿",
            "10亿",
            "Token",
            "token",
            "AI",
            "Agent",
            "agent",
            "Vibe Coding",
            "SOP",
        ],
    },
}


def to_seconds(t: str) -> float:
    h, m, rest = t.split(":")
    s, cs = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100


def parse_ass_events(path: Path) -> list[tuple[float, float, str]]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        events.append((to_seconds(parts[1]), to_seconds(parts[2]), parts[9].replace(r"\N", "\n")))
    return events


def split_single_line_events(events: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    split_events = []
    for start, end, text in events:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if len(lines) <= 1 or end <= start:
            split_events.append((start, end, lines[0] if lines else text.replace("\n", "")))
            continue
        unit = (end - start) / len(lines)
        for idx, line in enumerate(lines):
            line_start = start + unit * idx
            line_end = end if idx == len(lines) - 1 else start + unit * (idx + 1)
            split_events.append((line_start, line_end, line))
    return split_events


def quote_filter_path(path: Path) -> str:
    return "'" + str(path.resolve()).replace("'", r"'\''") + "'"


def parse_hex_color(value: str) -> tuple[int, int, int, int]:
    s = value.strip()
    if not s.startswith("#") or len(s) not in (7, 9):
        raise ValueError(f"expected #RRGGBB or #RRGGBBAA color, got {value!r}")
    vals = [int(s[i:i + 2], 16) for i in range(1, len(s), 2)]
    if len(vals) == 3:
        vals.append(255)
    return tuple(vals)  # type: ignore[return-value]


def scale_args_for_canvas(args: argparse.Namespace) -> None:
    scale = args.height / 2160
    for name in ("font_size", "bottom", "leading", "stroke_width", "box_pad_x", "box_pad_y", "box_radius"):
        if hasattr(args, name):
            setattr(args, name, max(0, round(getattr(args, name) * scale)))


def split_highlight(line: str, highlight_words: list[str]) -> list[tuple[str, bool]]:
    if not highlight_words:
        return [(line, False)]
    words = sorted([w for w in highlight_words if w], key=len, reverse=True)
    parts: list[tuple[str, bool]] = []
    i = 0
    while i < len(line):
        matched = next((word for word in words if line.startswith(word, i)), None)
        if matched:
            parts.append((matched, True))
            i += len(matched)
            continue
        j = i + 1
        while j < len(line) and not any(line.startswith(word, j) for word in words):
            j += 1
        parts.append((line[i:j], False))
        i = j
    return parts


def text_bbox(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, text: str, stroke_width: int) -> tuple[int, int, int, int]:
    return draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)


def text_size(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, text: str, stroke_width: int) -> tuple[int, int]:
    bbox = text_bbox(draw, font, text, stroke_width)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_rich_line(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    line: str,
    font: ImageFont.FreeTypeFont,
    args: argparse.Namespace,
) -> None:
    cursor = x
    stroke = (args.stroke_gray, args.stroke_gray, args.stroke_gray, args.stroke_alpha)
    highlight_fill = parse_hex_color(args.highlight_fill)
    for chunk, highlighted in split_highlight(line, args.highlight_words if args.highlight else []):
        fill = highlight_fill if highlighted else (255, 255, 255, 255)
        draw.text(
            (cursor, y),
            chunk,
            font=font,
            fill=fill,
            stroke_width=args.stroke_width,
            stroke_fill=stroke,
        )
        cursor += text_size(draw, font, chunk, args.stroke_width)[0]


def draw_text(text: str, path: Path, args: argparse.Namespace) -> None:
    font = ImageFont.truetype(args.font_path, args.font_size)
    lines = text.split("\n")
    dummy = Image.new("RGBA", (args.width, args.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy)
    bboxes = [draw.textbbox((0, 0), line, font=font, stroke_width=args.stroke_width) for line in lines]
    line_heights = [b[3] - b[1] for b in bboxes]
    widths = [b[2] - b[0] for b in bboxes]
    total_h = sum(line_heights) + args.leading * (len(lines) - 1)
    y = args.height - args.bottom - total_h

    img = Image.new("RGBA", (args.width, args.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if args.box:
        box_w = max(widths) + args.box_pad_x * 2
        box_h = total_h + args.box_pad_y * 2
        box_x = (args.width - box_w) / 2
        box_y = y - args.box_pad_y
        draw.rounded_rectangle(
            (box_x, box_y, box_x + box_w, box_y + box_h),
            radius=args.box_radius,
            fill=(0, 0, 0, args.box_alpha),
        )

    for line, width, height in zip(lines, widths, line_heights):
        x = (args.width - width) / 2
        draw_rich_line(draw, x, y, line, font, args)
        y += height + args.leading
    img.save(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ass", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--filter-out", required=True, type=Path)
    parser.add_argument("--width", type=int, default=3840)
    parser.add_argument("--height", type=int, default=2160)
    parser.add_argument("--font-path", default="/System/Library/Fonts/Hiragino Sans GB.ttc")
    parser.add_argument("--preset", choices=sorted(PRESETS), default="classic")
    parser.add_argument("--font-size", type=int)
    parser.add_argument("--bottom", type=int)
    parser.add_argument("--leading", type=int)
    parser.add_argument("--stroke-width", type=int)
    parser.add_argument("--stroke-gray", type=int)
    parser.add_argument("--stroke-alpha", type=int)
    parser.add_argument("--single-line", action="store_true")
    parser.add_argument("--box", action="store_true")
    parser.add_argument("--box-alpha", type=int)
    parser.add_argument("--box-pad-x", type=int)
    parser.add_argument("--box-pad-y", type=int)
    parser.add_argument("--box-radius", type=int)
    parser.add_argument("--highlight", action="store_true")
    parser.add_argument("--highlight-fill")
    parser.add_argument("--highlight-words", nargs="*")
    parser.add_argument("--no-scale-preset", action="store_true", help="do not scale preset values from 4K to --height")
    args = parser.parse_args()

    preset = PRESETS[args.preset]
    for key, value in preset.items():
        current = getattr(args, key, None)
        if current is None or (isinstance(current, bool) and current is False):
            setattr(args, key, value)
    if args.stroke_alpha is None:
        args.stroke_alpha = 255
    if args.box_alpha is None:
        args.box_alpha = 0
    if args.box_pad_x is None:
        args.box_pad_x = 0
    if args.box_pad_y is None:
        args.box_pad_y = 0
    if args.box_radius is None:
        args.box_radius = 0
    if args.highlight_fill is None:
        args.highlight_fill = "#FFFFFF"
    if args.highlight_words is None:
        args.highlight_words = []
    if not args.no_scale_preset and args.height != 2160:
        scale_args_for_canvas(args)
    return args


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.filter_out.parent.mkdir(parents=True, exist_ok=True)
    events = parse_ass_events(args.ass)
    if args.single_line:
        events = split_single_line_events(events)

    for i, (_, _, text) in enumerate(events):
        draw_text(text, args.out_dir / f"sub_{i:03d}.png", args)

    lines = []
    previous = "[0:v]"
    for i, (start, end, _) in enumerate(events):
        lines.append(f"movie={quote_filter_path(args.out_dir / f'sub_{i:03d}.png')}[s{i}];")
        out = "[vout]" if i == len(events) - 1 else f"[v{i}]"
        lines.append(f"{previous}[s{i}]overlay=0:0:enable='between(t,{start:.2f},{end:.2f})'{out};")
        previous = out
    text = re.sub(r";$", "", "\n".join(lines))
    args.filter_out.write_text(text, encoding="utf-8")
    print(f"rendered {len(events)} PNGs")
    print(args.filter_out)


if __name__ == "__main__":
    main()

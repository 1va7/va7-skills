#!/usr/bin/env python3
"""Stack the current VA7 cover preview with historical reference previews."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont



def _cached_font() -> str:
    """NotoSansSC-Bold from the va7 cover asset cache (cover_assets.py ensure)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cover_assets
    return str(cover_assets.FONT)

def load_font(size: int):
    for path in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        _cached_font(),
    ):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size, index=2)
            except Exception:
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    pass
    return ImageFont.load_default()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--reference", action="append", default=[], type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--width", type=int, default=2900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if len(args.reference) < 2:
        raise SystemExit("At least two --reference previews are required")

    entries = [("CURRENT", args.current)] + [(f"REFERENCE {i}", p) for i, p in enumerate(args.reference, 1)]
    for _, path in entries:
        if not path.expanduser().exists():
            raise SystemExit(f"Missing preview: {path}")

    font = load_font(34)
    label_h = 72
    gap = 24
    rows = []
    for role, raw_path in entries:
        path = raw_path.expanduser().resolve()
        with Image.open(path) as source:
            image = source.convert("RGB")
        height = round(image.height * args.width / image.width)
        image = image.resize((args.width, height), Image.Resampling.LANCZOS)
        row = Image.new("RGB", (args.width, label_h + height), "white")
        draw = ImageDraw.Draw(row)
        draw.text((22, 16), f"{role}: {path.name}", fill=(20, 20, 20), font=font)
        row.paste(image, (0, label_h))
        rows.append(row)

    canvas = Image.new(
        "RGB",
        (args.width, sum(row.height for row in rows) + gap * (len(rows) - 1)),
        (225, 225, 225),
    )
    y = 0
    for row in rows:
        canvas.paste(row, (0, y))
        y += row.height + gap

    out = args.out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=94, subsampling=0)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

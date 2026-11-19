#!/usr/bin/env python3
"""
Render VA7 cover images from an approved frame and JSON layout.

Default output directory is <source video folder>/cover when --source-video is
provided, otherwise <frame folder>/cover.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


DEFAULT_SPECS = {
    "16x9": {"size": [3840, 2160]},
    "4x3": {"size": [2880, 2160]},
    "3x4": {"size": [1620, 2160]},
}


TEXT_BLOCK_PRESETS = {
    "va7-main-title-clear": {
        "default": {
            "fill": "#FFF500",
            "weight": 2,
        },
        "specs": {
            "16x9": {
                "font_size": 248,
                "line_gap": 18,
                "shadow": {"offset": [8, 10], "alpha": 115, "blur": 1.4, "weight": 1},
            },
            "4x3": {
                "font_size": 224,
                "line_gap": 18,
                "shadow": {"offset": [8, 10], "alpha": 115, "blur": 1.4, "weight": 1},
            },
            "3x4": {
                "font_size": 186,
                "line_gap": 16,
                "shadow": {"offset": [7, 9], "alpha": 120, "blur": 1.4, "weight": 1},
            },
        },
    },
}



def _cached_font() -> str:
    """NotoSansSC-Bold from the va7 cover asset cache (cover_assets.py ensure)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cover_assets
    return str(cover_assets.FONT)

def load_font(path: str | None, size: int):
    candidates = []
    if path:
        candidates.append(path)
    candidates += [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        _cached_font(),
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size, index=2)
            except Exception:
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    pass
    raise SystemExit("No usable CJK font found; pass --font-path")


def parse_color(value, default):
    if value is None:
        return default
    if isinstance(value, list):
        return tuple(value)
    s = str(value).strip()
    if s.startswith("#") and len(s) in (7, 9):
        vals = [int(s[i:i+2], 16) for i in range(1, len(s), 2)]
        if len(vals) == 3:
            vals.append(255)
        return tuple(vals)
    raise ValueError(f"Unsupported color: {value}")


def merge_dicts(*items: dict) -> dict:
    merged: dict = {}
    for item in items:
        for key, value in item.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = merge_dicts(merged[key], value)
            else:
                merged[key] = deepcopy(value)
    return merged


def resolve_text_block(block: dict, spec_name: str) -> dict:
    preset_name = block.get("preset")
    if not preset_name:
        return block
    preset = TEXT_BLOCK_PRESETS.get(str(preset_name))
    if not preset:
        allowed = ", ".join(sorted(TEXT_BLOCK_PRESETS))
        raise SystemExit(f"Unknown text block preset '{preset_name}'. Available presets: {allowed}")
    explicit = {k: v for k, v in block.items() if k != "preset"}
    return merge_dicts(preset.get("default", {}), preset.get("specs", {}).get(spec_name, {}), explicit)


def cover_crop(img: Image.Image, crop_box, target_size):
    if crop_box:
        crop = img.crop(tuple(crop_box))
    else:
        tw, th = target_size
        target_ratio = tw / th
        src_ratio = img.width / img.height
        if src_ratio > target_ratio:
            new_w = round(img.height * target_ratio)
            left = round((img.width - new_w) * 0.5)
            crop = img.crop((left, 0, left + new_w, img.height))
        else:
            new_h = round(img.width / target_ratio)
            top = round((img.height - new_h) * 0.5)
            crop = img.crop((0, top, img.width, top + new_h))
    return crop.resize(tuple(target_size), Image.Resampling.LANCZOS).convert("RGBA")


def offsets(weight: int):
    pts = [(0, 0)]
    for dx in range(-weight, weight + 1):
        for dy in range(-weight, weight + 1):
            if dx * dx + dy * dy <= weight * weight and (dx or dy):
                pts.append((dx, dy))
    return pts


def line_height(draw: ImageDraw.ImageDraw, font, line: str):
    bbox = draw.textbbox((0, 0), line, font=font)
    return bbox[3] - bbox[1]


def draw_block(base: Image.Image, block: dict, font_path: str | None):
    lines = block["lines"]
    xy = tuple(block.get("xy", [60, 60]))
    font = load_font(block.get("font_path") or font_path, int(block.get("font_size", 180)))
    line_gap = int(block.get("line_gap", 18))
    fill = parse_color(block.get("fill"), (255, 245, 0, 255))
    weight = int(block.get("weight", 0))
    shadow = block.get("shadow", {})
    shadow_alpha = int(shadow.get("alpha", 120))
    shadow_blur = float(shadow.get("blur", 2.0))
    shadow_offset = tuple(shadow.get("offset", [8, 10]))
    shadow_weight = int(shadow.get("weight", max(0, weight - 1)))

    if shadow_alpha > 0:
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(layer)
        x, y = xy
        yy = y
        for line in lines:
            for dx, dy in offsets(shadow_weight):
                sd.text((x + shadow_offset[0] + dx, yy + shadow_offset[1] + dy), line, font=font, fill=(0, 0, 0, shadow_alpha))
            yy += line_height(sd, font, line) + line_gap
        layer = layer.filter(ImageFilter.GaussianBlur(shadow_blur))
        base.alpha_composite(layer)

    d = ImageDraw.Draw(base)
    x, y = xy
    yy = y
    for line in lines:
        for dx, dy in offsets(weight):
            d.text((x + dx, yy + dy), line, font=font, fill=fill)
        yy += line_height(d, font, line) + line_gap


def render_preview(paths: list[Path], out: Path):
    imgs = [Image.open(p).convert("RGB") for p in paths]
    thumb_h = 720
    thumbs = [im.resize((round(im.width * thumb_h / im.height), thumb_h), Image.Resampling.LANCZOS) for im in imgs]
    gap = 30
    canvas = Image.new("RGB", (sum(t.width for t in thumbs) + gap * (len(thumbs) + 1), thumb_h + 40), (245, 245, 245))
    x = gap
    for t in thumbs:
        canvas.paste(t, (x, 20))
        x += t.width + gap
    canvas.save(out, quality=92, subsampling=0)


def video_is_hdr_or_hlg(path: str | None) -> bool:
    if not path:
        return False
    cp = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=color_transfer,color_primaries",
            "-of", "json", str(Path(path).expanduser()),
        ],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if cp.returncode != 0:
        return False
    try:
        streams = json.loads(cp.stdout or "{}").get("streams") or []
    except json.JSONDecodeError:
        return False
    if not streams:
        return False
    transfer = str(streams[0].get("color_transfer") or "").lower()
    primaries = str(streams[0].get("color_primaries") or "").lower()
    return transfer in {"arib-std-b67", "smpte2084"} or primaries == "bt2020"


def guard_frame_color(frame: Path, source_video: str | None, override: bool) -> None:
    if override or not video_is_hdr_or_hlg(source_video):
        return
    name = frame.name.lower()
    if "_raw" in name or name.endswith("raw.jpg") or name.endswith("raw.png"):
        raise SystemExit(
            "Refusing to render final covers from a raw frame of an HDR/HLG source. "
            "Extract an SDR-managed frame first, e.g. on macOS:\n"
            "  swift <skills_root>/va7-cover-tools/scripts/extract_avfoundation_frame.swift "
            "\"$SRC\" \"$TS\" work/selected_frame_sdr.jpg 3840\n"
            "Then pass that SDR frame to render_cover_set.py. Use --allow-raw-hdr-frame only for explicit diagnostics."
        )


def gatelib_sha(path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", required=True, help="approved still frame")
    ap.add_argument("--preflight", required=True, help="cover_gate.py preflight 产出的 cover_preflight.json；未通过则拒绝渲染")
    ap.add_argument("--layout", required=True, help="JSON layout config")
    ap.add_argument("--source-video", help="source video path; used to place output in <source folder>/cover")
    ap.add_argument("--out-dir", help="default: <source folder>/cover or <frame folder>/cover")
    ap.add_argument("--prefix", default="cover")
    ap.add_argument("--font-path")
    ap.add_argument("--allow-raw-hdr-frame", action="store_true", help="diagnostic override only")
    args = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "va7-pipeline" / "scripts"))
    import gatelib
    pre = gatelib.require_preflight(args.preflight, "cover")
    if pre["branch"] == "direct_image":
        if gatelib_sha(args.frame) != pre["base_sha256"]:
            gatelib.stop("direct_image 分支：--frame 必须就是用户给的原图（sha256 与预检不一致）")
        args.allow_raw_hdr_frame = True  # 直接给图不做色彩判断：原图就是底图

    frame = Path(args.frame).expanduser().resolve()
    guard_frame_color(frame, args.source_video, args.allow_raw_hdr_frame)
    cfg = json.loads(Path(args.layout).expanduser().read_text())
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import qa_cover_set
    bad = [c for c in qa_cover_set.check_explicit_crops(Path(args.layout), frame) if not c["ok"]]
    if bad:
        gatelib.stop("出图前的构图检查没过（crop/人物位置/文字几何），不渲染：" + json.dumps(bad, ensure_ascii=False))
    if args.out_dir:
        out_dir = Path(args.out_dir).expanduser().resolve()
    elif args.source_video:
        out_dir = Path(args.source_video).expanduser().resolve().parent / "cover"
    else:
        out_dir = frame.parent / "cover"
    out_dir.mkdir(parents=True, exist_ok=True)

    src = Image.open(frame).convert("RGB")
    specs = cfg.get("specs", DEFAULT_SPECS)
    outputs: list[Path] = []
    for name, spec in specs.items():
        size = spec.get("size", DEFAULT_SPECS.get(name, {}).get("size"))
        if not size:
            raise SystemExit(f"missing size for spec {name}")
        base = cover_crop(src, spec.get("crop"), size)
        for block in spec.get("text_blocks", cfg.get("text_blocks", [])):
            draw_block(base, resolve_text_block(block, name), args.font_path)
        out = out_dir / f"{args.prefix}_{name}.jpg"
        base.convert("RGB").save(out, quality=int(cfg.get("quality", 95)), subsampling=0)
        outputs.append(out)

    preview = out_dir / f"{args.prefix}_preview.jpg"
    render_preview(outputs, preview)
    for p in outputs + [preview]:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

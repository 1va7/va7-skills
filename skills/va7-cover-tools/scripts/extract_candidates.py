#!/usr/bin/env python3
"""
Extract labeled candidate stills for VA7 video covers.

Outputs:
  cover/candidates/candidate_*.jpg
  cover/candidates/contact_sheet.jpg

The script is intentionally deterministic: it samples timestamps, extracts
frames in parallel, and builds a labeled sheet for human selection.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SCRIPT_DIR = Path(__file__).resolve().parent



def _cached_font() -> str:
    """NotoSansSC-Bold from the va7 cover asset cache (cover_assets.py ensure)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cover_assets
    return str(cover_assets.FONT)

def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def duration_seconds(src: Path) -> float:
    cp = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(src)
    ])
    return float(cp.stdout.strip())


def video_color_metadata(src: Path) -> dict:
    cp = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=pix_fmt,color_space,color_transfer,color_primaries,width,height,r_frame_rate",
        "-of", "json", str(src),
    ])
    data = json.loads(cp.stdout or "{}")
    streams = data.get("streams") or []
    return streams[0] if streams else {}


def available_filters() -> set[str]:
    cp = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    text = (cp.stdout or "") + "\n" + (cp.stderr or "")
    names = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].isidentifier():
            names.add(parts[1])
    return names


def is_hdr_or_hlg(meta: dict) -> bool:
    transfer = str(meta.get("color_transfer") or "").lower()
    primaries = str(meta.get("color_primaries") or "").lower()
    return transfer in {"arib-std-b67", "smpte2084"} or primaries == "bt2020"


def can_use_avfoundation() -> bool:
    return (
        platform.system() == "Darwin"
        and shutil.which("swift") is not None
        and (SCRIPT_DIR / "extract_avfoundation_frame.swift").exists()
    )


def build_timestamps(duration: float, count: int, start_margin: float, end_margin: float) -> list[float]:
    usable_start = min(start_margin, max(0.0, duration * 0.1))
    usable_end = max(usable_start + 1.0, duration - min(end_margin, max(0.0, duration * 0.08)))
    if count <= 1:
        return [(usable_start + usable_end) / 2]
    step = (usable_end - usable_start) / (count + 1)
    return [usable_start + step * (i + 1) for i in range(count)]


def vf_for_mode(mode: str, width: int) -> str:
    scale = f"scale={width}:-1"
    if mode == "raw":
        return scale
    if mode == "zscale":
        return "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709:t=bt709:m=bt709:r=tv,format=yuv420p," + scale
    if mode == "colorspace":
        return "colorspace=all=bt709:iall=bt2020:format=yuv420p," + scale
    raise ValueError(f"unknown color mode: {mode}")


def extract_avfoundation(src: Path, out: Path, ts: float, width: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "swift", str(SCRIPT_DIR / "extract_avfoundation_frame.swift"),
            str(src), f"{ts:.4f}", str(out), str(width),
        ],
        check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def extract_one(
    src: Path,
    out: Path,
    ts: float,
    mode: str,
    width: int,
    *,
    source_is_hdr: bool,
    filters: set[str],
    allow_raw_fallback: bool,
) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    if mode == "raw":
        modes_to_try = ["raw"]
    elif mode == "sdr":
        modes_to_try = []
        if source_is_hdr and can_use_avfoundation():
            modes_to_try.append("avfoundation")
        if "zscale" in filters:
            modes_to_try.append("zscale")
        if not source_is_hdr and "colorspace" in filters:
            modes_to_try.append("colorspace")
        if not source_is_hdr or allow_raw_fallback:
            modes_to_try.append("raw")
        if not modes_to_try:
            raise RuntimeError(
                "HDR/HLG source requires a real SDR extraction path. "
                "Install/use AVFoundation on macOS or ffmpeg zscale; refusing raw HDR fallback."
            )
    else:
        raise ValueError(f"unknown mode: {mode}")
    last_error = None
    used_mode = mode
    for try_mode in modes_to_try:
        if try_mode == "avfoundation":
            cp = extract_avfoundation(src, out, ts, width)
        else:
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{ts:.3f}", "-i", str(src),
                "-frames:v", "1", "-vf", vf_for_mode(try_mode, width), str(out),
            ]
            cp = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if cp.returncode == 0:
            used_mode = try_mode if try_mode == mode else f"{mode}-{try_mode}"
            if source_is_hdr and mode == "sdr" and try_mode == "raw" and not allow_raw_fallback:
                raise RuntimeError("internal error: raw HDR fallback was not allowed")
            break
        last_error = cp.stderr
    else:
        raise RuntimeError(f"failed to extract {ts:.2f}s {mode}: {last_error}")
    return {"timestamp": ts, "file": str(out), "mode": used_mode}


def font(size: int):
    for p in [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        _cached_font(),
    ]:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def make_contact_sheet(items: list[dict], out: Path, cols: int = 4, thumb_w: int = 420) -> None:
    thumbs = []
    label_font = font(28)
    for idx, item in enumerate(items):
        im = Image.open(item["file"]).convert("RGB")
        thumb_h = round(im.height * thumb_w / im.width)
        im = im.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        tile = Image.new("RGB", (thumb_w, thumb_h + 48), (245, 245, 245))
        tile.paste(im, (0, 0))
        d = ImageDraw.Draw(tile)
        label = f"{idx+1:02d}  {item['timestamp']:.1f}s  {item['mode']}"
        d.rectangle((0, thumb_h, thumb_w, thumb_h + 48), fill=(20, 20, 20))
        d.text((12, thumb_h + 8), label, fill=(255, 255, 255), font=label_font)
        thumbs.append(tile)

    rows = math.ceil(len(thumbs) / cols)
    tile_w = thumb_w
    tile_h = max(t.height for t in thumbs)
    gap = 18
    sheet = Image.new("RGB", (cols * tile_w + (cols + 1) * gap, rows * tile_h + (rows + 1) * gap), (235, 235, 235))
    for i, tile in enumerate(thumbs):
        x = gap + (i % cols) * (tile_w + gap)
        y = gap + (i // cols) * (tile_h + gap)
        sheet.paste(tile, (x, y))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=92, subsampling=0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="source MOV/video path")
    ap.add_argument("--count", type=int, default=24)
    ap.add_argument("--start-margin", type=float, default=6.0)
    ap.add_argument("--end-margin", type=float, default=6.0)
    ap.add_argument("--width", type=int, default=960, help="candidate frame width")
    ap.add_argument("--mode", choices=["raw", "sdr", "both"], default="sdr")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out-dir", help="default: <source folder>/cover/candidates")
    ap.add_argument(
        "--allow-raw-fallback",
        action="store_true",
        help="allow raw extraction when SDR conversion is unavailable; never use this for final HDR covers",
    )
    args = ap.parse_args()

    src = Path(args.src).expanduser().resolve()
    if not src.exists():
        raise SystemExit(f"source not found: {src}")
    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else src.parent / "cover" / "candidates"
    if out_dir.exists():
        # Keep old user-approved artifacts out of the candidate folder only.
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dur = duration_seconds(src)
    color_meta = video_color_metadata(src)
    source_is_hdr = is_hdr_or_hlg(color_meta)
    filters = available_filters()
    timestamps = build_timestamps(dur, args.count, args.start_margin, args.end_margin)
    modes = ["raw", "sdr"] if args.mode == "both" else [args.mode]

    jobs = []
    for mode in modes:
        for i, ts in enumerate(timestamps, 1):
            out = out_dir / f"candidate_{i:02d}_{ts:07.2f}s_{mode}.jpg"
            jobs.append((src, out, ts, mode, args.width))

    items: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [
            ex.submit(
                extract_one,
                *job,
                source_is_hdr=source_is_hdr,
                filters=filters,
                allow_raw_fallback=args.allow_raw_fallback,
            )
            for job in jobs
        ]
        for fut in concurrent.futures.as_completed(futs):
            items.append(fut.result())

    items.sort(key=lambda x: (x["mode"], x["timestamp"]))
    manifest = {
        "source": str(src),
        "duration": dur,
        "color_metadata": color_meta,
        "source_is_hdr_or_hlg": source_is_hdr,
        "available_color_filters": sorted(filters & {"zscale", "colorspace", "tonemap", "scale", "scale_vt"}),
        "avfoundation_available": can_use_avfoundation(),
        "allow_raw_fallback": args.allow_raw_fallback,
        "requested_count": args.count,
        "candidate_count": len(items),
        "items": items,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    make_contact_sheet(items, out_dir / "contact_sheet.jpg")
    print(out_dir / "contact_sheet.jpg")
    print(out_dir / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

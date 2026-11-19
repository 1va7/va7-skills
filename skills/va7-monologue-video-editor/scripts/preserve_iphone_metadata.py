#!/usr/bin/env python3
"""Preserve iPhone/QuickTime metadata on edited MOV outputs.

This script prefers a Finder/Spotlight-friendly path on macOS:

1. If the source carries Apple metadata tracks and the target is a MOV, use
   AVFoundation passthrough remux to combine target A/V with source metadata tracks.
2. Overlay writable metadata fields from the source with ExifTool.
3. Validate both ExifTool-visible tags and, on macOS, Spotlight-imported fields.

For non-macOS hosts or simpler targets, it falls back to ExifTool-only copying.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SWIFT_HELPER = SCRIPT_DIR / "rewrap_mov_with_metadata.swift"


def run(
    cmd: list[str],
    *,
    timeout: int = 120,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"command failed: {' '.join(cmd)}")
    return proc


def ffprobe(path: Path) -> dict[str, Any]:
    proc = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        timeout=120,
        check=True,
    )
    return json.loads(proc.stdout)


def exiftool_tags(path: Path) -> dict[str, str]:
    proc = run(
        [
            "exiftool",
            "-j",
            "-CreateDate",
            "-CreationDate",
            "-GPSCoordinates",
            "-LocationAccuracyHorizontal",
            "-Make",
            "-Model",
            "-Software",
            "-LensModel",
            "-FocalLengthIn35mmFormat",
            "-CameraLensIrisfnumber",
            str(path),
        ],
        timeout=120,
        check=True,
    )
    data = json.loads(proc.stdout)
    return data[0] if data else {}


def mdimport_attrs(path: Path) -> dict[str, Any] | None:
    if sys.platform != "darwin" or not shutil.which("mdimport") or not shutil.which("plutil"):
        return None
    proc = run(["mdimport", "-d2", "-n", str(path)], timeout=120)
    if proc.returncode != 0:
        return None
    text = proc.stdout + proc.stderr
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    plist_text = text[start : end + 1]
    plutil = subprocess.run(
        ["plutil", "-convert", "json", "-o", "-", "--", "-"],
        input=plist_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if plutil.returncode != 0:
        return None
    return json.loads(plutil.stdout)


def source_has_metadata_tracks(probe: dict[str, Any]) -> bool:
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "data" and stream.get("codec_tag_string") == "mebx":
            return True
    return False


def source_supports_finder_metadata(attrs: dict[str, Any] | None) -> bool:
    if not attrs:
        return False
    codecs = attrs.get("kMDItemCodecs") or []
    lat = attrs.get("kMDItemLatitude")
    lon = attrs.get("kMDItemLongitude")
    enc = attrs.get("kMDItemEncodingApplications")
    return bool(lat or lon or enc or "Timed Metadata" in codecs)


def target_needs_finder_fix(source_attrs: dict[str, Any] | None, target_attrs: dict[str, Any] | None) -> bool:
    if not source_supports_finder_metadata(source_attrs):
        return False
    if not target_attrs:
        return True
    source_lat = source_attrs.get("kMDItemLatitude")
    target_lat = target_attrs.get("kMDItemLatitude")
    source_lon = source_attrs.get("kMDItemLongitude")
    target_lon = target_attrs.get("kMDItemLongitude")
    source_enc = source_attrs.get("kMDItemEncodingApplications")
    target_enc = target_attrs.get("kMDItemEncodingApplications")
    source_codecs = source_attrs.get("kMDItemCodecs") or []
    target_codecs = target_attrs.get("kMDItemCodecs") or []
    if source_lat and not target_lat:
        return True
    if source_lon and not target_lon:
        return True
    if source_enc and not target_enc:
        return True
    if "Timed Metadata" in source_codecs and "Timed Metadata" not in target_codecs:
        return True
    return False


def compile_swift_helper() -> Path:
    swiftc = shutil.which("swiftc")
    if not swiftc:
        raise RuntimeError("swiftc not found; cannot run AVFoundation metadata remux")
    binary = Path(tempfile.gettempdir()) / "va7_rewrap_mov_with_metadata"
    if not binary.exists() or binary.stat().st_mtime < SWIFT_HELPER.stat().st_mtime:
        run(
            [swiftc, "-parse-as-library", str(SWIFT_HELPER), "-o", str(binary)],
            timeout=600,
            check=True,
        )
    return binary


def avfoundation_rewrap(source: Path, target: Path, output: Path) -> None:
    binary = compile_swift_helper()
    run([str(binary), str(source), str(target), str(output)], timeout=3600, check=True)


def copy_writable_metadata(source: Path, target: Path) -> None:
    run(
        [
            "exiftool",
            "-overwrite_original",
            "-TagsFromFile",
            str(source),
            "-all:all",
            str(target),
        ],
        timeout=600,
        check=True,
    )


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def replace_file(src: Path, dst: Path) -> None:
    os.replace(src, dst)


def build_summary(path: Path) -> dict[str, Any]:
    probe = ffprobe(path)
    exif = exiftool_tags(path)
    spotlight = mdimport_attrs(path)
    video = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), {})
    return {
        "path": str(path),
        "ffprobe": {
            "duration": (probe.get("format") or {}).get("duration"),
            "video_codec": video.get("codec_name"),
            "audio_codec": audio.get("codec_name"),
            "width": video.get("width"),
            "height": video.get("height"),
            "color_primaries": video.get("color_primaries"),
            "color_transfer": video.get("color_transfer"),
            "color_space": video.get("color_space"),
            "format_tags": (probe.get("format") or {}).get("tags") or {},
        },
        "exiftool": exif,
        "spotlight": spotlight,
    }


def validate(source_summary: dict[str, Any], final_summary: dict[str, Any]) -> dict[str, Any]:
    source_exif = source_summary.get("exiftool") or {}
    final_exif = final_summary.get("exiftool") or {}
    source_spot = source_summary.get("spotlight") or {}
    final_spot = final_summary.get("spotlight") or {}
    checks: list[dict[str, Any]] = []

    for key in [
        "CreationDate",
        "GPSCoordinates",
        "LocationAccuracyHorizontal",
        "Make",
        "Model",
        "Software",
        "LensModel",
        "FocalLengthIn35mmFormat",
    ]:
        source_val = source_exif.get(key)
        if source_val is None:
            continue
        checks.append({
            "name": f"exiftool_{key}",
            "ok": final_exif.get(key) == source_val,
            "source": source_val,
            "final": final_exif.get(key),
        })

    if source_spot:
        for key in ["kMDItemLatitude", "kMDItemLongitude", "kMDItemEncodingApplications"]:
            source_val = source_spot.get(key)
            if source_val in (None, "(null)"):
                continue
            checks.append({
                "name": f"spotlight_{key}",
                "ok": final_spot.get(key) == source_val,
                "source": source_val,
                "final": final_spot.get(key),
            })
        source_codecs = source_spot.get("kMDItemCodecs") or []
        if "Timed Metadata" in source_codecs:
            final_codecs = final_spot.get("kMDItemCodecs") or []
            checks.append({
                "name": "spotlight_timed_metadata_codec",
                "ok": "Timed Metadata" in final_codecs,
                "source": source_codecs,
                "final": final_codecs,
            })

    return {
        "passed": all(check["ok"] for check in checks) if checks else True,
        "checks": checks,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-metadata-video", required=True, type=Path)
    parser.add_argument("--target-video", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--force-avfoundation", action="store_true")
    parser.add_argument("--prefer-finder-friendly", action="store_true", default=True)
    parser.add_argument("--no-prefer-finder-friendly", dest="prefer_finder_friendly", action="store_false")
    parser.add_argument("--backup-path", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source_metadata_video.expanduser().resolve()
    target = args.target_video.expanduser().resolve()

    if args.in_place and args.output:
        raise SystemExit("--in-place and --output are mutually exclusive")
    if not args.in_place and not args.output:
        raise SystemExit("provide --output or --in-place")

    output = target if args.in_place else args.output.expanduser().resolve()
    if output.exists() and not args.overwrite and not args.in_place:
        raise SystemExit(f"output exists: {output}")

    ensure_parent(output)
    source_probe = ffprobe(source)
    target_probe = ffprobe(target)
    source_spot = mdimport_attrs(source)
    target_spot = mdimport_attrs(target)

    source_meta_tracks = source_has_metadata_tracks(source_probe)
    should_use_avf = (
        sys.platform == "darwin"
        and output.suffix.lower() == ".mov"
        and source_meta_tracks
        and (
            args.force_avfoundation
            or (
                args.prefer_finder_friendly
                and target_needs_finder_fix(source_spot, target_spot)
            )
        )
    )

    with tempfile.TemporaryDirectory(prefix="va7_meta_") as tmpdir:
        temp_output = Path(tmpdir) / output.name
        work_target = temp_output

        if should_use_avf:
            avfoundation_rewrap(source, target, work_target)
        else:
            shutil.copy2(target, work_target)

        copy_writable_metadata(source, work_target)

        if args.backup_path and args.in_place:
            backup = args.backup_path.expanduser().resolve()
            ensure_parent(backup)
            shutil.copy2(target, backup)
        elif args.backup_path and not args.in_place:
            raise SystemExit("--backup-path is only valid with --in-place")

        if args.in_place:
            replace_file(work_target, output)
        else:
            shutil.copy2(work_target, output)

    source_summary = build_summary(source)
    final_summary = build_summary(output)
    validation = validate(source_summary, final_summary)
    report = {
        "source": source_summary,
        "target_before": {
            "path": str(target),
            "ffprobe": {
                "stream_count": len(target_probe.get("streams", [])),
                "format_tags": (target_probe.get("format") or {}).get("tags") or {},
            },
            "spotlight": target_spot,
        },
        "output": final_summary,
        "route": {
            "used_avfoundation_rewrap": should_use_avf,
            "source_has_metadata_tracks": source_meta_tracks,
            "prefer_finder_friendly": args.prefer_finder_friendly,
            "force_avfoundation": args.force_avfoundation,
        },
        "validation": validation,
    }

    text = json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if validation["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

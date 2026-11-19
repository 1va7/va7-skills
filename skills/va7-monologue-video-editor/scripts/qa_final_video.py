#!/usr/bin/env python3
"""Run deterministic QA checks for a final VA7 monologue render."""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
from pathlib import Path
from typing import Any


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=timeout)


def ffprobe(path: Path) -> dict[str, Any]:
    proc = run([
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ])
    if proc.returncode != 0:
        return {"error": proc.stderr.strip() or proc.stdout.strip()}
    return json.loads(proc.stdout)


def mdimport_attrs(path: Path) -> dict[str, Any] | None:
    if platform.system() != "Darwin":
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
    conv = subprocess.run(
        ["plutil", "-convert", "json", "-o", "-", "--", "-"],
        input=plist_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if conv.returncode != 0:
        return None
    try:
        return json.loads(conv.stdout)
    except json.JSONDecodeError:
        return None


def first_stream(probe: dict[str, Any], codec_type: str) -> dict[str, Any]:
    return next((s for s in probe.get("streams", []) if s.get("codec_type") == codec_type), {})


def frame_rate(value: str | None) -> float:
    if not value or "/" not in value:
        return 0.0
    a, b = value.split("/", 1)
    try:
        return float(a) / float(b)
    except (ValueError, ZeroDivisionError):
        return 0.0


def extract_frame(video: Path, timestamp: float, out: Path) -> dict[str, Any]:
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = run([
        "ffmpeg",
        "-hide_banner",
        "-v",
        "error",
        "-y",
        "-ss",
        f"{max(0.0, timestamp):.3f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        str(out),
    ])
    return {"path": str(out), "ok": proc.returncode == 0, "stderr": proc.stderr.strip()[-500:]}


def decode_check(video: Path) -> dict[str, Any]:
    proc = run([
        "ffmpeg",
        "-hide_banner",
        "-v",
        "error",
        "-i",
        str(video),
        "-map",
        "0:v:0",
        "-frames:v",
        "1",
        "-f",
        "null",
        "-",
    ])
    return {"ok": proc.returncode == 0, "stderr": proc.stderr.strip()[-1000:]}


def parse_loudnorm_json(text: str) -> dict[str, Any]:
    matches = re.findall(r"\{\s*\"input_i\".*?\}", text, flags=re.DOTALL)
    if not matches:
        return {"error": "Could not parse loudnorm JSON output."}
    try:
        return json.loads(matches[-1])
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid loudnorm JSON: {exc}"}


def measure_loudness(video: Path, target_i: float, target_tp: float, target_lra: float) -> dict[str, Any]:
    proc = run([
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        str(video),
        "-map",
        "0:a:0",
        "-af",
        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
        "-f",
        "null",
        "-",
    ], timeout=600)
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()[-1000:] or proc.stdout.strip()[-1000:]}
    return parse_loudnorm_json(proc.stderr + "\n" + proc.stdout)


def loudness_ok(metrics: dict[str, Any], min_i: float, max_i: float, max_tp: float) -> bool:
    try:
        integrated = float(metrics["input_i"])
        true_peak = float(metrics["input_tp"])
    except (KeyError, TypeError, ValueError):
        return False
    return min_i <= integrated <= max_i and true_peak <= max_tp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", required=True, type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--expected-start", type=float)
    parser.add_argument("--expected-end", type=float)
    parser.add_argument("--target-i", type=float, default=-16.0)
    parser.add_argument("--target-tp", type=float, default=-2.5)
    parser.add_argument("--target-lra", type=float, default=7.0)
    parser.add_argument("--pass-min-i", type=float, default=-18.0)
    parser.add_argument("--pass-max-i", type=float, default=-14.0)
    parser.add_argument("--pass-max-tp", type=float, default=-1.0)
    parser.add_argument("--skip-loudness", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=Path("work/qa/final"))
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    final = args.final.expanduser().resolve()
    source = args.source.expanduser().resolve() if args.source else None
    final_probe = ffprobe(final)
    source_probe = ffprobe(source) if source else {}
    final_mdimport = mdimport_attrs(final)
    source_mdimport = mdimport_attrs(source) if source else None
    fv = first_stream(final_probe, "video")
    fa = first_stream(final_probe, "audio")
    sv = first_stream(source_probe, "video") if source else {}
    final_duration = float((final_probe.get("format") or {}).get("duration") or 0.0)
    expected_duration = None
    if args.expected_start is not None and args.expected_end is not None:
        expected_duration = max(0.0, args.expected_end - args.expected_start)

    checks = []
    if source:
        checks.append({
            "name": "resolution_matches_source",
            "ok": (fv.get("width"), fv.get("height")) == (sv.get("width"), sv.get("height")),
            "final": [fv.get("width"), fv.get("height")],
            "source": [sv.get("width"), sv.get("height")],
        })
        checks.append({
            "name": "frame_rate_close_to_source",
            "ok": abs(frame_rate(fv.get("r_frame_rate")) - frame_rate(sv.get("r_frame_rate"))) < 0.2,
            "final": fv.get("r_frame_rate"),
            "source": sv.get("r_frame_rate"),
        })
        checks.append({
            "name": "hdr_color_tags_present",
            "ok": bool(fv.get("color_primaries") and fv.get("color_transfer") and fv.get("color_space")),
            "final": {
                "primaries": fv.get("color_primaries"),
                "transfer": fv.get("color_transfer"),
                "space": fv.get("color_space"),
            },
        })
        if source_mdimport:
            source_lat = source_mdimport.get("kMDItemLatitude")
            source_lon = source_mdimport.get("kMDItemLongitude")
            source_codecs = source_mdimport.get("kMDItemCodecs") or []
            source_enc = source_mdimport.get("kMDItemEncodingApplications")
            if source_lat is not None:
                checks.append({
                    "name": "finder_latitude_matches_source",
                    "ok": final_mdimport is not None and final_mdimport.get("kMDItemLatitude") == source_lat,
                    "final": None if final_mdimport is None else final_mdimport.get("kMDItemLatitude"),
                    "source": source_lat,
                })
            if source_lon is not None:
                checks.append({
                    "name": "finder_longitude_matches_source",
                    "ok": final_mdimport is not None and final_mdimport.get("kMDItemLongitude") == source_lon,
                    "final": None if final_mdimport is None else final_mdimport.get("kMDItemLongitude"),
                    "source": source_lon,
                })
            if source_enc not in (None, "(null)"):
                checks.append({
                    "name": "finder_encoding_applications_matches_source",
                    "ok": final_mdimport is not None and final_mdimport.get("kMDItemEncodingApplications") == source_enc,
                    "final": None if final_mdimport is None else final_mdimport.get("kMDItemEncodingApplications"),
                    "source": source_enc,
                })
            if "Timed Metadata" in source_codecs:
                final_codecs = [] if final_mdimport is None else (final_mdimport.get("kMDItemCodecs") or [])
                checks.append({
                    "name": "finder_reads_timed_metadata",
                    "ok": "Timed Metadata" in final_codecs,
                    "final": final_codecs,
                    "source": source_codecs,
                })
    checks.append({"name": "audio_present", "ok": bool(fa), "codec": fa.get("codec_name")})
    loudness = None
    if fa and not args.skip_loudness:
        loudness = measure_loudness(final, args.target_i, args.target_tp, args.target_lra)
        checks.append({
            "name": "audio_loudness_in_range",
            "ok": loudness_ok(loudness, args.pass_min_i, args.pass_max_i, args.pass_max_tp),
            "target": {
                "integrated_lufs": args.target_i,
                "true_peak_dbtp": args.target_tp,
                "lra": args.target_lra,
                "pass_min_integrated_lufs": args.pass_min_i,
                "pass_max_integrated_lufs": args.pass_max_i,
                "pass_max_true_peak_dbtp": args.pass_max_tp,
            },
            "measured": loudness,
        })
    if expected_duration is not None:
        checks.append({
            "name": "duration_near_expected",
            "ok": abs(final_duration - expected_duration) < 1.0,
            "final_duration": final_duration,
            "expected_duration": expected_duration,
        })
    checks.append({"name": "decode_first_frame", **decode_check(final)})

    frame_times = [0.4, max(0.5, final_duration / 2), max(0.5, final_duration - 1.2)]
    frames = [
        extract_frame(final, ts, args.out_dir / f"final_{label}.jpg")
        for ts, label in zip(frame_times, ["start", "mid", "end"])
    ]
    checks.append({"name": "qa_frames_extracted", "ok": all(f["ok"] for f in frames), "frames": frames})

    result = {
        "final": str(final),
        "source": str(source) if source else None,
        "final_duration": final_duration,
        "audio_loudness": loudness,
        "finder_spotlight": final_mdimport,
        "checks": checks,
        "passed": all(check.get("ok", False) for check in checks),
        "model_gate": "Inspect extracted start/mid/end frames, audition the opening, and deliver only when audio_loudness_in_range passes.",
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

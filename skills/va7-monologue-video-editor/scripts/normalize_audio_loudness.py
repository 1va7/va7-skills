#!/usr/bin/env python3
"""Measure and normalize VA7 monologue video loudness with fixed口播 defaults."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "va7.audio_loudness.v1"
TARGET_I = -16.0
TARGET_TP = -2.5
TARGET_LRA = 7.0
PASS_MIN_I = -18.0
PASS_MAX_I = -14.0
PASS_MAX_TP = -1.0
DEFAULT_AUDIO_CODEC = "aac"
DEFAULT_AUDIO_BITRATE = "192k"
PRESERVE_SCRIPT = Path(__file__).resolve().parent / "preserve_iphone_metadata.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Input video with audio.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output video. Defaults to '<input stem>_loudnorm<input suffix>' beside the input.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="JSON report. Defaults to '<input folder>/audio/<output stem>_loudness_report.json'.",
    )
    parser.add_argument("--measure-only", action="store_true", help="Only measure and report; do not write output video.")
    parser.add_argument("--target-i", type=float, default=TARGET_I)
    parser.add_argument("--target-tp", type=float, default=TARGET_TP)
    parser.add_argument("--target-lra", type=float, default=TARGET_LRA)
    parser.add_argument("--pass-min-i", type=float, default=PASS_MIN_I)
    parser.add_argument("--pass-max-i", type=float, default=PASS_MAX_I)
    parser.add_argument("--pass-max-tp", type=float, default=PASS_MAX_TP)
    parser.add_argument("--audio-codec", default=DEFAULT_AUDIO_CODEC)
    parser.add_argument("--audio-bitrate", default=DEFAULT_AUDIO_BITRATE)
    parser.add_argument(
        "--metadata-source-video",
        type=Path,
        help="Optional original iPhone MOV whose metadata should be re-applied after loudness normalization.",
    )
    parser.add_argument(
        "--preserve-finder-metadata",
        action="store_true",
        help="After loudness normalization, run preserve_iphone_metadata.py using --metadata-source-video.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing the output file.")
    return parser.parse_args()


def run(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=timeout)


def parse_loudnorm_json(text: str) -> dict[str, Any]:
    matches = re.findall(r"\{\s*\"input_i\".*?\}", text, flags=re.DOTALL)
    if not matches:
        raise SystemExit("Could not parse ffmpeg loudnorm JSON output.")
    try:
        return json.loads(matches[-1])
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid loudnorm JSON: {exc}") from None


def ffprobe_audio(input_path: Path) -> dict[str, Any]:
    proc = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=index,codec_name,channels,channel_layout,sample_rate,bit_rate",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(input_path),
        ],
        timeout=60,
    )
    if proc.returncode != 0:
        return {"error": proc.stderr.strip() or proc.stdout.strip()}
    return json.loads(proc.stdout)


def measure(input_path: Path, target_i: float, target_tp: float, target_lra: float) -> dict[str, Any]:
    proc = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(input_path),
            "-map",
            "0:a:0",
            "-af",
            f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
            "-f",
            "null",
            "-",
        ],
        timeout=None,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip()[-2000:] or proc.stdout.strip()[-2000:])
    return parse_loudnorm_json(proc.stderr + "\n" + proc.stdout)


def to_float(metrics: dict[str, Any], key: str) -> float:
    try:
        return float(metrics[key])
    except (KeyError, TypeError, ValueError):
        raise SystemExit(f"Missing numeric loudnorm metric: {key}") from None


def passed(metrics: dict[str, Any], min_i: float, max_i: float, max_tp: float) -> bool:
    integrated = to_float(metrics, "input_i")
    true_peak = to_float(metrics, "input_tp")
    return min_i <= integrated <= max_i and true_peak <= max_tp


def two_pass_filter(first_pass: dict[str, Any], target_i: float, target_tp: float, target_lra: float) -> str:
    return (
        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:"
        f"measured_I={to_float(first_pass, 'input_i')}:"
        f"measured_TP={to_float(first_pass, 'input_tp')}:"
        f"measured_LRA={to_float(first_pass, 'input_lra')}:"
        f"measured_thresh={to_float(first_pass, 'input_thresh')}:"
        f"offset={to_float(first_pass, 'target_offset')}:"
        "linear=true:print_format=json"
    )


def normalize(input_path: Path, output_path: Path, filter_expr: str, args: argparse.Namespace) -> dict[str, Any]:
    if output_path.exists() and not args.overwrite:
        raise SystemExit(f"Output already exists; pass --overwrite to replace: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    proc = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y" if args.overwrite else "-n",
            "-i",
            str(input_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c:v",
            "copy",
            "-af",
            filter_expr,
            "-c:a",
            args.audio_codec,
            "-b:a",
            args.audio_bitrate,
            "-ar",
            "48000",
            "-map_metadata",
            "0",
            "-movflags",
            "use_metadata_tags",
            str(output_path),
        ],
        timeout=None,
    )
    result = {
        "returncode": proc.returncode,
        "stderr_tail": proc.stderr.strip()[-2000:],
        "stdout_tail": proc.stdout.strip()[-1000:],
    }
    if proc.returncode != 0:
        raise SystemExit(json.dumps(result, ensure_ascii=False, indent=2))
    result["loudnorm"] = parse_loudnorm_json(proc.stderr + "\n" + proc.stdout)
    return result


def default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_loudnorm{input_path.suffix}")


def default_report_path(input_path: Path, output_path: Path) -> Path:
    return input_path.parent / "audio" / f"{output_path.stem}_loudness_report.json"


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def preserve_metadata(metadata_source: Path, output_path: Path) -> dict[str, Any]:
    backup_path = output_path.with_name(f"{output_path.stem}.backup_before_metadata_fix{output_path.suffix}")
    proc = run(
        [
            "python3",
            str(PRESERVE_SCRIPT),
            "--source-metadata-video",
            str(metadata_source),
            "--target-video",
            str(output_path),
            "--in-place",
            "--backup-path",
            str(backup_path),
            "--pretty",
        ],
        timeout=None,
    )
    payload = None
    text = (proc.stdout or "").strip()
    if text:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"raw_stdout": text}
    return {
        "returncode": proc.returncode,
        "backup_path": str(backup_path),
        "report": payload,
        "stderr_tail": proc.stderr.strip()[-2000:],
    }


def main() -> int:
    args = parse_args()
    input_path = args.input.expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"Missing input video: {input_path}")

    output_path = (args.output.expanduser().resolve() if args.output else default_output_path(input_path))
    report_path = args.report.expanduser().resolve() if args.report else default_report_path(input_path, output_path)

    before = measure(input_path, args.target_i, args.target_tp, args.target_lra)
    normalization: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    metadata_preservation: dict[str, Any] | None = None

    if not args.measure_only:
        filter_expr = two_pass_filter(before, args.target_i, args.target_tp, args.target_lra)
        normalization = normalize(input_path, output_path, filter_expr, args)
        if args.preserve_finder_metadata:
            if not args.metadata_source_video:
                raise SystemExit("--preserve-finder-metadata requires --metadata-source-video")
            metadata_source = args.metadata_source_video.expanduser().resolve()
            if not metadata_source.exists():
                raise SystemExit(f"Missing metadata source video: {metadata_source}")
            if not PRESERVE_SCRIPT.exists():
                raise SystemExit(f"Missing metadata preservation script: {PRESERVE_SCRIPT}")
            metadata_preservation = preserve_metadata(metadata_source, output_path)
            if metadata_preservation["returncode"] != 0:
                raise SystemExit(json.dumps(metadata_preservation, ensure_ascii=False, indent=2))
        after = measure(output_path, args.target_i, args.target_tp, args.target_lra)

    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input": str(input_path),
        "output": None if args.measure_only else str(output_path),
        "target": {
            "integrated_lufs": args.target_i,
            "true_peak_dbtp": args.target_tp,
            "lra": args.target_lra,
            "pass_min_integrated_lufs": args.pass_min_i,
            "pass_max_integrated_lufs": args.pass_max_i,
            "pass_max_true_peak_dbtp": args.pass_max_tp,
        },
        "audio_probe": ffprobe_audio(input_path),
        "before": before,
        "normalization": normalization,
        "metadata_preservation": metadata_preservation,
        "after": after,
        "passed_before": passed(before, args.pass_min_i, args.pass_max_i, args.pass_max_tp),
        "passed_after": None if after is None else passed(after, args.pass_min_i, args.pass_max_i, args.pass_max_tp),
        "model_gate": "For VA7口播, deliver only when after.input_i is around -16 LUFS and after.input_tp is below the true-peak ceiling.",
    }
    write_json(report_path, report)

    summary = {
        "report": str(report_path),
        "input_i_before": before.get("input_i"),
        "input_tp_before": before.get("input_tp"),
        "output": None if args.measure_only else str(output_path),
        "input_i_after": None if after is None else after.get("input_i"),
        "input_tp_after": None if after is None else after.get("input_tp"),
        "passed_after": report["passed_after"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if (args.measure_only or report["passed_after"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())

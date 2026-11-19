#!/usr/bin/env python3
"""Suggest conservative head/tail trim points for a one-take monologue."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


def run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=timeout)


def ffprobe_duration(src: Path) -> float:
    proc = run([
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(src),
    ])
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip())
    return float(proc.stdout.strip())


def load_segments(path: Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = data.get("segments") if isinstance(data, dict) else None
    if not isinstance(segments, list):
        raise SystemExit(f"Unsupported ASR JSON shape: {path}")
    return [seg for seg in segments if isinstance(seg, dict)]


def silence_scan(src: Path, seconds: float) -> list[dict[str, float]]:
    proc = run([
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-vn",
        "-i",
        str(src),
        "-map",
        "0:a:0",
        "-af",
        "silencedetect=noise=-35dB:d=0.08",
        "-t",
        f"{seconds:.3f}",
        "-f",
        "null",
        "-",
    ])
    text = proc.stderr + proc.stdout
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", text)]
    ends = [
        (float(end), float(dur))
        for end, dur in re.findall(r"silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)", text)
    ]
    items: list[dict[str, float]] = []
    for i, start in enumerate(starts):
        item = {"start": start}
        if i < len(ends):
            item["end"] = ends[i][0]
            item["duration"] = ends[i][1]
        items.append(item)
    return items


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument("--asr-json", type=Path)
    parser.add_argument("--head-scan", type=float, default=12.0)
    parser.add_argument("--tail-pad", type=float, default=0.65)
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    src = args.src.expanduser().resolve()
    duration = ffprobe_duration(src)
    segments = load_segments(args.asr_json)
    first_seg = segments[0] if segments else {}
    last_seg = segments[-1] if segments else {}
    first_asr_start = float(first_seg.get("start", 0.0) or 0.0)
    last_asr_end = float(last_seg.get("end", duration) or duration)
    silences = silence_scan(src, args.head_scan)

    initial_silence_end = None
    for item in silences:
        if abs(item.get("start", 999.0)) < 0.05 and "end" in item:
            initial_silence_end = float(item["end"])
            break

    if initial_silence_end is not None:
        start_offset = max(0.0, initial_silence_end - 0.04)
        start_reason = "initial_silence_end_minus_40ms"
    else:
        start_offset = max(0.0, first_asr_start - 0.15)
        start_reason = "first_asr_start_minus_150ms"

    end_time = min(duration, last_asr_end + args.tail_pad)
    if duration - end_time < 0.25:
        end_time = duration

    result = {
        "source": str(src),
        "duration": duration,
        "asr_json": str(args.asr_json) if args.asr_json else None,
        "first_asr_segment": first_seg,
        "last_asr_segment": last_seg,
        "head_silences": silences,
        "recommended": {
            "start_offset": round(start_offset, 3),
            "end_time": round(end_time, 3),
            "duration": round(max(0.0, end_time - start_offset), 3),
            "start_reason": start_reason,
            "end_reason": "last_asr_end_plus_tail_pad",
        },
        "model_gate": "Audition a short audio/video sample at start_offset and near end_time before final render.",
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

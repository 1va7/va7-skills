#!/usr/bin/env python3
"""Archive VA7 timestamped ASR/subtitle artifacts in a fixed source-folder format."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "va7.subtitle_archive.v1"
TSV_COLUMNS = ["index", "start", "end", "start_seconds", "end_seconds", "text"]


@dataclass
class Event:
    start: float
    end: float
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-video", required=True, type=Path)
    parser.add_argument("--asr-json", required=True, type=Path)
    parser.add_argument(
        "--asr-label",
        required=True,
        help="Stable backend/model label used in the ASR JSON filename, e.g. mlx_small or doubao.",
    )
    parser.add_argument("--final-video", action="append", default=[], type=Path)
    parser.add_argument("--edited-srt", type=Path, help="Edited-video-relative subtitle file.")
    parser.add_argument("--edited-ass", type=Path, help="Edited-video-relative ASS file to archive.")
    parser.add_argument("--edited-quality", choices=["corrected", "rough_asr"], help="Quality label for edited-relative output.")
    parser.add_argument("--edited-time-axis", choices=["confirmed", "estimated"], default="confirmed")
    parser.add_argument("--start-offset", type=float, help="Seconds trimmed from the source head.")
    parser.add_argument("--end-time-source", type=float, help="Source-relative end time retained in the final edit.")
    parser.add_argument(
        "--estimate-start-offset-from-duration-delta",
        action="store_true",
        help="Estimate head trim as source duration minus first final-video duration. Marks edited time axis estimated.",
    )
    parser.add_argument("--source-duration", type=float)
    parser.add_argument("--edited-duration", type=float)
    parser.add_argument("--reference-script", type=Path)
    parser.add_argument("--topic-record", type=Path)
    parser.add_argument("--note", action="append", default=[])
    return parser.parse_args()


def validate_label(label: str, name: str) -> str:
    normalized = label.strip().replace(" ", "_")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", normalized):
        raise SystemExit(f"{name} must contain only letters, numbers, underscore, or hyphen: {label!r}")
    return normalized


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Missing file: {path}") from None
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON {path}: {exc}") from None


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ffprobe_duration(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    text = proc.stdout.strip()
    try:
        return float(text)
    except ValueError:
        return None


def as_float(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise SystemExit(f"ASR segment missing numeric {field}: {value!r}") from None


def clean_text(text: str) -> str:
    text = text.replace("\\N", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def one_line(text: str) -> str:
    return re.sub(r"\s+", " ", clean_text(text)).strip()


def events_from_asr(
    data: Any,
    *,
    start_offset: float = 0.0,
    end_time_source: float | None = None,
) -> list[Event]:
    if not isinstance(data, dict) or not isinstance(data.get("segments"), list):
        raise SystemExit("ASR JSON must be an object with a segments array.")

    events: list[Event] = []
    for seg in data["segments"]:
        if not isinstance(seg, dict):
            continue
        source_start = as_float(seg.get("start"), "start")
        source_end = as_float(seg.get("end"), "end")
        if end_time_source is not None:
            source_end = min(source_end, end_time_source)
        start = max(0.0, source_start - start_offset)
        end = source_end - start_offset
        if end <= 0:
            continue
        if end_time_source is not None and source_start >= end_time_source:
            continue
        end = max(end, start + 0.2)
        text = clean_text(str(seg.get("text", "")))
        if not text:
            continue
        events.append(Event(start=start, end=end, text=text))
    return events


def srt_time(seconds: float) -> str:
    ms_total = int(round(max(0.0, seconds) * 1000))
    hours, rem = divmod(ms_total, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def compact_time(seconds: float) -> str:
    ms_total = int(round(max(0.0, seconds) * 1000))
    hours, rem = divmod(ms_total, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"


def parse_srt_time(text: str) -> float:
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", text.strip())
    if not match:
        raise ValueError(text)
    hours, minutes, seconds, millis = [int(part) for part in match.groups()]
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def parse_srt(path: Path) -> list[Event]:
    text = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n\s*\n", text.strip())
    events: list[Event] = []
    time_re = re.compile(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})")
    for block in blocks:
        lines = [line.rstrip("\r") for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        time_idx = next((idx for idx, line in enumerate(lines) if "-->" in line), None)
        if time_idx is None:
            continue
        match = time_re.search(lines[time_idx])
        if not match:
            raise SystemExit(f"Invalid SRT time line in {path}: {lines[time_idx]!r}")
        subtitle_text = clean_text("\n".join(lines[time_idx + 1 :]))
        if not subtitle_text:
            continue
        events.append(Event(parse_srt_time(match.group(1)), parse_srt_time(match.group(2)), subtitle_text))
    if not events:
        raise SystemExit(f"No subtitle events parsed from {path}")
    return events


def write_srt(path: Path, events: list[Event]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for idx, event in enumerate(events, 1):
        blocks.append(f"{idx}\n{srt_time(event.start)} --> {srt_time(event.end)}\n{clean_text(event.text)}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")


def write_tsv(path: Path, events: list[Event]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(TSV_COLUMNS)
        for idx, event in enumerate(events, 1):
            writer.writerow(
                [
                    idx,
                    compact_time(event.start),
                    compact_time(event.end),
                    f"{event.start:.3f}",
                    f"{event.end:.3f}",
                    one_line(event.text),
                ]
            )


def write_txt(path: Path, events: list[Event]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"[{compact_time(event.start)} - {compact_time(event.end)}] {one_line(event.text)}" for event in events]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_text_file(src: Path, dst: Path) -> None:
    if not src.exists():
        raise SystemExit(f"Missing file: {src}")
    if src.resolve() == dst.resolve():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def output_set(
    archive_dir: Path,
    stem: str,
    suffix: str,
    events: list[Event],
    *,
    include_srt: bool = True,
) -> dict[str, str]:
    files: dict[str, str] = {}
    base = archive_dir / f"{stem}_{suffix}"
    if include_srt:
        write_srt(base.with_suffix(".srt"), events)
        files["srt"] = base.with_suffix(".srt").name
    write_tsv(base.with_suffix(".tsv"), events)
    write_txt(base.with_suffix(".txt"), events)
    files["tsv"] = base.with_suffix(".tsv").name
    files["txt"] = base.with_suffix(".txt").name
    return files


def write_readme(path: Path, stem: str, transcripts: dict[str, Any], preferred_key: str | None) -> None:
    lines = [
        f"# {stem} 字幕留档",
        "",
        "本目录由 `archive_subtitle_artifacts.py` 生成。不要手工改文件名或 TSV 字段；需要重建时重新运行脚本。",
        "",
        "固定字段：",
        "",
        "- `*.tsv`: `index`, `start`, `end`, `start_seconds`, `end_seconds`, `text`",
        "- `*.srt`: 剪辑/字幕工具使用",
        "- `*.txt`: 人工快速浏览",
        "- `*_subtitle_archive_manifest.json`: 机器读取的归档清单",
        "",
        "时间轴：",
        "",
    ]
    for key, meta in transcripts.items():
        lines.append(f"- `{key}`: {meta['description']}")
    if preferred_key:
        preferred = transcripts[preferred_key]["files"].get("tsv")
        lines.extend(["", f"章节生成优先使用：`{preferred}`"])
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def existing_auxiliary_files(archive_dir: Path, stem: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for suffix, key in [
        ("reference_script.txt", "reference_script"),
        ("topic_record.json", "topic_record"),
    ]:
        path = archive_dir / f"{stem}_{suffix}"
        if path.exists():
            result[key] = path.name
    return result


def main() -> int:
    args = parse_args()
    source_video = args.source_video.expanduser().resolve()
    if not source_video.exists():
        raise SystemExit(f"Missing source video: {source_video}")

    asr_label = validate_label(args.asr_label, "--asr-label")
    stem = source_video.stem
    archive_dir = source_video.parent / "subtitles"
    archive_dir.mkdir(parents=True, exist_ok=True)

    asr_data = load_json(args.asr_json)
    source_duration = args.source_duration or ffprobe_duration(source_video)
    final_videos = [path.expanduser().resolve() for path in args.final_video]
    edited_duration = args.edited_duration
    if edited_duration is None and final_videos:
        edited_duration = ffprobe_duration(final_videos[0])

    start_offset = args.start_offset
    end_time_source = args.end_time_source
    edited_time_axis = args.edited_time_axis
    if args.estimate_start_offset_from_duration_delta:
        if source_duration is None or edited_duration is None:
            raise SystemExit("Cannot estimate offset without source and edited durations.")
        start_offset = round(max(0.0, source_duration - edited_duration), 3)
        end_time_source = source_duration
        edited_time_axis = "estimated"

    asr_archive = archive_dir / f"{stem}_asr_source_relative_{asr_label}.json"
    write_json(asr_archive, asr_data)

    transcripts: dict[str, Any] = {}
    source_events = events_from_asr(asr_data)
    source_files = output_set(archive_dir, stem, "source_relative_rough_asr", source_events)
    transcripts["source_relative_rough_asr"] = {
        "time_axis": "source_relative",
        "quality": "rough_asr",
        "description": "时间轴对应原始素材，文本来自粗 ASR，适合回源核对。",
        "event_count": len(source_events),
        "files": source_files,
    }

    if args.edited_srt or start_offset is not None:
        edited_quality = args.edited_quality or ("corrected" if args.edited_srt else "rough_asr")
        suffix = f"edited_relative_{edited_quality}"
        if edited_time_axis == "estimated":
            suffix += "_estimated"
        if args.edited_srt:
            edited_events = parse_srt(args.edited_srt)
        else:
            edited_events = events_from_asr(
                asr_data,
                start_offset=start_offset or 0.0,
                end_time_source=end_time_source,
            )
        edited_files = output_set(archive_dir, stem, suffix, edited_events)
        if args.edited_ass:
            ass_dst = archive_dir / f"{stem}_{suffix}.ass"
            copy_text_file(args.edited_ass, ass_dst)
            edited_files["ass"] = ass_dst.name
        key = suffix
        quality_text = "已校正字幕" if edited_quality == "corrected" else "粗 ASR 字幕"
        confidence_text = "已确认 trim" if edited_time_axis == "confirmed" else "按时长/offset 推算，正式章节前需复核"
        transcripts[key] = {
            "time_axis": "edited_relative",
            "time_axis_confidence": edited_time_axis,
            "quality": edited_quality,
            "description": f"时间轴对应剪辑后成片，{quality_text}，{confidence_text}。",
            "event_count": len(edited_events),
            "files": edited_files,
        }

    if args.reference_script:
        ref_dst = archive_dir / f"{stem}_reference_script.txt"
        copy_text_file(args.reference_script, ref_dst)
    if args.topic_record:
        topic_dst = archive_dir / f"{stem}_topic_record.json"
        copy_text_file(args.topic_record, topic_dst)

    preferred_key = None
    edited_keys = [key for key in transcripts if key.startswith("edited_relative")]
    if edited_keys:
        preferred_key = sorted(edited_keys, key=lambda key: ("estimated" in key, "rough_asr" in key))[0]
    else:
        preferred_key = "source_relative_rough_asr"

    manifest_path = archive_dir / f"{stem}_subtitle_archive_manifest.json"
    readme_path = archive_dir / "README.md"
    write_readme(readme_path, stem, transcripts, preferred_key)

    auxiliary = existing_auxiliary_files(archive_dir, stem)
    managed_files = {asr_archive.name, manifest_path.name, readme_path.name}
    for transcript in transcripts.values():
        managed_files.update(transcript["files"].values())
    managed_files.update(auxiliary.values())

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "video_id": stem,
        "source_video": str(source_video),
        "final_videos": [str(path) for path in final_videos],
        "archive_dir": str(archive_dir),
        "asr": {
            "label": asr_label,
            "source_file": str(args.asr_json.expanduser().resolve()),
            "archive_file": asr_archive.name,
            "language": asr_data.get("language") if isinstance(asr_data, dict) else None,
            "segment_count": len(asr_data.get("segments", [])) if isinstance(asr_data, dict) else None,
        },
        "durations": {
            "source_seconds": round(source_duration, 3) if source_duration is not None else None,
            "edited_seconds": round(edited_duration, 3) if edited_duration is not None else None,
        },
        "trim": {
            "start_offset_seconds": round(start_offset, 3) if start_offset is not None else None,
            "end_time_seconds_source": round(end_time_source, 3) if end_time_source is not None else None,
            "time_axis_confidence": edited_time_axis if edited_keys else None,
            "estimated_from_duration_delta": bool(args.estimate_start_offset_from_duration_delta),
        },
        "transcripts": transcripts,
        "chapter_generation": {
            "preferred_transcript": preferred_key,
            "preferred_tsv": transcripts[preferred_key]["files"].get("tsv") if preferred_key else None,
            "tsv_columns": TSV_COLUMNS,
        },
        "auxiliary_files": auxiliary,
        "notes": args.note,
        "files": sorted(managed_files),
    }
    write_json(manifest_path, manifest)

    summary = {
        "archive_dir": str(archive_dir),
        "manifest": str(manifest_path),
        "preferred_tsv": manifest["chapter_generation"]["preferred_tsv"],
        "files": sorted(managed_files),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

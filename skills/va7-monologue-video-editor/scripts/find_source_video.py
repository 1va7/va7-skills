#!/usr/bin/env python3
"""List and rank candidate source videos for a VA7 monologue folder/query."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}


def norm(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text.lower(), flags=re.UNICODE)


def run_ffprobe(path: Path) -> dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,r_frame_rate,pix_fmt,color_space,color_transfer,color_primaries",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=60)
    if proc.returncode != 0:
        return {"error": proc.stderr.strip() or proc.stdout.strip()}
    return json.loads(proc.stdout)


def video_summary(path: Path) -> dict[str, Any]:
    stat = path.stat()
    probe = run_ffprobe(path)
    streams = probe.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    fmt = probe.get("format") or {}
    return {
        "path": str(path),
        "parent": str(path.parent),
        "size_bytes": stat.st_size,
        "mtime": stat.st_mtime,
        "duration": float(fmt.get("duration") or 0),
        "bit_rate": fmt.get("bit_rate"),
        "video": {
            "codec": video.get("codec_name"),
            "size": f"{video.get('width')}x{video.get('height')}" if video.get("width") else None,
            "frame_rate": video.get("r_frame_rate"),
            "pix_fmt": video.get("pix_fmt"),
            "color": {
                "primaries": video.get("color_primaries"),
                "transfer": video.get("color_transfer"),
                "space": video.get("color_space"),
            },
        },
        "probe_error": probe.get("error"),
    }


def iter_videos(folder: Path, max_depth: int) -> list[Path]:
    if folder.is_file() and folder.suffix.lower() in VIDEO_EXTS:
        return [folder.resolve()]
    if not folder.exists():
        return []
    base_depth = len(folder.resolve().parts)
    paths = []
    for path in folder.resolve().rglob("*"):
        if len(path.parts) - base_depth > max_depth:
            continue
        if path.is_file() and path.suffix.lower() in VIDEO_EXTS:
            paths.append(path)
    return paths


def discover_from_query(roots: list[Path], query: str, max_depth: int) -> list[Path]:
    q = norm(query)
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            try:
                rel_depth = len(path.relative_to(root).parts)
            except ValueError:
                rel_depth = 0
            if rel_depth > max_depth:
                continue
            if q and q not in norm(path.name) and q not in norm(str(path.parent.name)):
                continue
            candidates = iter_videos(path, max_depth=2) if path.is_dir() else iter_videos(path, max_depth=0)
            for item in candidates:
                if item not in seen:
                    seen.add(item)
                    found.append(item)
    return found


def score_candidate(summary: dict[str, Any], hints: list[str]) -> tuple[float, list[str]]:
    text = norm(Path(summary["path"]).name + " " + Path(summary["parent"]).name)
    score = 0.0
    reasons: list[str] = []
    for hint in hints:
        h = norm(hint)
        if len(h) >= 2 and h in text:
            score += 20
            reasons.append(f"hint:{hint}")
    duration = float(summary.get("duration") or 0)
    if 30 <= duration <= 1800:
        score += 10
        reasons.append("monologue_duration_range")
    size = int(summary.get("size_bytes") or 0)
    if size > 100_000_000:
        score += 8
        reasons.append("large_video_file")
    if str(summary.get("video", {}).get("size") or "").startswith("3840x2160"):
        score += 5
        reasons.append("4k_source")
    return score, reasons


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, help="Known source folder or file.")
    parser.add_argument("--query", help="Folder/title query, e.g. '0612 Token消耗'.")
    parser.add_argument("--root", action="append", type=Path, default=[], help="Search root for --query. Can repeat.")
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = args.root or [Path.home() / "Desktop"]
    paths: list[Path] = []
    hints: list[str] = []
    if args.folder:
        paths.extend(iter_videos(args.folder.expanduser(), args.max_depth))
        hints.append(args.folder.name)
    if args.query:
        paths.extend(discover_from_query([r.expanduser() for r in roots], args.query, args.max_depth))
        hints.append(args.query)

    unique = []
    seen: set[Path] = set()
    for path in paths:
        rp = path.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(rp)

    summaries = []
    for path in unique:
        summary = video_summary(path)
        score, reasons = score_candidate(summary, hints)
        summary["score"] = score
        summary["reasons"] = reasons
        summaries.append(summary)
    summaries.sort(key=lambda x: (x["score"], x["size_bytes"]), reverse=True)

    ambiguous = len(summaries) != 1
    if len(summaries) >= 2 and summaries[0]["score"] - summaries[1]["score"] >= 15:
        ambiguous = False
    result = {
        "query": args.query,
        "folder": str(args.folder) if args.folder else None,
        "candidate_count": len(summaries),
        "ambiguous": ambiguous,
        "selected": summaries[0] if summaries and not ambiguous else None,
        "candidates": summaries,
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

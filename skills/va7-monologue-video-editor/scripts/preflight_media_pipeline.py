#!/usr/bin/env python3
"""Preflight VA7 monologue video editing environment and media routes."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path


def run(cmd: list[str], timeout: int = 20) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} not found"
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "timeout"


def which_many(names: list[str]) -> dict[str, str | None]:
    return {name: shutil.which(name) for name in names}


def find_recent_tool_paths(roots: Iterable[Path], names: list[str], max_hits: int = 20) -> dict[str, list[str]]:
    hits = {name: [] for name in names}
    ignored_parts = {
        ".git",
        "node_modules",
        "Library",
        ".codex",
        "__pycache__",
        ".cache",
    }
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for name in names:
            if len(hits[name]) >= max_hits:
                continue
            try:
                for path in root.glob(f"**/{name}"):
                    if len(hits[name]) >= max_hits:
                        break
                    if ignored_parts.intersection(path.parts):
                        continue
                    if path.is_file() or path.is_symlink():
                        hits[name].append(str(path))
            except OSError:
                continue
    return {k: v for k, v in hits.items() if v}


def find_workflow_files(roots: Iterable[Path], patterns: list[str], max_hits: int = 20) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    ignored_parts = {
        ".git",
        "node_modules",
        "Library",
        ".codex",
        "__pycache__",
        ".cache",
        ".uv-cache",
        "site-packages",
        "build",
    }
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for pattern in patterns:
            try:
                for path in root.glob(f"**/{pattern}"):
                    if len(found) >= max_hits:
                        return found
                    if ignored_parts.intersection(path.parts):
                        continue
                    if path.is_file():
                        item = str(path)
                        if item not in seen:
                            seen.add(item)
                            found.append(item)
            except OSError:
                continue
    return found


def ffmpeg_lines(args: list[str]) -> str:
    code, out, err = run(["ffmpeg", "-hide_banner", *args], timeout=30)
    return out + err if code in (0, 1) else err


def probe_source(src: Path) -> dict:
    code, out, err = run(
        [
            "ffprobe",
            "-hide_banner",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate:format_tags:"
            "stream=index,codec_type,codec_name,codec_tag_string,width,height,r_frame_rate,pix_fmt,"
            "color_space,color_transfer,color_primaries,bit_rate,sample_rate,channels",
            "-of",
            "json",
            str(src),
        ],
        timeout=60,
    )
    if code != 0:
        return {"error": err.strip() or out.strip()}
    return json.loads(out)


def mdimport_attrs(src: Path) -> dict | None:
    if platform.system() != "Darwin" or not shutil.which("mdimport") or not shutil.which("plutil"):
        return None
    proc = subprocess.run(
        ["mdimport", "-d2", "-n", str(src)],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
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
        timeout=60,
        check=False,
    )
    if conv.returncode != 0:
        return None
    try:
        return json.loads(conv.stdout)
    except json.JSONDecodeError:
        return None


def host_profile() -> dict:
    info = {
        "system": platform.system(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "release": platform.release(),
    }
    if info["system"] == "Darwin":
        code, out, _ = run(["sysctl", "-n", "machdep.cpu.brand_string"])
        info["cpu_brand"] = out.strip() if code == 0 else ""
        info["apple_silicon"] = info["machine"] in {"arm64", "aarch64"}
    else:
        info["apple_silicon"] = False
    return info


def classify_encoder(encoders_text: str, host: dict) -> dict:
    encoders = {
        "hevc_videotoolbox": "hevc_videotoolbox" in encoders_text,
        "hevc_nvenc": "hevc_nvenc" in encoders_text,
        "hevc_qsv": "hevc_qsv" in encoders_text,
        "hevc_vaapi": "hevc_vaapi" in encoders_text,
        "libx265": "libx265" in encoders_text,
    }
    if host["system"] == "Darwin" and encoders["hevc_videotoolbox"]:
        recommendation = "hevc_videotoolbox"
    elif encoders["hevc_nvenc"]:
        recommendation = "hevc_nvenc"
    elif encoders["hevc_qsv"]:
        recommendation = "hevc_qsv"
    elif encoders["hevc_vaapi"]:
        recommendation = "hevc_vaapi"
    elif encoders["libx265"]:
        recommendation = "libx265_slow_confirm_first"
    else:
        recommendation = "no_hevc_encoder_found_confirm_first"
    return {"available": encoders, "recommendation": recommendation}


def classify_asr(
    tools: dict[str, str | None],
    host: dict,
    discovered_tools: dict[str, list[str]],
    workflow_files: list[str],
) -> dict:
    local_routes: list[str] = []
    cloud_routes: list[str] = []
    mlx_path = tools.get("mlx_whisper") or (discovered_tools.get("mlx_whisper") or [None])[0]
    if mlx_path and host.get("apple_silicon"):
        local_routes.append(f"mlx_whisper_apple_silicon:{mlx_path}")
    if tools.get("faster-whisper"):
        local_routes.append("faster_whisper_cli")
    if tools.get("whisper-cli") or tools.get("whisper.cpp"):
        local_routes.append("whisper_cpp")
    if tools.get("whisper"):
        local_routes.append("openai_whisper_cli")
    if any("doubao" in Path(p).name.lower() or "asr" in Path(p).name.lower() for p in workflow_files):
        local_routes.append("possible_project_asr_workflow_confirm")

    doubao_legacy = bool(os.environ.get("DOUBAO_APP_ID") and os.environ.get("DOUBAO_ACCESS_TOKEN"))
    doubao_asr = bool(os.environ.get("DOUBAO_ASR_APP_ID") and os.environ.get("DOUBAO_ASR_ACCESS_TOKEN"))
    if doubao_legacy:
        cloud_routes.append("doubao_legacy_env")
    if doubao_asr:
        cloud_routes.append("doubao_asr_env")

    if local_routes:
        recommendation = local_routes[0]
    elif cloud_routes:
        recommendation = cloud_routes[0]
    else:
        recommendation = "check_doubao_or_ask_before_cpu_asr"
    return {
        "local_routes": local_routes,
        "cloud_routes": cloud_routes,
        "env": {
            "DOUBAO_APP_ID_and_ACCESS_TOKEN": doubao_legacy,
            "DOUBAO_ASR_APP_ID_and_ACCESS_TOKEN": doubao_asr,
        },
        "recommendation": recommendation,
    }


def source_summary(probe: dict) -> dict:
    streams = probe.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    return {
        "duration": probe.get("format", {}).get("duration"),
        "size": probe.get("format", {}).get("size"),
        "bit_rate": probe.get("format", {}).get("bit_rate"),
        "video": {
            "codec": video.get("codec_name"),
            "size": f"{video.get('width')}x{video.get('height')}"
            if video.get("width")
            else None,
            "frame_rate": video.get("r_frame_rate"),
            "pix_fmt": video.get("pix_fmt"),
            "color": {
                "primaries": video.get("color_primaries"),
                "transfer": video.get("color_transfer"),
                "space": video.get("color_space"),
            },
            "bit_rate": video.get("bit_rate"),
        },
        "audio": {
            "codec": audio.get("codec_name"),
            "sample_rate": audio.get("sample_rate"),
            "channels": audio.get("channels"),
            "bit_rate": audio.get("bit_rate"),
        },
        "tags": probe.get("format", {}).get("tags") or {},
    }


def metadata_preservation_summary(probe: dict, spotlight: dict | None) -> dict:
    streams = probe.get("streams") or []
    mebx_tracks = [
        s for s in streams
        if s.get("codec_type") == "data" and s.get("codec_tag_string") == "mebx"
    ]
    codecs = (spotlight or {}).get("kMDItemCodecs") or []
    return {
        "metadata_track_count": len(mebx_tracks),
        "has_iphone_timed_metadata_tracks": bool(mebx_tracks) or "Timed Metadata" in codecs,
        "finder_reads_timed_metadata": "Timed Metadata" in codecs,
        "finder_latitude": (spotlight or {}).get("kMDItemLatitude"),
        "finder_longitude": (spotlight or {}).get("kMDItemLongitude"),
        "finder_encoding_applications": (spotlight or {}).get("kMDItemEncodingApplications"),
        "recommended_preservation_route": (
            "scripts/preserve_iphone_metadata.py --in-place"
            if platform.system() == "Darwin" and (mebx_tracks or "Timed Metadata" in codecs)
            else "exiftool_or_ffmpeg_map_metadata_only"
        ),
    }


def next_actions(report: dict) -> list[str]:
    actions = [
        "Search/confirm va7-library reference before final subtitle correction.",
        "Run audio-only silence scans with -vn and -map 0:a:0.",
    ]
    asr = report["asr"]["recommendation"]
    if asr == "check_doubao_or_ask_before_cpu_asr":
        actions.append("No fast local ASR detected; check Doubao credentials/scripts or ask user before slow CPU ASR.")
    else:
        actions.append(f"Use ASR route: {asr}, unless user prefers Doubao/cloud ASR.")

    enc = report["encoder"]["recommendation"]
    if "confirm_first" in enc:
        actions.append(f"Encoder route is {enc}; run a short smoke test and ask before full 4K render.")
    else:
        actions.append(f"Use final render encoder: {enc}; run a 5s smoke test on new hosts.")
    return actions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, help="Optional source MOV/video path.")
    parser.add_argument(
        "--search-root",
        action="append",
        type=Path,
        default=[],
        help="Optional root to search for prior ASR workflows or venv tools.",
    )
    parser.add_argument(
        "--no-recent-search",
        action="store_true",
        help="Disable bounded search of recent Codex workspace tools.",
    )
    parser.add_argument("--pretty", action="store_true", help="Print indented JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tools = which_many(
        [
            "ffmpeg",
            "ffprobe",
            "exiftool",
            "python3",
            "lark-cli",
            "mlx_whisper",
            "faster-whisper",
            "whisper-cli",
            "whisper.cpp",
            "whisper",
        ]
    )
    host = host_profile()
    search_roots = list(args.search_root)
    if not args.no_recent_search:
        search_roots.extend(
            [
                Path.cwd(),
                Path.home() / "Documents" / "Codex",
            ]
        )
    discovered_tools = find_recent_tool_paths(
        search_roots,
        ["mlx_whisper", "faster-whisper", "whisper-cli", "whisper"],
    )
    workflow_files = find_workflow_files(
        search_roots,
        ["*doubao*asr*.py", "*asr*.py", "*whisper*.py"],
    )
    hwaccels = ffmpeg_lines(["-hwaccels"]) if tools.get("ffmpeg") else ""
    encoders_text = ffmpeg_lines(["-encoders"]) if tools.get("ffmpeg") else ""
    report = {
        "host": host,
        "tools": tools,
        "discovered_tool_paths": discovered_tools,
        "discovered_asr_workflow_files": workflow_files,
        "ffmpeg_hwaccels": [line.strip() for line in hwaccels.splitlines() if line.strip()],
        "encoder": classify_encoder(encoders_text, host),
        "asr": classify_asr(tools, host, discovered_tools, workflow_files),
    }
    if args.src:
        report["source_path"] = str(args.src)
        probe = probe_source(args.src)
        report["source"] = source_summary(probe) if "error" not in probe else probe
        if "error" not in probe:
            spotlight = mdimport_attrs(args.src)
            report["spotlight_import"] = spotlight
            report["metadata_preservation"] = metadata_preservation_summary(probe, spotlight)
    report["next_actions"] = next_actions(report)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()

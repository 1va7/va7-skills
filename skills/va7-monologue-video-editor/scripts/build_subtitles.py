#!/usr/bin/env python3
"""Build corrected ASS/SRT subtitles for VA7 one-take monologue videos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_REPLACEMENTS = {
    "AI的": "AI 的",
    "英文达": "英伟达",
    "中仓": "重仓",
    "跨进电商": "跨境电商",
    "端道端": "端到端",
    "日军": "日均",
    "Air原生": "AI 原生",
    "卖假": "卖家",
    "活跃市场": "活跃时长",
    "抖增": "陡增",
    "没有上线了": "没有上限了",
    "boostrap": "bootstrap",
    "Altropic": "Anthropic",
    "all in": "All in",
    "vibecoding": "Vibe Coding",
    "one off": "one-off",
    "new api": "newapi",
    "sub-toe API": "sub2api",
    "VH": "VA7",
    "还有good one": "Have a good one",
}

DEFAULT_PROTECTED = [
    "All in",
    "AI",
    "Agent",
    "Token",
    "Prompt Engineering",
    "Vibe Coding",
    "SOP",
    "evaluation",
    "trace",
    "loop",
    "one-off",
    "sub2api",
    "newapi",
    "catch up",
    "bootstrap",
    "Anthropic",
]


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    cs = int(round(seconds * 100))
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    c = cs % 100
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def srt_time(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def wrap_text(text: str, limit: int, protected: list[str]) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text

    # Keep compact English/product phrases intact; a slightly longer one-line
    # subtitle is better than splitting "Vibe Coding" or "make sense".
    ascii_count = sum(1 for ch in text if ch.isascii() and not ch.isspace())
    if ascii_count >= 4 and len(text) <= limit + 8:
        return text

    break_chars = "，。！？、,!? "
    candidates: list[tuple[float, int]] = []
    mid = len(text) / 2
    for idx, ch in enumerate(text):
        if ch not in break_chars:
            continue
        if any(start < idx < start + len(phrase) for phrase in protected for start in find_all(text, phrase)):
            continue
        left, right = idx + 1, len(text) - idx - 1
        if 4 <= left <= limit + 4 and 4 <= right <= limit + 4:
            candidates.append((abs((idx + 1) - mid), idx + 1))
    if candidates:
        _, pos = min(candidates)
        return text[:pos].rstrip() + r"\N" + text[pos:].lstrip()

    candidate_positions = []
    for i in range(6, len(text) - 5):
        if not any(start < i < start + len(phrase) for phrase in protected for start in find_all(text, phrase)):
            candidate_positions.append(i)
    if not candidate_positions:
        candidate_positions = list(range(6, len(text) - 5))
    pos = min(candidate_positions, key=lambda i: abs(i - mid))
    return text[:pos] + r"\N" + text[pos:]


def find_all(text: str, needle: str) -> list[int]:
    starts = []
    start = text.find(needle)
    while start != -1:
        starts.append(start)
        start = text.find(needle, start + 1)
    return starts


def escape_ass(text: str) -> str:
    return text.replace("{", r"\{").replace("}", r"\}")


def load_config(path: Path | None) -> tuple[dict[str, str], dict[str, str], list[str]]:
    segment_corrections: dict[str, str] = {}
    replacements = dict(DEFAULT_REPLACEMENTS)
    protected = list(DEFAULT_PROTECTED)
    if not path:
        return segment_corrections, replacements, protected
    cfg = json.loads(path.read_text(encoding="utf-8"))
    segment_corrections.update({str(k): str(v) for k, v in cfg.get("segment_corrections", {}).items()})
    replacements.update({str(k): str(v) for k, v in cfg.get("replacements", {}).items()})
    protected.extend(str(x) for x in cfg.get("protected_phrases", []) if str(x) not in protected)
    return segment_corrections, replacements, protected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asr-json", required=True, type=Path)
    parser.add_argument("--out-ass", required=True, type=Path)
    parser.add_argument("--out-srt", required=True, type=Path)
    parser.add_argument("--start-offset", required=True, type=float, help="Seconds cut from original head.")
    parser.add_argument("--end-time", required=True, type=float, help="Original-source end time in seconds.")
    parser.add_argument("--corrections-json", type=Path)
    parser.add_argument("--width", type=int, default=3840)
    parser.add_argument("--height", type=int, default=2160)
    parser.add_argument("--font-name", default="Hiragino Sans GB")
    parser.add_argument("--font-size", type=int, default=110)
    parser.add_argument("--outline", type=int, default=2)
    parser.add_argument("--outline-color", default="D8D8D8", help="RGB hex, ASS BGR conversion is handled.")
    parser.add_argument("--margin-v", type=int, default=176)
    parser.add_argument("--wrap-limit", type=int, default=15)
    return parser.parse_args()


def ass_color(rgb_hex: str) -> str:
    rgb_hex = rgb_hex.strip().lstrip("#")
    if len(rgb_hex) != 6:
        raise ValueError("--outline-color must be 6-digit RGB hex")
    rr, gg, bb = rgb_hex[0:2], rgb_hex[2:4], rgb_hex[4:6]
    return f"&H00{bb}{gg}{rr}"


def main() -> None:
    args = parse_args()
    data = json.loads(args.asr_json.read_text(encoding="utf-8"))
    corrections, replacements, protected = load_config(args.corrections_json)

    events = []
    for seg in data["segments"]:
        seg_id = str(seg.get("id", len(events)))
        start = max(0.0, float(seg["start"]) - args.start_offset)
        end = min(args.end_time, float(seg["end"])) - args.start_offset
        if end <= 0 or start >= args.end_time - args.start_offset:
            continue
        end = max(end, start + 0.45)

        text = corrections.get(seg_id, str(seg.get("text", "")).strip())
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = escape_ass(wrap_text(text, args.wrap_limit, protected))
        events.append((start, end, text))

    outline_color = ass_color(args.outline_color)
    header = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: {args.width}
PlayResY: {args.height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{args.font_name},{args.font_size},&H00FFFFFF,&H000000FF,{outline_color},&H00000000,-1,0,0,0,100,100,0,0,1,{args.outline},0,2,240,240,{args.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    args.out_ass.parent.mkdir(parents=True, exist_ok=True)
    args.out_srt.parent.mkdir(parents=True, exist_ok=True)
    args.out_ass.write_text(
        header
        + "\n".join(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Default,,0,0,0,,{t}" for s, e, t in events)
        + "\n",
        encoding="utf-8",
    )

    blocks = []
    for i, (start, end, text) in enumerate(events, 1):
        plain = text.replace(r"\N", "\n")
        blocks.append(f"{i}\n{srt_time(start)} --> {srt_time(end)}\n{plain}\n")
    args.out_srt.write_text("\n".join(blocks), encoding="utf-8")
    print(f"wrote {args.out_ass} and {args.out_srt} ({len(events)} events)")


if __name__ == "__main__":
    main()

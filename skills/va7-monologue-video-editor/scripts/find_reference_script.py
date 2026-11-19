#!/usr/bin/env python3
"""Find VA7 monologue reference scripts from the Feishu inspiration topic table.

The deterministic gate is:
  - 选题库.待做 checkbox is checked
  - 选题库.发布排期 is not empty
  - 选题库.口播终稿 is not empty

The script returns structured candidates only. A model or human should inspect
the top candidates and choose the actual matching稿件 before subtitle correction.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


# Library base comes from the shared va7 config (VA7_USER_CONFIG / va7-config).
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "va7-pipeline" / "scripts"))
from va7config import base_config, run_capture  # noqa: E402

BASE_TOKEN, _TABLES = base_config()
TOPIC_TABLE = _TABLES.get("topics")
FIELDS = [
    "选题标题",
    "待做",
    "发布排期",
    "口播终稿",
    "口播草稿",
    "选题角度",
    "人性钩子",
    "标签",
    "目标平台",
    "创建日期",
]


def extract_json(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start == -1:
        raise SystemExit(f"Could not find JSON object in lark-cli output:\n{text[:1000]}")
    return json.loads(text[start:])


def run_lark_record_list(offset: int, limit: int) -> dict[str, Any]:
    if not shutil.which("lark-cli"):
        raise SystemExit("Missing required command: lark-cli")
    if not BASE_TOKEN or not TOPIC_TABLE:
        raise SystemExit("找不到灵感库配置：设 VA7_USER_CONFIG 或部署 va7-config（见 va7-pipeline「Multi-User Config」）")
    cmd = [
        "lark-cli",
        "base",
        "+record-list",
        "--base-token",
        BASE_TOKEN,
        "--table-id",
        TOPIC_TABLE,
        "--limit",
        str(limit),
        "--offset",
        str(offset),
    ]
    for field in FIELDS:
        cmd.extend(["--field-id", field])
    cmd.extend(["--format", "json"])
    proc = run_capture(cmd)
    if proc.returncode != 0:
        raise SystemExit(
            "lark-cli record-list failed\n"
            f"STDOUT:\n{proc.stdout[-2000:]}\nSTDERR:\n{proc.stderr[-2000:]}"
        )
    data = extract_json(proc.stdout)
    if data.get("ok") is False:
        raise SystemExit(json.dumps(data.get("error") or data, ensure_ascii=False, indent=2))
    return data


def normalize_record_list(data: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    payload = data.get("data") or {}
    fields = payload.get("fields") or []
    record_ids = payload.get("record_id_list") or []
    rows = payload.get("data") or []
    records: list[dict[str, Any]] = []
    for record_id, row in zip(record_ids, rows):
        record: dict[str, Any] = {"record_id": str(record_id)}
        for index, field in enumerate(fields):
            record[str(field)] = row[index] if index < len(row) else None
        records.append(record)
    return records, bool(payload.get("has_more"))


def fetch_topic_records(limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    offset = 0
    page_size = min(max(limit, 1), 500)
    while True:
        page, has_more = normalize_record_list(run_lark_record_list(offset, page_size))
        records.extend(page)
        if not has_more or not page:
            break
        offset += len(page)
    return records


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(
            value.get("text")
            or value.get("name")
            or value.get("value")
            or value.get("record_id")
            or value.get("id")
            or ""
        ).strip()
    values = [cell_text(item) for item in as_list(value)]
    return " ".join(v for v in values if v).strip()


def checkbox_checked(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "checked", "勾选", "是"}
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, dict):
        return checkbox_checked(value.get("checked") or value.get("value") or value.get("text"))
    return any(checkbox_checked(item) for item in as_list(value))


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("token", "token")
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)
    return text


def ngrams(text: str, n: int = 2) -> set[str]:
    text = normalize_text(text)
    if not text:
        return set()
    if len(text) <= n:
        return {text}
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_asr_text(path: Path | None) -> str:
    if not path:
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if isinstance(data.get("text"), str):
            return data["text"]
        segments = data.get("segments")
        if isinstance(segments, list):
            return "".join(str(seg.get("text", "")) for seg in segments if isinstance(seg, dict))
    raise SystemExit(f"Unsupported ASR JSON shape: {path}")


def keyword_hits(haystack: str, needles: list[str]) -> list[str]:
    hay = normalize_text(haystack)
    hits = []
    for needle in needles:
        n = normalize_text(needle)
        if len(n) >= 2 and n in hay:
            hits.append(needle)
    return hits


def score_record(record: dict[str, Any], asr_text: str, hints: list[str]) -> tuple[float, list[str]]:
    title = cell_text(record.get("选题标题"))
    final_script = cell_text(record.get("口播终稿"))
    angle = cell_text(record.get("选题角度"))
    hook = cell_text(record.get("人性钩子"))
    searchable = "\n".join([title, angle, hook, final_script[:1600]])

    reasons: list[str] = []
    score = 0.0

    hits = keyword_hits(searchable, hints)
    if hits:
        score += min(18.0, 6.0 * len(hits))
        reasons.append("hint_hit:" + ",".join(hits[:4]))

    if asr_text.strip():
        asr_head = normalize_text(asr_text[:1800])
        script_head = normalize_text(final_script[:2200])
        jac = jaccard(ngrams(asr_head), ngrams(script_head))
        ratio = difflib.SequenceMatcher(None, asr_head[:1200], script_head[:1200]).ratio()
        score += jac * 65.0 + ratio * 20.0
        reasons.append(f"asr_bigram_jaccard={jac:.3f}")
        reasons.append(f"asr_sequence_ratio={ratio:.3f}")

        asr_first = normalize_text(asr_text[:80])
        if asr_first and asr_first[:20] in script_head:
            score += 12.0
            reasons.append("opening_phrase_match")

    title_hits = keyword_hits(title, hints)
    if title_hits:
        score += min(14.0, 7.0 * len(title_hits))
        reasons.append("title_hit:" + ",".join(title_hits[:4]))

    return round(score, 3), reasons


def record_summary(
    record: dict[str, Any],
    score: float,
    reasons: list[str],
    *,
    include_script: bool,
    preview_chars: int,
) -> dict[str, Any]:
    final_script = cell_text(record.get("口播终稿"))
    item = {
        "record_id": record["record_id"],
        "score": score,
        "title": cell_text(record.get("选题标题")),
        "publish_schedule": cell_text(record.get("发布排期")),
        "todo_checked": checkbox_checked(record.get("待做")),
        "final_script_chars": len(final_script),
        "final_script_preview": final_script[:preview_chars],
        "angle": cell_text(record.get("选题角度")),
        "hook_preview": cell_text(record.get("人性钩子"))[:preview_chars],
        "reasons": reasons,
    }
    if include_script:
        item["final_script"] = final_script
    return item


def confidence(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "none"
    top = float(candidates[0]["score"])
    second = float(candidates[1]["score"]) if len(candidates) > 1 else 0.0
    if top >= 45 and top - second >= 8:
        return "high"
    if top >= 25:
        return "medium"
    return "low"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asr-json", type=Path, help="ASR JSON with text/segments, used only for scoring.")
    parser.add_argument("--asr-text", help="Plain ASR text, used only for scoring.")
    parser.add_argument("--source-path", type=Path, help="Source video path; basename and parent folder become hints.")
    parser.add_argument("--hint", action="append", default=[], help="Extra title/topic hint. Can be repeated.")
    parser.add_argument("--limit", type=int, default=500, help="Record-list page size / max page size.")
    parser.add_argument("--top", type=int, default=5, help="Number of candidates to return.")
    parser.add_argument("--include-script", action="store_true", help="Include full 口播终稿 in output.")
    parser.add_argument("--script-preview-chars", type=int, default=260)
    parser.add_argument("--out", type=Path, help="Write JSON to this path. JSON is also printed.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    hints = list(args.hint)
    if args.source_path:
        hints.extend([args.source_path.stem, args.source_path.parent.name])
    asr_text = args.asr_text or load_asr_text(args.asr_json)

    records = fetch_topic_records(args.limit)
    eligible = []
    rejected_counts = {"todo_unchecked": 0, "empty_schedule": 0, "empty_final_script": 0}
    for record in records:
        todo = checkbox_checked(record.get("待做"))
        schedule = cell_text(record.get("发布排期"))
        final_script = cell_text(record.get("口播终稿"))
        if not todo:
            rejected_counts["todo_unchecked"] += 1
            continue
        if not schedule:
            rejected_counts["empty_schedule"] += 1
            continue
        if not final_script:
            rejected_counts["empty_final_script"] += 1
            continue
        score, reasons = score_record(record, asr_text, hints)
        eligible.append((score, reasons, record))

    eligible.sort(key=lambda item: item[0], reverse=True)
    candidates = [
        record_summary(
            record,
            score,
            reasons,
            include_script=args.include_script,
            preview_chars=args.script_preview_chars,
        )
        for score, reasons, record in eligible[: max(0, args.top)]
    ]
    result = {
        "source": "feishu_inspiration_topic_table",
        "base_token": BASE_TOKEN,
        "table_id": TOPIC_TABLE,
        "deterministic_filter": {
            "待做": "checked",
            "发布排期": "not_empty",
            "口播终稿": "not_empty",
        },
        "input_hints": hints,
        "asr_chars": len(asr_text),
        "records_scanned": len(records),
        "eligible_count": len(eligible),
        "rejected_counts": rejected_counts,
        "confidence": confidence(candidates),
        "candidates": candidates,
        "model_gate": "Inspect candidates and choose the actual matching 口播终稿; do not use caches or finished-content rows as source of truth.",
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

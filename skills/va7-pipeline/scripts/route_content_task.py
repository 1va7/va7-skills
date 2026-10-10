#!/usr/bin/env python3
"""Route a VA7 content request to the next correct skill."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "va7-interview" / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))
from validate_content_brief import load_brief  # noqa: E402
from writing_intent import active_signal_matches, decide_writing_request, instruction_text  # noqa: E402


# No default base: every user's library lives in their own Bitable, recorded
# in the config.json written by va7-onboarding. Without VA7_USER_CONFIG the
# router skips live Base search instead of touching anyone's data.
def _load_user_base_config() -> tuple[str | None, dict[str, str]]:
    config_path = os.environ.get("VA7_USER_CONFIG")
    if not config_path:
        return None, {}
    data = json.loads(Path(config_path).expanduser().read_text(encoding="utf-8"))
    base = data.get("base", {})
    return base.get("base_token"), dict(base.get("tables", {}))


BASE_TOKEN, TABLES = _load_user_base_config()

RAW_TOPIC_PATTERNS = [
    r"我有个?灵感",
    r"这个选题",
    r"选题是",
    r"主题是",
    r"能不能写成",
    r"写.*口播",
    r"写.*小红书",
    r"帮我想.*方向",
]

VIDEO_PATTERNS = [r"剪视频", r"加字幕", r"口播视频", r"\.mov\b", r"\.mp4\b", r"一镜到底"]
COVER_PATTERNS = [r"封面", r"封面图", r"缩略图", r"抽帧", r"候选帧"]
PUBLISH_PATTERNS = [r"发布物料", r"标题正文", r"hashtag", r"Hashtag", r"章节", r"同步.*灵感库", r"成品内容"]
WECHAT_PATTERNS = [r"公众号", r"WeChat", r"草稿箱"]
REVIEW_PATTERNS = [r"复盘", r"RL\s*数据集", r"训练数据", r"版本追踪", r"写作版本", r"session"]
INGEST_PATTERNS = [r"加到灵感库", r"记到灵感库", r"入库", r"抓.*灵感库", r"转录.*灵感库"]
CONTINUE_PATTERNS = [r"继续", r"做到哪", r"现在.*阶段", r"接下来", r"之前"]


def match_any(text: str, patterns: list[str]) -> list[str]:
    return active_signal_matches(text, patterns)


def compact_keyword(text: str) -> str:
    cleaned = re.sub(r"https?://\S+", " ", text)
    cleaned = re.sub(r"[/\\].*", " ", cleaned)
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", cleaned)
    tokens = [t for t in cleaned.split() if len(t) >= 2]
    stop = {"帮我", "一下", "这个", "选题", "口播", "小红书", "内容", "继续", "现在", "阶段"}
    tokens = [t for t in tokens if t not in stop]
    return " ".join(tokens[:8]).strip()


def keyword_variants(keyword: str) -> list[str]:
    parts = [p for p in keyword.split() if len(p) >= 2]
    variants: list[str] = []
    if keyword:
        variants.append(keyword)
    for part in parts:
        if part not in variants:
            variants.append(part)
    ascii_terms = [p for p in parts if re.search(r"[A-Za-z]", p)]
    chinese_terms = [p for p in parts if re.search(r"[\u4e00-\u9fff]", p)]
    for combo in [" ".join(ascii_terms[:2]), " ".join(chinese_terms[:2])]:
        if combo and combo not in variants:
            variants.append(combo)
    return variants[:5]


def run_json(cmd: list[str], timeout: int = 20) -> dict[str, Any]:
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        return {"ok": False, "cmd": cmd, "returncode": proc.returncode, "stderr": proc.stderr.strip(), "stdout": proc.stdout[:2000]}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "cmd": cmd, "error": "non-json stdout", "stdout": proc.stdout[:2000]}
    payload["_cmd"] = cmd
    return payload


def search_table(keyword: str, table_id: str, search_fields: list[str], select_fields: list[str], limit: int = 5) -> dict[str, Any]:
    if not BASE_TOKEN:
        return {"ok": False, "skipped": "VA7_USER_CONFIG not set; base search disabled"}
    if not keyword:
        return {"ok": False, "skipped": "empty keyword"}
    cmd = [
        "lark-cli",
        "base",
        "+record-search",
        "--base-token",
        BASE_TOKEN,
        "--table-id",
        table_id,
        "--keyword",
        keyword,
        "--limit",
        str(limit),
        "--format",
        "json",
        "--as",
        "user",
    ]
    for field in search_fields:
        cmd.extend(["--search-field", field])
    for field in select_fields:
        cmd.extend(["--field-id", field])
    return run_json(cmd)


def search_table_variants(keyword: str, table_id: str, search_fields: list[str], select_fields: list[str], limit: int = 5) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for variant in keyword_variants(keyword):
        payload = search_table(variant, table_id, search_fields, select_fields, limit=limit)
        payload["keyword_variant"] = variant
        attempts.append(
            {
                "ok": payload.get("ok"),
                "keyword_variant": variant,
                "count": count_records(payload),
                "error": payload.get("error") or payload.get("stderr"),
            }
        )
        if count_records(payload):
            payload["attempts"] = attempts
            return payload
    return attempts[-1] | {"attempts": attempts} if attempts else {"ok": False, "skipped": "no keyword variants"}


def count_records(payload: dict[str, Any]) -> int:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return 0
    records = data.get("items") or data.get("records") or data.get("record_list") or data.get("data") or []
    return len(records) if isinstance(records, list) else 0


def local_context_hits(keyword: str, limit: int = 20) -> list[dict[str, str]]:
    roots = [Path.cwd() / "work", Path.cwd() / "outputs"]
    extra_roots = os.environ.get("VA7_LOCAL_CONTEXT_ROOTS", "")
    roots.extend(Path(p) for p in extra_roots.split(":") if p)
    variants = keyword_variants(keyword)
    hits: list[dict[str, str]] = []
    for root in roots:
        if not root.exists():
            continue
        for variant in variants:
            if not variant:
                continue
            try:
                proc = subprocess.run(
                    ["rg", "-n", "--fixed-strings", "--glob", "!*.pyc", "--glob", "!node_modules/**", variant, str(root)],
                    text=True,
                    capture_output=True,
                    timeout=8,
                    check=False,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
            for line in proc.stdout.splitlines()[:limit]:
                pieces = line.split(":", 2)
                if len(pieces) == 3:
                    hits.append({"path": pieces[0], "line": pieces[1], "match": pieces[2][:240], "keyword_variant": variant})
                    if len(hits) >= limit:
                        return hits
    return hits


def classify(text: str, path: str | None) -> dict[str, Any]:
    hits = {
        "raw_topic": match_any(text, RAW_TOPIC_PATTERNS),
        "video": match_any(text, VIDEO_PATTERNS),
        "cover": match_any(text, COVER_PATTERNS),
        "publish": match_any(text, PUBLISH_PATTERNS),
        "wechat": match_any(text, WECHAT_PATTERNS),
        "review": match_any(text, REVIEW_PATTERNS),
        "ingest": match_any(text, INGEST_PATTERNS),
        "continue": match_any(text, CONTINUE_PATTERNS),
    }
    if path:
        lower = path.lower()
        if lower.endswith((".mov", ".mp4", ".m4v")):
            hits["video"].append("path-video-extension")
        if Path(path).expanduser().is_dir():
            hits["video"].append("path-directory")
    return hits


def recommend(hits: dict[str, list[str]], *, base_matches: dict[str, Any], writing: dict[str, Any] | None = None) -> tuple[str, str, list[str], list[str]]:
    topic_matches = count_records(base_matches.get("topics", {}))
    finished_matches = count_records(base_matches.get("finished", {}))

    if hits["review"]:
        return "review_stage", "agent-writing-rl-dataset", ["scan/export/validate before sync"], ["Run agent-writing-rl-dataset workflow"]
    if hits["wechat"]:
        return "wechat_stage", "wechat-converter", ["preserve images", "then route to wechat-cover and wechat-draft-publisher"], ["Convert article for WeChat"]
    if hits["publish"]:
        return "publish_stage", "va7-publish", ["dry-run before apply", "chapters require real timestamps"], ["Prepare title/body/hashtag/chapter JSON"]
    if writing and writing["decision"] in {"ready_to_outline", "ready_to_draft", "ready_to_revise"} and not hits["cover"]:
        stages = {"ready_to_outline": "outline_stage", "ready_to_draft": "draft_stage", "ready_to_revise": "revision_stage"}
        actions = {
            "ready_to_outline": "Present a speaking outline only; preserve confirmed decisions and expose only real evidence gaps",
            "ready_to_draft": "Write the explicitly authorized full draft from the confirmed outline or current user direction",
            "ready_to_revise": "Edit the identified source text within the requested scope; preserve authorship",
        }
        # A video attachment is reference context when the user explicitly asks to write.
        if writing["requested_artifact"] and (not hits["video"] or writing.get("explicit_request")):
            return stages[writing["decision"]], "va7-script", [writing["reason"], "current user instructions override this advisory classifier"], [actions[writing["decision"]]]
    if hits["cover"] and hits["video"]:
        return "media_stage", "va7-video-cover-maker + va7-monologue-video-editor", ["source/copy/frame gates", "video preflight"], ["Run media preflight and cover candidate extraction"]
    if hits["cover"]:
        return "media_stage", "va7-video-cover-maker", ["approved source frame and title required"], ["Run cover preflight"]
    if hits["video"]:
        return "media_stage", "va7-monologue-video-editor", ["source video and reference script gate"], ["Run video preflight"]
    if hits["ingest"]:
        return "ingestion_stage", "va7-library", ["schema audit", "duplicate search", "readback"], ["Run inspiration_pipeline.py"]
    if hits["continue"]:
        return "context_recovery", "va7-pipeline", ["recover artifact, outline version, and confirmation evidence", "a Base hit is context, not authorization"], ["Recover existing decisions; ask only for a missing next action"]
    if (writing and writing["decision"] == "route_to_interview") or (not writing and hits["raw_topic"]):
        if topic_matches or finished_matches:
            return "topic_needs_interview", "va7-interview", ["existing record is context, not drafting permission"], ["Summarize matches and start direction/interview gate"]
        return "new_raw_topic", "va7-interview", ["must not draft", "search Base first", "offer alternatives"], ["Start VA7 content interview"]
    return "needs_context", "va7-pipeline", ["recover current intent and existing decisions", "do not infer full-draft permission or restart the interview"], ["Resolve only the missing context or ask one targeted question"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--path")
    parser.add_argument("--out")
    parser.add_argument("--brief", help="Optional content brief with writing_state; topic approval alone permits only outlining")
    parser.add_argument("--no-base-search", action="store_true")
    args = parser.parse_args()

    text = args.input.strip()
    keyword = compact_keyword(text)
    hits = classify(instruction_text(text), args.path)
    brief, validator_report = load_brief(args.brief) if args.brief else ({}, {})
    writing = decide_writing_request(
        text,
        brief_ready=validator_report.get("ok") is True,
        writing_state=brief.get("writing_state"),
        has_brief=bool(args.brief),
    )

    base_matches: dict[str, Any] = {}
    if not args.no_base_search and keyword:
        base_matches["topics"] = search_table_variants(
            keyword,
            TABLES["topics"],
            ["选题标题", "选题角度", "口播草稿"],
            ["选题标题", "选题角度", "潜力等级", "目标平台", "口播草稿", "口播终稿"],
        )
        base_matches["finished"] = search_table_variants(
            keyword,
            TABLES["finished"],
            ["标题", "正文描述", "口播稿全文"],
            ["标题", "平台", "状态", "发布日期", "链接", "口播稿全文"],
        )
        base_matches["schedules"] = search_table_variants(
            keyword,
            TABLES["schedules"],
            ["视频标题", "视频文案介绍", "备注"],
            ["视频标题", "状态", "发布日期", "视频文案介绍"],
        )

    stage, skill, checks, actions = recommend(hits, base_matches=base_matches, writing=writing)
    result = {
        "ok": True,
        "input": text,
        "path": args.path,
        "keyword": keyword,
        "detected_signals": hits,
        "stage": stage,
        "writing_gate": writing,
        "validator_report": validator_report,
        "recommended_skill": skill,
        "required_checks": checks,
        "next_actions": actions,
        "base_search": {
            name: {
                "ok": payload.get("ok"),
                "count": count_records(payload),
                "cmd": payload.get("_cmd"),
                "error": payload.get("error") or payload.get("stderr"),
            }
            for name, payload in base_matches.items()
        },
        "local_context_hits": local_context_hits(keyword) if hits["continue"] else [],
        "base_search_raw": base_matches,
    }

    if args.out:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
import argparse
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# No default base: this script writes records, so it refuses to run without
# the invoking user's config.json (written by va7-onboarding).
def _load_user_base_config() -> tuple[str, dict[str, str]]:
    config_path = os.environ.get("VA7_USER_CONFIG")
    if not config_path:
        raise SystemExit("VA7_USER_CONFIG 未设置。先跑 va7-onboarding，再 export VA7_USER_CONFIG=<用户目录>/config.json")
    data = json.loads(Path(config_path).expanduser().read_text(encoding="utf-8"))
    base = data.get("base", {})
    token = base.get("base_token")
    if not token:
        raise SystemExit("config.json 缺 base.base_token，请重跑 va7-onboarding")
    return token, dict(base.get("tables", {}))


BASE_TOKEN, _TABLES = _load_user_base_config()
TOPIC_TABLE = _TABLES["topics"]
SCHEDULE_TABLE = _TABLES["schedules"]
FINISHED_TABLE = _TABLES["finished"]
TIME_RE = re.compile(r"^(?:(\d{1,2}):)?([0-5]?\d):([0-5]\d)$")


@dataclass
class Record:
    record_id: str
    fields: dict[str, Any]


def run_lark(args: list[str], *, dry_run: bool = False) -> dict[str, Any]:
    cmd = ["lark-cli", *args, "--format", "json"]
    if dry_run and "+record-" in " ".join(args):
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(f"Command failed:\n{' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Failed to parse lark-cli JSON output: {exc}\n{proc.stdout}") from exc


def map_records(payload: dict[str, Any]) -> list[Record]:
    data = payload["data"]
    fields = data["fields"]
    rows = data["data"]
    ids = data["record_id_list"]
    out: list[Record] = []
    for record_id, row in zip(ids, rows):
        out.append(Record(record_id=record_id, fields=dict(zip(fields, row))))
    return out


def record_ids(cell: Any) -> list[str]:
    ids: list[str] = []
    if not cell:
        return ids
    items = cell if isinstance(cell, list) else [cell]
    for item in items:
        if isinstance(item, dict):
            value = item.get("id") or item.get("record_id")
        else:
            value = item
        if value:
            ids.append(str(value))
    return ids


def first_select(cell: Any) -> str | None:
    if isinstance(cell, list) and cell:
        return str(cell[0])
    if isinstance(cell, str) and cell:
        return cell
    return None


def get_topics(topic_ids: list[str]) -> dict[str, Record]:
    args = [
        "base",
        "+record-get",
        "--base-token",
        BASE_TOKEN,
        "--table-id",
        TOPIC_TABLE,
    ]
    for rid in topic_ids:
        args += ["--record-id", rid]
    for field in ["选题标题", "关联内容排期", "选题类型", "目标平台", "口播终稿", "文字标题", "视频正文", "Hashtag", "章节"]:
        args += ["--field-id", field]
    records = map_records(run_lark(args))
    return {record.record_id: record for record in records}


def get_schedules(schedule_ids: list[str]) -> dict[str, Record]:
    if not schedule_ids:
        return {}
    args = [
        "base",
        "+record-get",
        "--base-token",
        BASE_TOKEN,
        "--table-id",
        SCHEDULE_TABLE,
    ]
    for rid in schedule_ids:
        args += ["--record-id", rid]
    for field in ["内容标题", "视频标题", "视频文案介绍", "备注", "关联选题", "平台发布记录", "选题类型"]:
        args += ["--field-id", field]
    records = map_records(run_lark(args))
    return {record.record_id: record for record in records}


def get_finished_by_schedule(schedule_ids: list[str]) -> dict[str, Record]:
    payload = run_lark([
        "base",
        "+record-list",
        "--base-token",
        BASE_TOKEN,
        "--table-id",
        FINISHED_TABLE,
        "--field-id",
        "标题",
        "--field-id",
        "正文描述",
        "--field-id",
        "Hashtag",
        "--field-id",
        "状态",
        "--field-id",
        "平台",
        "--field-id",
        "选题类型",
        "--field-id",
        "关联内容排期",
        "--limit",
        "200",
    ])
    by_schedule: dict[str, Record] = {}
    for record in map_records(payload):
        for sid in record_ids(record.fields.get("关联内容排期")):
            if sid in schedule_ids:
                by_schedule[sid] = record
    return by_schedule


def upsert_record(table_id: str, record_id: str | None, patch: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    args = [
        "base",
        "+record-upsert",
        "--base-token",
        BASE_TOKEN,
        "--table-id",
        table_id,
        "--json",
        json.dumps(patch, ensure_ascii=False),
    ]
    if record_id:
        args += ["--record-id", record_id]
    return run_lark(args, dry_run=dry_run)


def time_to_seconds(value: str) -> int:
    match = TIME_RE.match(value.strip())
    if not match:
        raise SystemExit(f"Invalid chapter timestamp {value!r}; use MM:SS or HH:MM:SS")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def validate_chapter_text(text: str) -> str:
    blocks = [block.strip() for block in text.strip().split("\n\n") if block.strip()]
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) != 3:
            raise SystemExit(f"Invalid chapter block; expected 3 lines, got {len(lines)}:\n{block}")
        title_line, range_line, content_line = lines
        if not (title_line.startswith("【") and title_line.endswith("】")):
            raise SystemExit(f"Invalid chapter title line: {title_line}")
        title = title_line[1:-1]
        if len(title) > 14:
            raise SystemExit(f"Chapter title too long ({len(title)} > 14): {title}")
        if len(content_line) > 20:
            raise SystemExit(f"Chapter content too long ({len(content_line)} > 20): {content_line}")
        if "-" not in range_line:
            raise SystemExit(f"Invalid chapter time range: {range_line}")
        start, end = [part.strip() for part in range_line.split("-", 1)]
        if time_to_seconds(start) >= time_to_seconds(end):
            raise SystemExit(f"Chapter start must be before end: {range_line}")
    return "\n\n".join(blocks)


def format_chapters(value: Any, *, max_chapters: int | None = None) -> str | None:
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        text = validate_chapter_text(value)
        blocks = [block for block in text.split("\n\n") if block.strip()]
        if max_chapters is not None and len(blocks) > max_chapters:
            raise SystemExit(f"Too many chapters ({len(blocks)} > {max_chapters})")
        return text
    if not isinstance(value, list):
        raise SystemExit("chapters must be a formatted string or a list of chapter objects")
    if max_chapters is not None and len(value) > max_chapters:
        raise SystemExit(f"Too many chapters ({len(value)} > {max_chapters})")
    blocks: list[str] = []
    last_end = -1
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"Chapter {index} must be an object")
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        start = str(item.get("start") or "").strip()
        end = str(item.get("end") or "").strip()
        if not title or not content or not start or not end:
            raise SystemExit(f"Chapter {index} requires title, start, end, content")
        if len(title) > 14:
            raise SystemExit(f"Chapter title too long ({len(title)} > 14): {title}")
        if len(content) > 20:
            raise SystemExit(f"Chapter content too long ({len(content)} > 20): {content}")
        start_s = time_to_seconds(start)
        end_s = time_to_seconds(end)
        if start_s >= end_s:
            raise SystemExit(f"Chapter {index} start must be before end: {start}-{end}")
        if last_end > start_s:
            raise SystemExit(f"Chapter {index} overlaps previous chapter: {start}-{end}")
        last_end = end_s
        blocks.append(f"【{title}】\n{start}-{end}\n{content}")
    return validate_chapter_text("\n\n".join(blocks))


def chapter_limit(item: dict[str, Any]) -> int | None:
    if item.get("max_chapters") not in (None, ""):
        return int(item["max_chapters"])
    if item.get("video_duration_seconds") not in (None, ""):
        return int(math.ceil(float(item["video_duration_seconds"]) / 60.0))
    return None


def create_finished(material: dict[str, Any], topic: Record, schedule_id: str, *, dry_run: bool) -> str:
    topic_type = first_select(topic.fields.get("选题类型")) or "专业性"
    patch = {
        "标题": material["title"],
        "正文描述": material["body"],
        "Hashtag": material["hashtag"],
        "状态": "草稿",
        "平台": "小红书",
        "选题类型": topic_type,
        "关联内容排期": [schedule_id],
        "口播稿全文": topic.fields.get("口播终稿") or "",
    }
    if dry_run:
        return "recDRYRUN_FINISHED"
    payload = upsert_record(FINISHED_TABLE, None, patch, dry_run=False)
    data = payload.get("data") or {}
    record = data.get("record") or {}
    record_id = record.get("record_id") or record.get("id")
    if not record_id:
        record_ids = data.get("record_id_list") or []
        if record_ids:
            record_id = record_ids[0]
    if not record_id:
        found = get_finished_by_schedule([schedule_id]).get(schedule_id)
        if found:
            record_id = found.record_id
    return str(record_id or "")


def with_publish_material_block(existing: Any, hashtag: str) -> str:
    text = str(existing or "").rstrip()
    block = f"[发布物料]\nHashtag: {hashtag}"
    marker = "[发布物料]"
    if marker in text:
        head = text.split(marker, 1)[0].rstrip()
        return (head + "\n\n" + block).strip()
    return (text + "\n\n" + block).strip() if text else block


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="JSON array with topic_record_id, title, body, hashtag, optional chapters")
    parser.add_argument("--apply", action="store_true", help="write to Feishu; omit for dry-run plan")
    parser.add_argument("--plan-out", help="write plan/readback JSON to this path")
    args = parser.parse_args()

    materials = json.loads(Path(args.input).read_text(encoding="utf-8"))
    topic_ids = [item["topic_record_id"] for item in materials]
    topics = get_topics(topic_ids)

    schedule_ids: list[str] = []
    plan: list[dict[str, Any]] = []
    for item in materials:
        topic = topics.get(item["topic_record_id"])
        if not topic:
            raise SystemExit(f"Topic not found: {item['topic_record_id']}")
        linked = record_ids(topic.fields.get("关联内容排期"))
        if len(linked) != 1:
            raise SystemExit(f"Topic {item['topic_record_id']} must have exactly one schedule link, got {linked}")
        schedule_ids.append(linked[0])

    schedules = get_schedules(schedule_ids)
    finished_by_schedule = get_finished_by_schedule(schedule_ids)
    apply_mode = bool(args.apply)
    created_or_updated_finished: dict[str, str] = {}

    for item in materials:
        topic = topics[item["topic_record_id"]]
        schedule_id = record_ids(topic.fields.get("关联内容排期"))[0]
        schedule = schedules[schedule_id]
        finished = finished_by_schedule.get(schedule_id)
        max_chapters = chapter_limit(item)
        chapter_text = format_chapters(item.get("chapters"), max_chapters=max_chapters)

        topic_patch = {
            "文字标题": item["title"],
            "视频正文": item["body"],
            "Hashtag": item["hashtag"],
        }
        if chapter_text:
            topic_patch["章节"] = chapter_text
        plan.append({
            "action": "update_topic_publish_materials",
            "record_id": item["topic_record_id"],
            "patch": topic_patch,
        })
        if apply_mode:
            upsert_record(TOPIC_TABLE, item["topic_record_id"], topic_patch, dry_run=False)

        schedule_patch = {
            "视频标题": item["title"],
            "视频文案介绍": item["body"],
            "备注": with_publish_material_block(schedule.fields.get("备注"), item["hashtag"]),
        }
        plan.append({
            "action": "update_schedule",
            "record_id": schedule_id,
            "topic_record_id": item["topic_record_id"],
            "patch": schedule_patch,
        })
        if apply_mode:
            upsert_record(SCHEDULE_TABLE, schedule_id, schedule_patch, dry_run=False)

        if finished:
            finished_patch = {
                "标题": item["title"],
                "正文描述": item["body"],
                "Hashtag": item["hashtag"],
                "口播稿全文": topic.fields.get("口播终稿") or "",
            }
            plan.append({
                "action": "update_finished_content",
                "record_id": finished.record_id,
                "schedule_record_id": schedule_id,
                "patch": finished_patch,
            })
            if apply_mode:
                upsert_record(FINISHED_TABLE, finished.record_id, finished_patch, dry_run=False)
                created_or_updated_finished[schedule_id] = finished.record_id
        else:
            plan.append({
                "action": "create_finished_content_draft",
                "schedule_record_id": schedule_id,
                "topic_record_id": item["topic_record_id"],
                "title": item["title"],
            })
            if apply_mode:
                finished_id = create_finished(item, topic, schedule_id, dry_run=False)
                if not finished_id:
                    raise SystemExit(f"Failed to create finished content for schedule {schedule_id}")
                created_or_updated_finished[schedule_id] = finished_id
                upsert_record(SCHEDULE_TABLE, schedule_id, {"平台发布记录": [finished_id]}, dry_run=False)
                plan.append({
                    "action": "backfill_schedule_finished_link",
                    "record_id": schedule_id,
                    "finished_record_id": finished_id,
                })

    readback: dict[str, Any] = {}
    if apply_mode:
        refreshed_schedules = get_schedules(schedule_ids)
        refreshed_finished = get_finished_by_schedule(schedule_ids)
        readback = {
            "topics": {
                rid: {
                    "文字标题": rec.fields.get("文字标题"),
                    "视频正文": rec.fields.get("视频正文"),
                    "Hashtag": rec.fields.get("Hashtag"),
                    "章节": rec.fields.get("章节"),
                }
                for rid, rec in get_topics(topic_ids).items()
            },
            "schedules": {
                sid: {
                    "视频标题": rec.fields.get("视频标题"),
                    "视频文案介绍": rec.fields.get("视频文案介绍"),
                    "平台发布记录": record_ids(rec.fields.get("平台发布记录")),
                }
                for sid, rec in refreshed_schedules.items()
            },
            "finished_content": {
                sid: {
                    "record_id": rec.record_id,
                    "标题": rec.fields.get("标题"),
                    "Hashtag": rec.fields.get("Hashtag"),
                    "状态": rec.fields.get("状态"),
                    "关联内容排期": record_ids(rec.fields.get("关联内容排期")),
                }
                for sid, rec in refreshed_finished.items()
            },
        }
        for item in materials:
            sid = record_ids(topics[item["topic_record_id"]].fields.get("关联内容排期"))[0]
            topic_back = readback["topics"].get(item["topic_record_id"]) or {}
            sched = readback["schedules"].get(sid) or {}
            fin = readback["finished_content"].get(sid) or {}
            expected_chapters = format_chapters(item.get("chapters"), max_chapters=chapter_limit(item))
            if topic_back.get("文字标题") != item["title"] or topic_back.get("Hashtag") != item["hashtag"]:
                raise SystemExit(f"Readback mismatch for topic publish fields {item['topic_record_id']}")
            if expected_chapters and topic_back.get("章节") != expected_chapters:
                raise SystemExit(f"Readback mismatch for topic chapters {item['topic_record_id']}")
            if sched.get("视频标题") != item["title"]:
                raise SystemExit(f"Readback mismatch for schedule title {sid}")
            if fin.get("标题") != item["title"] or fin.get("Hashtag") != item["hashtag"]:
                raise SystemExit(f"Readback mismatch for finished content {sid}")

    result = {"ok": True, "apply": apply_mode, "plan": plan, "readback": readback}
    if args.plan_out:
        Path(args.plan_out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

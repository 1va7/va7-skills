#!/usr/bin/env python3
"""Scripted ingestion pipeline for the VA7 inspiration library.

The script owns deterministic work:
- fetch source material from Feishu docs, local files, URLs, or X/Twitter
- extract 16k mono audio from media files
- call a configurable transcription backend
- validate draft JSON against live Feishu Base schema
- create material/topic records and verify required fields after upload

It intentionally does not pretend to be the creative model. Use `make-draft`
to generate a JSON scaffold and prompt, fill the draft with an LLM, then run
`validate-draft` and `upload`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


BASE_TOKEN: str | None = None
BASE_URL: str | None = None
MATERIAL_TABLE: str | None = None
TOPIC_TABLE: str | None = None
FINISHED_CONTENT_TABLE: str | None = None
VIRAL_TOPIC_TABLE: str | None = None
PRODUCTION_SCHEDULE_TABLE: str | None = None


def _apply_user_base_config() -> None:
    """Every user's library lives in their own Bitable, recorded in the
    config.json written by va7-onboarding. This pipeline writes records, so
    it refuses to run without that config."""
    config_path = os.environ.get("VA7_USER_CONFIG")
    if not config_path:
        raise SystemExit("VA7_USER_CONFIG 未设置。先跑 va7-onboarding，再 export VA7_USER_CONFIG=<用户目录>/config.json")
    global BASE_TOKEN, BASE_URL, MATERIAL_TABLE, TOPIC_TABLE, FINISHED_CONTENT_TABLE, VIRAL_TOPIC_TABLE, PRODUCTION_SCHEDULE_TABLE
    data = json.loads(Path(config_path).expanduser().read_text(encoding="utf-8"))
    base = data.get("base", {})
    BASE_TOKEN = base.get("base_token")
    BASE_URL = base.get("url")
    tables = base.get("tables", {})
    MATERIAL_TABLE = tables.get("materials")
    TOPIC_TABLE = tables.get("topics")
    FINISHED_CONTENT_TABLE = tables.get("finished")
    VIRAL_TOPIC_TABLE = tables.get("viral_topics")
    PRODUCTION_SCHEDULE_TABLE = tables.get("schedules")


_apply_user_base_config()

MATERIAL_FIELDS = {
    "title": "VA7 选题灵感库",
    "type": "类型",
    "source_url": "来源链接",
    "summary": "内容摘要",
    "quotes": "金句",
    "tags": "标签",
    "status": "状态",
    "date": "添加日期",
    "linked_topics": "关联选题",
    "topic_type": "选题类型",
}

TOPIC_FIELDS = {
    "title": "选题标题",
    "angle": "选题角度",
    "cognitive_density": "认知密度",
    "potential": "潜力等级",
    "script": "口播草稿",
    "human_hook": "人性钩子",
    "platforms": "目标平台",
    "tags": "标签",
    "created_at": "创建日期",
    "source_material": "来源素材",
    "topic_type": "选题类型",
    "todo": "待做",
    # Kept for compatibility with old drafts. The live topic table currently
    # has no 状态 field, so this is skipped unless the field reappears.
    "status": "状态",
}

MATERIAL_AUDIT_FIELDS = [
    "VA7 选题灵感库",
    "类型",
    "来源链接",
    "内容摘要",
    "金句",
    "标签",
    "状态",
    "关联选题",
    "添加日期",
    "选题类型",
]

TOPIC_AUDIT_FIELDS = [
    "选题标题",
    "选题角度",
    "认知密度",
    "潜力等级",
    "口播草稿",
    "人性钩子",
    "目标平台",
    "标签",
    "来源素材",
    "创建日期",
    "选题类型",
    "待做",
]

VIRAL_AUDIT_FIELDS = [
    "选题标题",
    "来源链接",
    "来源平台",
    "系列",
    "爆款数据",
    "为什么爆",
    "可借鉴点",
    "口播草稿",
    "人性钩子",
    "认知密度",
    "潜力等级",
    "状态",
    "标签",
    "添加日期",
]

FINISHED_CONTENT_AUDIT_FIELDS = [
    "ID",
    "标题",
    "平台",
    "状态",
    "发布日期",
    "链接",
    "正文描述",
    "Hashtag",
    "口播稿全文",
    "选题类型",
    "关联内容排期",
    "封面图",
    "封面图URL",
    "IP属地",
    "视频时长(秒)",
    "点赞",
    "收藏",
    "评论",
    "分享",
    "备注",
]

PRODUCTION_SCHEDULE_AUDIT_FIELDS = [
    "内容标题",
    "视频标题",
    "备注",
    "选题类型",
    "拍摄剪辑日",
    "发布时间",
    "公众号标题",
    "平台发布记录",
    "主发布日期",
    "视频文案介绍",
    "稿子完成日",
    "公众号排版稿",
    "关联选题",
]

FINISHED_CONTENT_FIELD_POLICY = {
    "ID": "system",
    "标题": "required",
    "平台": "required",
    "状态": "required",
    "发布日期": "required_after_publish",
    "链接": "required_after_publish",
    "正文描述": "required_after_publish",
    "Hashtag": "recommended",
    "口播稿全文": "required_after_publish",
    "选题类型": "required_after_publish",
    "关联内容排期": "required_after_publish",
    "封面图": "recoverable_platform_asset",
    "封面图URL": "recoverable_platform_asset_url",
    "IP属地": "recoverable_platform_metadata",
    "视频时长(秒)": "recommended_after_publish",
    "点赞": "metrics",
    "收藏": "metrics",
    "评论": "metrics",
    "分享": "metrics",
    "备注": "provenance",
}

PRODUCTION_SCHEDULE_FIELD_POLICY = {
    "内容标题": "required",
    "视频标题": "required_for_video_publish",
    "备注": "provenance",
    "选题类型": "required_when_scheduled_or_published",
    "拍摄剪辑日": "planning_optional",
    "发布时间": "required_when_scheduled_or_published",
    "主发布日期": "required_when_scheduled_or_published",
    "视频文案介绍": "required_for_video_publish",
    "平台发布记录": "required_after_publish",
    "关联选题": "recommended_for_planned_topic",
    "稿子完成日": "planning_optional",
    "公众号标题": "公众号_optional",
    "公众号排版稿": "公众号_optional",
    "公众号摘要": "公众号_optional",
    "公众号封面图": "公众号_optional_asset",
    "封面标题": "cover_optional",
    "横版4:3封面": "cover_optional_asset",
    "横版16:9封面": "cover_optional_asset",
    "竖版3:4封面": "cover_optional_asset",
}

FINISHED_HISTORY_RECOVERY_RULES = [
    {
        "title_contains": "花100w做ai却没效果",
        "topic_type": "专业性",
        "start_marker": "为什么老板花了上百万，AI 还是落不了地？",
        "end_markers": ["\n你看下", "\n你存档", "\n这是我最终"],
        "required_terms": ["传统数字化", "最小闭环", "Agent 进入业务现场"],
    },
    {
        "title_contains": "分享打造AI原生组织",
        "topic_type": "专业性",
        "start_marker": "到底怎么转型成 AI 原生团队、怎么做 FDE？",
        "end_markers": ["\n这是我最终的版本", "\n你存档"],
        "required_terms": ["FDE", "Agentic FDE", "自我进化"],
    },
]

TIKHUB_CONFIG_CANDIDATES = [
    Path("/Users/va7/Downloads/tikhub-xiaohongshu/config.json"),
    Path("/Users/va7/Downloads/content-skills-temp/tikhub-xiaohongshu/config.json"),
]
TIKHUB_BASE_URL = "https://api.tikhub.io"
TIKHUB_NOTE_ENDPOINTS = [
    "/api/v1/xiaohongshu/app_v2/get_image_note_detail",
    "/api/v1/xiaohongshu/app/get_note_info",
]
TIKHUB_USER_NOTES_ENDPOINTS = [
    "/api/v1/xiaohongshu/app_v2/get_user_posted_notes",
    "/api/v1/xiaohongshu/app/get_user_notes",
]
TIKHUB_VA7_USER_ID = "5bfd693851783a4917f40d5a"

IP_LOCATION_MAP = {
    "beijing": "北京",
    "shanghai": "上海",
    "tianjin": "天津",
    "chongqing": "重庆",
    "hebei": "河北",
    "shanxi": "山西",
    "liaoning": "辽宁",
    "jilin": "吉林",
    "heilongjiang": "黑龙江",
    "jiangsu": "江苏",
    "zhejiang": "浙江",
    "anhui": "安徽",
    "fujian": "福建",
    "jiangxi": "江西",
    "shandong": "山东",
    "henan": "河南",
    "hubei": "湖北",
    "hunan": "湖南",
    "guangdong": "广东",
    "hainan": "海南",
    "sichuan": "四川",
    "guizhou": "贵州",
    "yunnan": "云南",
    "shaanxi": "陕西",
    "shaanxi province": "陕西",
    "gansu": "甘肃",
    "qinghai": "青海",
    "taiwan": "台湾",
    "inner mongolia": "内蒙古",
    "neimenggu": "内蒙古",
    "guangxi": "广西",
    "tibet": "西藏",
    "xizang": "西藏",
    "ningxia": "宁夏",
    "xinjiang": "新疆",
    "hong kong": "香港",
    "hongkong": "香港",
    "macau": "澳门",
    "macao": "澳门",
    "united states": "美国",
    "usa": "美国",
    "us": "美国",
    "japan": "日本",
    "singapore": "新加坡",
}

SELECT_ALIAS = {
    "潜力等级": {
        "高": "🔥高潜力",
        "高潜力": "🔥高潜力",
        "🔥 高潜力": "🔥高潜力",
        "🔥高潜力": "🔥高潜力",
        "中": "⚠️中等潜力",
        "中等": "⚠️中等潜力",
        "中等潜力": "⚠️中等潜力",
        "⚠️ 中等": "⚠️中等潜力",
        "⚠️ 中等潜力": "⚠️中等潜力",
        "⚠️中等": "⚠️中等潜力",
        "⚠️中等潜力": "⚠️中等潜力",
        "素材": "💡素材向",
        "素材向": "💡素材向",
        "💡 素材向": "💡素材向",
        "💡素材向": "💡素材向",
    },
    "认知密度": {
        "高": "高",
        "中高": "中高",
        "中": "中",
        "低": "低",
    },
    "类型": {
        "会议": "会议洞察",
        "会议洞察": "会议洞察",
        "外部": "外部内容",
        "外部内容": "外部内容",
    },
    "状态": {
        "未拆解": "未拆解",
        "待拆解": "待拆解",
        "已拆解": "已拆解",
        "已用完": "已用完",
        "已用": "已用",
    },
}

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".jsonl",
    ".csv",
    ".srt",
    ".vtt",
}

MEDIA_EXTENSIONS = {
    ".mp3",
    ".m4a",
    ".wav",
    ".aac",
    ".flac",
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
}


class PipelineError(RuntimeError):
    """A user-actionable pipeline failure."""


class SchemaError(PipelineError):
    """A Feishu schema or cell-value mismatch."""


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
        if tag in {"p", "br", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1
        if tag in {"p", "div", "section", "article", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            text = data.strip()
            if text:
                self.parts.append(text)

    def text(self) -> str:
        joined = " ".join(self.parts)
        joined = html.unescape(joined)
        joined = re.sub(r"[ \t\r\f\v]+", " ", joined)
        joined = re.sub(r"\n\s+", "\n", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        return joined.strip()


@dataclass
class FieldInfo:
    name: str
    field_id: str
    type: str
    multiple: bool = False
    style: dict[str, Any] | None = None
    options: list[str] | None = None
    link_table: str | None = None


@dataclass
class TableSchema:
    table_id: str
    fields: dict[str, FieldInfo]

    def has(self, name: str) -> bool:
        return name in self.fields

    def get(self, name: str) -> FieldInfo:
        try:
            return self.fields[name]
        except KeyError as exc:
            raise SchemaError(f"Field not found in {self.table_id}: {name}") from exc


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def extract_json(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        raise PipelineError("Command returned empty output; expected JSON.")
    start = text.find("{")
    if start == -1:
        start = text.find("[")
    if start == -1:
        raise PipelineError(f"Could not locate JSON in output:\n{text[:1000]}")
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Could not parse JSON output:\n{text[:2000]}") from exc


def run_cmd(
    cmd: list[str] | str,
    *,
    shell: bool = False,
    timeout: int = 120,
    check: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    shown = cmd if isinstance(cmd, str) else " ".join(shlex.quote(x) for x in cmd)
    proc = subprocess.run(
        cmd,
        shell=shell,
        text=True,
        input=input_text,
        capture_output=True,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise PipelineError(
            f"Command failed ({proc.returncode}): {shown}\n"
            f"STDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-3000:]}"
        )
    return proc


def run_json(cmd: list[str], *, timeout: int = 120) -> dict[str, Any]:
    proc = run_cmd(cmd, timeout=timeout)
    data = extract_json(proc.stdout)
    if isinstance(data, dict) and data.get("ok") is False:
        raise PipelineError(json.dumps(data.get("error") or data, ensure_ascii=False, indent=2))
    if not isinstance(data, dict):
        raise PipelineError(f"Expected JSON object, got: {type(data).__name__}")
    return data


def lark_error_from_data(data: dict[str, Any]) -> str:
    ignored_fields = ((data.get("data") or {}).get("record") or {}).get("ignored_fields")
    if ignored_fields:
        return "Lark ignored fields: " + json.dumps(ignored_fields, ensure_ascii=False)
    ignored_fields = (data.get("data") or {}).get("ignored_fields")
    if ignored_fields:
        return "Lark ignored fields: " + json.dumps(ignored_fields, ensure_ascii=False)
    return ""


def run_lark(
    args: list[str],
    *,
    dry_run: bool = False,
    timeout: int = 120,
    fail_on_ignored_fields: bool = False,
) -> dict[str, Any]:
    cmd = ["lark-cli", *args]
    if dry_run:
        cmd.append("--dry-run")
    proc = run_cmd(cmd, timeout=timeout)
    data = extract_json(proc.stdout)
    if isinstance(data, dict) and data.get("ok") is False:
        raise PipelineError(json.dumps(data.get("error") or data, ensure_ascii=False, indent=2))
    if fail_on_ignored_fields and isinstance(data, dict):
        ignored_error = lark_error_from_data(data)
        if ignored_error:
            raise PipelineError(ignored_error)
    return data


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise PipelineError(f"Missing required command: {name}")
    return path


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def now_ms() -> int:
    return int(time.time() * 1000)


def parse_date_ms(value: Any) -> int:
    if value in (None, ""):
        return now_ms()
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            parsed = dt.datetime.strptime(text, fmt)
            return int(parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo).timestamp() * 1000)
        except ValueError:
            pass
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        return int(parsed.timestamp() * 1000)
    except ValueError as exc:
        raise SchemaError(f"Could not parse date value: {value!r}") from exc


def as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        if "," in value:
            return [x.strip() for x in value.split(",") if x.strip()]
        return [value]
    return [value]


def compact_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(compact_text(item) for item in value if compact_text(item))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def slugify(value: str, fallback: str = "material") -> str:
    text = re.sub(r"https?://", "", value.strip())
    text = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", text)
    text = text.strip("-._")
    return (text[:80] or fallback)


def normalize_url(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, dict):
        return str(value.get("link") or value.get("url") or value.get("text") or "")
    text = str(value).strip()
    markdown_match = re.match(r"^\[[^\]]+\]\((https?://[^)]+)\)$", text)
    if markdown_match:
        return markdown_match.group(1)
    url_match = re.search(r"https?://[^\s)>\]]+", text)
    if url_match:
        return url_match.group(0)
    return text


def date_from_text(value: Any) -> str:
    text = compact_text(value)
    if not text:
        return ""
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if not match:
        return ""
    year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    try:
        return dt.date(year, month, day).isoformat()
    except ValueError:
        return ""


def strip_select_reason(value: str) -> str:
    text = str(value).strip()
    for sep in ("（", "(", "：", ":", " - ", " — ", "，", ","):
        if sep in text:
            head = text.split(sep, 1)[0].strip()
            if head:
                return head
    return text


def normalize_option(
    field: FieldInfo,
    value: Any,
    *,
    allow_new_tag: bool = True,
    warnings: list[str],
) -> str:
    raw = compact_text(value)
    if not raw:
        return ""
    options = field.options or []
    if raw in options:
        return raw

    alias = SELECT_ALIAS.get(field.name, {})
    stripped = strip_select_reason(raw)
    candidates = [raw, stripped, raw.replace(" ", ""), stripped.replace(" ", "")]
    for candidate in candidates:
        mapped = alias.get(candidate)
        if mapped and mapped in options:
            if mapped != raw:
                warnings.append(f"{field.name}: normalized {raw!r} -> {mapped!r}")
            return mapped
        if candidate in options:
            if candidate != raw:
                warnings.append(f"{field.name}: normalized {raw!r} -> {candidate!r}")
            return candidate

    folded = raw.replace(" ", "")
    for option in options:
        if option.replace(" ", "") == folded:
            warnings.append(f"{field.name}: normalized {raw!r} -> {option!r}")
            return option

    if field.name == "潜力等级":
        for marker in ("高潜力", "中等", "素材向"):
            if marker in raw:
                for option in options:
                    if marker in option:
                        warnings.append(f"{field.name}: normalized {raw!r} -> {option!r}")
                        return option

    if field.name == "认知密度" and stripped in options:
        warnings.append(f"{field.name}: removed reason from {raw!r} -> {stripped!r}")
        return stripped

    if field.name == "标签" and allow_new_tag:
        warnings.append(f"{field.name}: option {raw!r} not found; sending as new option")
        return raw

    raise SchemaError(
        f"Invalid option for {field.name}: {raw!r}. "
        f"Allowed: {', '.join(options) if options else '(no options returned)'}"
    )


def coerce_cell(
    schema: TableSchema,
    field_name: str,
    value: Any,
    *,
    allow_new_tag: bool,
    warnings: list[str],
) -> Any:
    field = schema.get(field_name)
    if value is None:
        return None
    if field.type == "formula":
        raise SchemaError(f"Cannot write formula field: {field_name}")
    if field.type == "datetime":
        return parse_date_ms(value)
    if field.type == "checkbox":
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "y", "是", "待做"}
    if field.type == "link":
        ids: list[str] = []
        for item in as_list(value):
            if isinstance(item, dict):
                item = item.get("record_id") or item.get("id")
            text = str(item or "").strip()
            if text:
                ids.append(text)
        if not ids:
            return None
        return ids
    if field.type == "select":
        if field.multiple:
            values = [
                normalize_option(field, item, allow_new_tag=allow_new_tag, warnings=warnings)
                for item in as_list(value)
                if compact_text(item)
            ]
            return values or None
        return normalize_option(field, value, allow_new_tag=allow_new_tag, warnings=warnings)
    if field.type == "text":
        if (field.style or {}).get("type") == "url":
            return normalize_url(value)
        return compact_text(value)
    if field.type == "number":
        if value in ("", None):
            return None
        return float(value)
    return value


def get_table_schema(table_id: str) -> TableSchema:
    data = run_lark(
        [
            "base",
            "+field-list",
            "--base-token",
            BASE_TOKEN,
            "--table-id",
            table_id,
            "--limit",
            "200",
        ]
    )
    fields: dict[str, FieldInfo] = {}
    for raw in data.get("data", {}).get("fields", []):
        name = str(raw.get("name") or "")
        if not name:
            continue
        fields[name] = FieldInfo(
            name=name,
            field_id=str(raw.get("id") or ""),
            type=str(raw.get("type") or ""),
            multiple=bool(raw.get("multiple")),
            style=raw.get("style") if isinstance(raw.get("style"), dict) else None,
            options=[str(item.get("name")) for item in raw.get("options", []) if item.get("name")],
            link_table=raw.get("link_table"),
        )
    return TableSchema(table_id=table_id, fields=fields)


def schema_to_json(schema: TableSchema) -> dict[str, Any]:
    return {
        "table_id": schema.table_id,
        "fields": [
            {
                "name": field.name,
                "id": field.field_id,
                "type": field.type,
                "multiple": field.multiple,
                "style": field.style,
                "options": field.options or [],
                "link_table": field.link_table,
            }
            for field in schema.fields.values()
        ],
    }


def load_live_schemas() -> dict[str, TableSchema]:
    return {
        "material": get_table_schema(MATERIAL_TABLE),
        "topic": get_table_schema(TOPIC_TABLE),
        "finished_content": get_table_schema(FINISHED_CONTENT_TABLE),
        "viral_topic": get_table_schema(VIRAL_TOPIC_TABLE),
        "production_schedule": get_table_schema(PRODUCTION_SCHEDULE_TABLE),
    }


def validate_expected_schema(schemas: dict[str, TableSchema], *, strict: bool = True) -> list[str]:
    warnings: list[str] = []
    required_material = [
        "VA7 选题灵感库",
        "类型",
        "来源链接",
        "内容摘要",
        "金句",
        "标签",
        "状态",
        "添加日期",
        "关联选题",
    ]
    required_topic = [
        "选题标题",
        "选题角度",
        "认知密度",
        "潜力等级",
        "口播草稿",
        "人性钩子",
        "目标平台",
        "标签",
        "创建日期",
        "来源素材",
    ]
    required_finished_content = [
        "标题",
        "平台",
        "状态",
        "发布日期",
        "链接",
        "正文描述",
        "关联内容排期",
    ]
    missing: list[str] = []
    for field in required_material:
        if not schemas["material"].has(field):
            missing.append(f"material.{field}")
    for field in required_topic:
        if not schemas["topic"].has(field):
            missing.append(f"topic.{field}")
    for field in required_finished_content:
        if not schemas["finished_content"].has(field):
            missing.append(f"finished_content.{field}")
    if missing and strict:
        raise SchemaError("Missing required Feishu fields: " + ", ".join(missing))
    for item in missing:
        warnings.append("missing optional/required field: " + item)

    topic_status = TOPIC_FIELDS["status"]
    if not schemas["topic"].has(topic_status):
        warnings.append("topic table has no 状态 field; upload will not write topic status")

    source_field = schemas["material"].fields.get("来源链接")
    if source_field and source_field.type == "text":
        warnings.append("material 来源链接 is text(style=url); script writes a plain URL string")
    return warnings


def fetch_url(url: str, timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 va7-library-ingest/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        content_type = response.headers.get("content-type", "")
    charset = "utf-8"
    match = re.search(r"charset=([^;]+)", content_type)
    if match:
        charset = match.group(1).strip()
    text = raw.decode(charset, errors="replace")
    if "html" in content_type or "<html" in text[:500].lower():
        parser = TextExtractor()
        parser.feed(text)
        plain = parser.text()
    else:
        plain = text.strip()
    title = url
    title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    if title_match:
        title = html.unescape(re.sub(r"\s+", " ", title_match.group(1))).strip()
    return {
        "source_type": "url",
        "source_url": url,
        "title": title,
        "text": plain,
        "fetched_at": now_ms(),
    }


def fetch_feishu_doc(doc: str) -> dict[str, Any]:
    data = run_lark(["docs", "+fetch", "--doc", doc, "--format", "json"], timeout=120)
    payload = data.get("data") or {}
    text = (
        payload.get("markdown")
        or payload.get("content")
        or payload.get("text")
        or json.dumps(payload, ensure_ascii=False)
    )
    title = payload.get("title") or payload.get("name") or doc
    return {
        "source_type": "feishu_doc",
        "source_url": doc if doc.startswith("http") else "",
        "title": str(title),
        "text": compact_text(text),
        "raw": payload,
        "fetched_at": now_ms(),
    }


def load_tikhub_config(config_path: str | None = None) -> dict[str, Any]:
    candidates: list[Path] = []
    if config_path:
        candidates.append(Path(config_path).expanduser())
    env_config = os.environ.get("TIKHUB_CONFIG")
    if env_config:
        candidates.append(Path(env_config).expanduser())
    candidates.extend(TIKHUB_CONFIG_CANDIDATES)

    config: dict[str, Any] = {}
    used_path = ""
    for path in candidates:
        if not path.exists():
            continue
        try:
            loaded = read_json(path)
        except Exception as exc:  # noqa: BLE001 - report bad config as actionable
            raise PipelineError(f"Could not read TikHub config {path}: {exc}") from exc
        if isinstance(loaded, dict):
            config.update(loaded)
            used_path = str(path)
            break

    api_key = os.environ.get("TIKHUB_API_KEY") or str(config.get("api_key") or "").strip()
    if not api_key:
        raise PipelineError(
            "TikHub API key not configured. Set TIKHUB_API_KEY or provide --tikhub-config with api_key."
        )
    base_url = os.environ.get("TIKHUB_BASE_URL") or str(config.get("base_url") or TIKHUB_BASE_URL)
    return {"api_key": api_key, "base_url": base_url.rstrip("/"), "config_path": used_path}


def tikhub_cache_path(endpoint: str, params: dict[str, Any], cache_dir: Path) -> Path:
    key = f"{endpoint}:{json.dumps(params, sort_keys=True, ensure_ascii=False)}"
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
    name = endpoint.strip("/").split("/")[-1] or "request"
    return cache_dir / dt.datetime.now().strftime("%Y-%m-%d") / f"{name}_{digest}.json"


def tikhub_request(
    endpoint: str,
    params: dict[str, Any],
    *,
    config: dict[str, Any],
    cache_dir: Path,
    use_cache: bool = True,
    timeout: int = 45,
) -> dict[str, Any]:
    cache_path = tikhub_cache_path(endpoint, params, cache_dir)
    if use_cache and cache_path.exists():
        cached = read_json(cache_path)
        if isinstance(cached, dict):
            cached["_from_cache"] = True
            cached["_cache_file"] = str(cache_path)
            return cached

    query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
    url = f"{config['base_url']}{endpoint}"
    if query:
        url = f"{url}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
            "User-Agent": "va7-library-tikhub-repair/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise PipelineError(f"TikHub HTTP {exc.code} for {endpoint}: {body[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise PipelineError(f"TikHub network error for {endpoint}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"TikHub returned non-JSON response for {endpoint}") from exc

    result = {"success": True, "data": payload, "_cache_file": str(cache_path)}
    if use_cache:
        write_json(cache_path, result)
    return result


def fetch_tikhub_note(
    url: str,
    *,
    config: dict[str, Any],
    cache_dir: Path,
    use_cache: bool,
) -> dict[str, Any]:
    params = {"share_text": url}
    errors: list[str] = []
    for endpoint in TIKHUB_NOTE_ENDPOINTS:
        try:
            result = tikhub_request(endpoint, params, config=config, cache_dir=cache_dir, use_cache=use_cache)
        except PipelineError as exc:
            errors.append(str(exc))
            continue
        if result.get("success"):
            result["_endpoint"] = endpoint
            return result
        errors.append(str(result.get("error") or result)[:1000])
    raise PipelineError(f"TikHub note fetch failed for {url}: {'; '.join(errors)}")


def fetch_tikhub_user_notes(
    user_id: str,
    *,
    config: dict[str, Any],
    cache_dir: Path,
    use_cache: bool,
    pages: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    notes_by_id: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for endpoint in TIKHUB_USER_NOTES_ENDPOINTS:
        cursor = ""
        for _page in range(max(1, pages)):
            params = {"user_id": user_id}
            if cursor:
                params["cursor"] = cursor
            try:
                response = tikhub_request(endpoint, params, config=config, cache_dir=cache_dir, use_cache=use_cache)
            except PipelineError as exc:
                warnings.append(f"{endpoint}: {exc}")
                break
            page_notes = find_tikhub_user_notes(response)
            if not page_notes:
                if not notes_by_id:
                    warnings.append(f"{endpoint}: no notes found")
                break
            for note in page_notes:
                note_id = tikhub_note_id(note)
                if note_id and note_id not in notes_by_id:
                    note["_endpoint"] = endpoint
                    note["_cache_file"] = response.get("_cache_file")
                    notes_by_id[note_id] = note
            next_cursor = tikhub_next_cursor(response, page_notes)
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        if notes_by_id:
            break
    return list(notes_by_id.values()), warnings


def find_tikhub_user_notes(value: Any) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key in ("notes", "note_list", "items", "list"):
            items = value.get(key)
            if isinstance(items, list):
                notes.extend(item for item in items if isinstance(item, dict) and tikhub_note_id(item))
        for item in value.values():
            notes.extend(find_tikhub_user_notes(item))
    elif isinstance(value, list):
        for item in value:
            notes.extend(find_tikhub_user_notes(item))
    deduped: dict[str, dict[str, Any]] = {}
    for note in notes:
        note_id = tikhub_note_id(note)
        if note_id and note_id not in deduped:
            deduped[note_id] = note
    return list(deduped.values())


def tikhub_next_cursor(response: dict[str, Any], notes: list[dict[str, Any]]) -> str:
    for key in ("cursor", "next_cursor", "last_cursor"):
        found = find_scalar_key(response, key)
        if found:
            return found
    if notes:
        return compact_text(notes[-1].get("cursor") or tikhub_note_id(notes[-1]))
    return ""


def find_scalar_key(value: Any, key: str) -> str:
    if isinstance(value, dict):
        if key in value and not isinstance(value.get(key), (dict, list)):
            return compact_text(value.get(key))
        for item in value.values():
            found = find_scalar_key(item, key)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_scalar_key(item, key)
            if found:
                return found
    return ""


def find_tikhub_note(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        note_list = value.get("note_list")
        if isinstance(note_list, list) and note_list:
            first = note_list[0]
            if isinstance(first, dict):
                return first
        if {"images_list", "ip_location"} & set(value):
            return value
        for item in value.values():
            found = find_tikhub_note(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_tikhub_note(item)
            if found:
                return found
    return None


def tikhub_note_id(note: dict[str, Any]) -> str:
    return compact_text(note.get("id") or note.get("note_id") or note.get("cursor"))


def tikhub_note_title(note: dict[str, Any]) -> str:
    return compact_text(note.get("title") or note.get("display_title"))


def tikhub_note_desc(note: dict[str, Any]) -> str:
    return compact_text(note.get("desc") or note.get("description") or note.get("content"))


def tikhub_note_url(note: dict[str, Any]) -> str:
    note_id = tikhub_note_id(note)
    return f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else ""


def tikhub_note_created_at(note: dict[str, Any]) -> str:
    raw = note.get("create_time") or note.get("time")
    if isinstance(raw, (int, float)) and raw > 0:
        if raw > 10_000_000_000:
            raw = raw / 1000
        return dt.datetime.fromtimestamp(raw).strftime("%Y-%m-%d %H:%M:%S")
    return ""


def tikhub_note_video_duration(note: dict[str, Any]) -> int | float | None:
    for path in [
        ("video_info_v2", "capa", "duration"),
        ("video_info_v2", "media", "video", "duration"),
        ("video", "duration"),
    ]:
        value: Any = note
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, (int, float)) and value > 0:
            return round(value / 1000) if value > 10000 else value
    return None


def tikhub_note_likes(note: dict[str, Any]) -> Any:
    return note.get("likes") if note.get("likes") is not None else note.get("liked_count")


def normalize_xhs_ip_location(value: Any) -> str:
    text = compact_text(value)
    if not text:
        return ""
    text = text.replace("IP属地：", "").replace("IP属地:", "").strip()
    if re.search(r"[\u4e00-\u9fff]", text):
        return text
    folded = re.sub(r"[_-]+", " ", text).strip().lower()
    return IP_LOCATION_MAP.get(folded, text)


def first_url_from_value(value: Any) -> str:
    if isinstance(value, str):
        return normalize_url(value)
    if isinstance(value, dict):
        for key in ("original", "high", "url", "thumb", "image", "link"):
            if key in value:
                url = first_url_from_value(value.get(key))
                if url:
                    return url
        for item in value.values():
            url = first_url_from_value(item)
            if url:
                return url
    if isinstance(value, list):
        for item in value:
            url = first_url_from_value(item)
            if url:
                return url
    return ""


def tikhub_cover_url(note: dict[str, Any]) -> str:
    candidates = tikhub_cover_url_candidates(note)
    return candidates[0] if candidates else ""


def tikhub_cover_url_candidates(note: dict[str, Any]) -> list[str]:
    urls: list[str] = []

    def add(value: Any) -> None:
        url = first_url_from_value(value)
        if url:
            urls.append(url)

    images = note.get("images_list")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            for path in [
                ("original",),
                ("url_multi_level", "high"),
                ("url_multi_level", "medium"),
                ("url",),
            ]:
                value: Any = first
                for key in path:
                    value = value.get(key) if isinstance(value, dict) else None
                add(value)
    for path in [
        ("mini_program_info", "thumb"),
        ("share_info", "image"),
        ("cover",),
        ("image",),
    ]:
        value = note
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        add(value)
    return unique_keep_order(urls)


def extension_from_response(url: str, content_type: str) -> str:
    parsed = urllib.parse.urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return suffix
    content_type = content_type.lower()
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    if "gif" in content_type:
        return ".gif"
    return ".jpg"


def download_tikhub_cover(url: str, out_dir: Path, record_id: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 va7-library-tikhub-repair/1.0",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Referer": "https://www.xiaohongshu.com/",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            content_type = response.headers.get("content-type", "")
    except urllib.error.URLError as exc:
        raise PipelineError(f"Could not download TikHub cover for {record_id}: {exc}") from exc
    if not raw:
        raise PipelineError(f"Downloaded empty TikHub cover for {record_id}: {url}")
    ext = extension_from_response(url, content_type)
    path = out_dir / f"{record_id}{ext}"
    path.write_bytes(raw)
    return path


def download_first_tikhub_cover(urls: list[str], out_dir: Path, record_id: str) -> tuple[Path | None, list[str]]:
    errors: list[str] = []
    for url in urls:
        try:
            return download_tikhub_cover(url, out_dir, record_id), errors
        except PipelineError as exc:
            errors.append(str(exc))
    return None, errors


def upload_attachment(
    table_id: str,
    record_id: str,
    field_name: str,
    file_path: Path,
    *,
    name: str | None = None,
    dry_run: bool,
) -> None:
    args = [
        "base",
        "+record-upload-attachment",
        "--base-token",
        BASE_TOKEN,
        "--table-id",
        table_id,
        "--record-id",
        record_id,
        "--field-id",
        field_name,
        "--file",
        str(file_path),
    ]
    if name:
        version = run_cmd(["lark-cli", "--version"], timeout=30, check=False).stdout
        match = re.search(r"(\d+)\.(\d+)\.(\d+)", version)
        version_tuple = tuple(int(part) for part in match.groups()) if match else (0, 0, 0)
        if version_tuple < (1, 0, 53):
            args.extend(["--name", name])
    run_lark(args, dry_run=dry_run, timeout=180, fail_on_ignored_fields=True)


def ensure_text_field(table_id: str, schema: TableSchema, field_name: str, *, dry_run: bool) -> bool:
    if schema.has(field_name):
        return True
    run_lark(
        [
            "base",
            "+field-create",
            "--base-token",
            BASE_TOKEN,
            "--table-id",
            table_id,
            "--json",
            json.dumps({"name": field_name, "type": "text"}, ensure_ascii=False),
        ],
        dry_run=dry_run,
        timeout=120,
    )
    if dry_run:
        return False
    refreshed = get_table_schema(table_id)
    schema.fields = refreshed.fields
    return schema.has(field_name)


def read_local_material(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix not in TEXT_EXTENSIONS:
        raise PipelineError(f"Unsupported text input extension: {suffix}")
    text = path.read_text(encoding="utf-8", errors="replace")
    items: list[dict[str, Any]] = []
    if suffix == ".jsonl":
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    items.append(item)
            except json.JSONDecodeError:
                pass
    elif suffix == ".json":
        try:
            data = json.loads(text)
            if isinstance(data, list):
                items = [item for item in data if isinstance(item, dict)]
            elif isinstance(data, dict):
                for key in ("data", "items", "tweets", "posts", "results"):
                    if isinstance(data.get(key), list):
                        items = [item for item in data[key] if isinstance(item, dict)]
                        break
                else:
                    items = [data]
        except json.JSONDecodeError:
            pass
    joined = normalize_items_to_text(items) if items else text
    return {
        "source_type": "file",
        "source_url": str(path),
        "title": path.stem,
        "text": compact_text(joined),
        "items": items,
        "fetched_at": now_ms(),
    }


def normalize_items_to_text(items: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for index, item in enumerate(items, start=1):
        text = (
            item.get("text")
            or item.get("full_text")
            or item.get("content")
            or item.get("body")
            or item.get("markdown")
            or ""
        )
        if not compact_text(text):
            text = json.dumps(item, ensure_ascii=False)
        url = item.get("url") or item.get("source_url") or item.get("link") or ""
        created = item.get("created_at") or item.get("date") or ""
        metrics = item.get("public_metrics") or item.get("metrics") or {}
        header = f"[{index}]"
        if created:
            header += f" {created}"
        if url:
            header += f" {url}"
        if metrics:
            header += " " + json.dumps(metrics, ensure_ascii=False)
        parts.append(header + "\n" + compact_text(text))
    return "\n\n".join(parts)


def fetch_x_with_api(handle: str, limit: int) -> dict[str, Any]:
    token = os.environ.get("X_BEARER_TOKEN") or os.environ.get("TWITTER_BEARER_TOKEN")
    if not token:
        raise PipelineError("X_BEARER_TOKEN is not set.")
    clean_handle = handle.lstrip("@")
    api_base = os.environ.get("X_API_BASE", "https://api.twitter.com/2").rstrip("/")

    def request_json(url: str) -> dict[str, Any]:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "va7-library-ingest/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise PipelineError(f"X API request failed: HTTP {exc.code}\n{body}") from exc

    user_url = (
        api_base
        + "/users/by/username/"
        + urllib.parse.quote(clean_handle)
        + "?user.fields=description,public_metrics,url,verified"
    )
    user = request_json(user_url).get("data") or {}
    user_id = user.get("id")
    if not user_id:
        raise PipelineError(f"Could not resolve X handle: {handle}")
    max_results = min(max(limit, 5), 100)
    params = urllib.parse.urlencode(
        {
            "max_results": str(max_results),
            "tweet.fields": "created_at,public_metrics,entities,referenced_tweets",
            "exclude": "retweets,replies",
        }
    )
    tweets_url = f"{api_base}/users/{user_id}/tweets?{params}"
    tweets_data = request_json(tweets_url)
    items = tweets_data.get("data") or []
    for item in items:
        item["url"] = f"https://x.com/{clean_handle}/status/{item.get('id')}"
    return {
        "source_type": "x_api",
        "source_url": f"https://x.com/{clean_handle}",
        "title": f"@{clean_handle} recent X posts",
        "author": user,
        "items": items,
        "text": normalize_items_to_text(items),
        "fetched_at": now_ms(),
    }


def fetch_x_with_external(handle: str, limit: int, out_dir: Path) -> dict[str, Any]:
    template = os.environ.get("INSPIRATION_X_FETCH_CMD") or os.environ.get("INSPIRATION_T_FETCH_CMD")
    if not template:
        raise PipelineError(
            "No X fetch backend configured. Set X_BEARER_TOKEN for X API v2, "
            "or set INSPIRATION_X_FETCH_CMD with placeholders {handle}, {limit}, {out}."
        )
    out = out_dir / f"x-{handle.lstrip('@')}.jsonl"
    command = template.format(handle=shlex.quote(handle.lstrip("@")), limit=limit, out=shlex.quote(str(out)))
    proc = run_cmd(command, shell=True, timeout=300, check=True)
    if out.exists() and out.stat().st_size:
        material = read_local_material(out)
    else:
        text = proc.stdout.strip()
        if not text:
            raise PipelineError("External X fetch command produced no file and no stdout.")
        stdout_file = out_dir / f"x-{handle.lstrip('@')}-stdout.txt"
        write_text(stdout_file, text)
        material = read_local_material(stdout_file)
    material["source_type"] = "x_external"
    material["source_url"] = f"https://x.com/{handle.lstrip('@')}"
    material["title"] = f"@{handle.lstrip('@')} X posts"
    return material


def fetch_x(handle: str, limit: int, out_dir: Path) -> dict[str, Any]:
    if os.environ.get("X_BEARER_TOKEN") or os.environ.get("TWITTER_BEARER_TOKEN"):
        return fetch_x_with_api(handle, limit)
    return fetch_x_with_external(handle, limit, out_dir)


def command_fetch(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.url:
        material = fetch_url(args.url)
    elif args.feishu_doc:
        material = fetch_feishu_doc(args.feishu_doc)
    elif args.x_handle:
        material = fetch_x(args.x_handle, args.limit, out_dir)
    elif args.input_file:
        material = read_local_material(Path(args.input_file).expanduser())
    else:
        raise PipelineError("Provide one of --url, --feishu-doc, --x-handle, --input-file.")
    out = Path(args.out).expanduser() if args.out else out_dir / "material.json"
    write_json(out, material)
    print(json.dumps({"ok": True, "material": str(out), "chars": len(material.get("text") or "")}, ensure_ascii=False))
    return 0


def command_prepare_audio(args: argparse.Namespace) -> int:
    require_tool("ffmpeg")
    src = Path(args.input).expanduser()
    if not src.exists():
        raise PipelineError(f"Input media file not found: {src}")
    out = Path(args.out).expanduser()
    ensure_parent(out)
    run_cmd(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-vn",
            "-i",
            str(src),
            "-map",
            "0:a:0",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(out),
        ],
        timeout=600,
    )
    print(json.dumps({"ok": True, "audio": str(out)}, ensure_ascii=False))
    return 0


def parse_transcript_output(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        raise PipelineError(f"Transcript output is empty: {path}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"source_type": "transcript_text", "text": text, "segments": []}
    if isinstance(data, dict):
        if "text" not in data:
            if "segments" in data:
                data["text"] = " ".join(compact_text(seg.get("text")) for seg in data.get("segments", []))
            else:
                data["text"] = compact_text(data)
        return data
    if isinstance(data, list):
        return {"source_type": "transcript_segments", "segments": data, "text": normalize_items_to_text(data)}
    raise PipelineError(f"Unsupported transcript JSON shape in {path}")


def transcribe_external(audio: Path, out: Path) -> dict[str, Any]:
    template = os.environ.get("INSPIRATION_TRANSCRIBE_CMD")
    if not template:
        raise PipelineError(
            "INSPIRATION_TRANSCRIBE_CMD is not set. "
            "Use placeholders {audio} and {out}, or choose --provider openai."
        )
    command = template.format(audio=shlex.quote(str(audio)), out=shlex.quote(str(out)))
    proc = run_cmd(command, shell=True, timeout=3600, check=True)
    if not out.exists() or out.stat().st_size == 0:
        write_text(out, proc.stdout)
    return parse_transcript_output(out)


def transcribe_openai(audio: Path, out: Path, model: str) -> dict[str, Any]:
    require_tool("curl")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise PipelineError("OPENAI_API_KEY is not set.")
    raw = out.with_suffix(".openai.json")
    run_cmd(
        [
            "curl",
            "-sS",
            "https://api.openai.com/v1/audio/transcriptions",
            "-H",
            f"Authorization: Bearer {api_key}",
            "-F",
            f"file=@{audio}",
            "-F",
            f"model={model}",
            "-F",
            "response_format=verbose_json",
            "-o",
            str(raw),
        ],
        timeout=3600,
    )
    data = parse_transcript_output(raw)
    write_json(out, data)
    return data


def command_transcribe(args: argparse.Namespace) -> int:
    audio = Path(args.audio).expanduser()
    if not audio.exists():
        raise PipelineError(f"Audio file not found: {audio}")
    out = Path(args.out).expanduser()
    ensure_parent(out)
    provider = args.provider
    if provider == "auto":
        provider = "external" if os.environ.get("INSPIRATION_TRANSCRIBE_CMD") else "openai"
    if provider == "external":
        transcript = transcribe_external(audio, out)
    elif provider == "openai":
        transcript = transcribe_openai(audio, out, args.model)
    else:
        raise PipelineError(f"Unsupported transcription provider: {provider}")
    transcript.setdefault("source_audio", str(audio))
    transcript.setdefault("transcribed_at", now_ms())
    write_json(out, transcript)
    print(json.dumps({"ok": True, "transcript": str(out), "chars": len(transcript.get("text") or "")}, ensure_ascii=False))
    return 0


def load_material_and_transcript(material_path: Path | None, transcript_path: Path | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    material = read_json(material_path) if material_path else {}
    transcript = read_json(transcript_path) if transcript_path else None
    if transcript:
        transcript_text = compact_text(transcript.get("text"))
        material_text = compact_text(material.get("text"))
        material["text"] = "\n\n".join(x for x in [material_text, "【语音转录】\n" + transcript_text] if x)
    return material, transcript


def draft_prompt(material: dict[str, Any]) -> str:
    source_title = compact_text(material.get("title")) or "未命名素材"
    source_url = compact_text(material.get("source_url"))
    text = compact_text(material.get("text"))
    excerpt = text[:12000]
    return f"""请把下面素材整理成可入库的 JSON，只输出 JSON，不要输出解释。

硬性要求：
1. material.summary 写 5-10 个核心要点，保留具体数据、故事、案例。
2. material.quotes 写 5-10 条金句，尽量保留原话和说话人。
3. topics 至少 3 条；高密度长素材拆 5-8 条。
4. 每条 topic 的 angle 不超过 50 字，不要塞入口播草稿。
5. cognitive_density 只能是 高 / 中高 / 中 / 低。
6. potential 只能是 🔥高潜力 / ⚠️中等潜力 / 💡素材向。
7. platforms 从 小红书 / 公众号 / 视频号 中选择。
8. tags 使用已有标签优先：创业、AI、OpenClaw、跨境、方法论、内容创作、产品、商业模式、Agent架构、交付稳定性、服务标准化、企业AI落地、技能管理、Agent运维、垂直领域、Agent设计、用户体验、组织管理、数据资产、投资、培训、内容工厂、小红书、数字员工。
9. script 不是终稿，也不能写成完整口播稿。只写 200-500 字 brief seed：候选 thesis、为什么值得讲、还缺哪些 VA7 一手经验、以及 2-3 个必须采访用户的问题。
10. 如果选题需要用户立场、个人经历、数字或边界才能成立，script 必须明确写“待采访确认”，不要替用户发明立场。

JSON 结构：
{{
  "material": {{
    "title": "{json_escape(source_title)}",
    "type": "外部内容",
    "source_url": "{json_escape(source_url)}",
    "summary": "",
    "quotes": "",
    "tags": []
  }},
  "topics": [
    {{
      "title": "",
      "angle": "",
      "cognitive_density": "高",
      "potential": "🔥高潜力",
      "script": "待采访确认：候选 thesis、价值、缺失的一手证据、采访问题...",
      "human_hook": "",
      "platforms": ["小红书"],
      "tags": ["AI"],
      "topic_type": "专业性"
    }}
  ]
}}

素材：
{excerpt}
"""


def json_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def command_make_draft(args: argparse.Namespace) -> int:
    material, transcript = load_material_and_transcript(
        Path(args.material).expanduser() if args.material else None,
        Path(args.transcript).expanduser() if args.transcript else None,
    )
    title = compact_text(material.get("title")) or "未命名素材"
    out = Path(args.out).expanduser()
    prompt_out = Path(args.prompt_out).expanduser() if args.prompt_out else out.with_suffix(".prompt.md")
    draft = {
        "material": {
            "title": title,
            "type": material.get("source_type") == "feishu_doc" and "会议洞察" or "外部内容",
            "source_url": material.get("source_url") or "",
            "summary": "",
            "quotes": "",
            "tags": [],
        },
        "topics": [],
        "_source": {
            "material_file": args.material,
            "transcript_file": args.transcript,
            "source_type": material.get("source_type"),
            "source_chars": len(material.get("text") or ""),
            "has_transcript": bool(transcript),
        },
    }
    write_json(out, draft)
    write_text(prompt_out, draft_prompt(material))
    print(json.dumps({"ok": True, "draft": str(out), "prompt": str(prompt_out)}, ensure_ascii=False))
    return 0


def pick(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def normalize_draft(raw: dict[str, Any]) -> dict[str, Any]:
    material_raw = raw.get("material") or raw.get("素材") or {}
    topics_raw = raw.get("topics") or raw.get("选题") or []
    if not isinstance(material_raw, dict):
        raise PipelineError("draft.material must be an object.")
    if not isinstance(topics_raw, list):
        raise PipelineError("draft.topics must be a list.")

    material = {
        "title": pick(material_raw, "title", "VA7 选题灵感库", "素材标题"),
        "type": pick(material_raw, "type", "类型", default="外部内容"),
        "source_url": pick(material_raw, "source_url", "url", "来源链接", default=""),
        "summary": pick(material_raw, "summary", "内容摘要", default=""),
        "quotes": pick(material_raw, "quotes", "金句", default=""),
        "tags": as_list(pick(material_raw, "tags", "标签", default=[])),
        "date": pick(material_raw, "date", "添加日期", default=now_ms()),
        "topic_type": pick(material_raw, "topic_type", "选题类型", default=None),
    }
    topics: list[dict[str, Any]] = []
    for item in topics_raw:
        if not isinstance(item, dict):
            raise PipelineError("Every topic item must be an object.")
        topics.append(
            {
                "title": pick(item, "title", "选题标题"),
                "angle": pick(item, "angle", "选题角度"),
                "cognitive_density": pick(item, "cognitive_density", "认知密度"),
                "potential": pick(item, "potential", "潜力等级"),
                "script": pick(item, "script", "口播草稿"),
                "human_hook": pick(item, "human_hook", "人性钩子"),
                "platforms": as_list(pick(item, "platforms", "目标平台", default=[])),
                "tags": as_list(pick(item, "tags", "标签", default=[])),
                "created_at": pick(item, "created_at", "创建日期", default=now_ms()),
                "topic_type": pick(item, "topic_type", "选题类型", default=None),
                "status": pick(item, "status", "状态", default="待采访"),
                "todo": pick(item, "todo", "待做", default=None),
            }
        )
    return {"material": material, "topics": topics}


def validate_draft_shape(draft: dict[str, Any], *, allow_incomplete: bool = False) -> list[str]:
    warnings: list[str] = []
    material = draft["material"]
    topics = draft["topics"]
    required_material = ["title", "type", "summary", "quotes", "tags"]
    required_topic = [
        "title",
        "angle",
        "cognitive_density",
        "potential",
        "script",
        "human_hook",
        "platforms",
        "tags",
    ]
    missing: list[str] = []
    for key in required_material:
        if key == "tags":
            if not material.get(key):
                missing.append(f"material.{key}")
        elif not compact_text(material.get(key)):
            missing.append(f"material.{key}")
    if not topics:
        missing.append("topics")
    for index, topic in enumerate(topics):
        for key in required_topic:
            if key in {"platforms", "tags"}:
                if not topic.get(key):
                    missing.append(f"topics[{index}].{key}")
            elif not compact_text(topic.get(key)):
                missing.append(f"topics[{index}].{key}")
        angle = compact_text(topic.get("angle"))
        if len(angle) > 80:
            warnings.append(f"topics[{index}].angle is long ({len(angle)} chars); target <= 50 Chinese chars")
        if "（" in compact_text(topic.get("cognitive_density")) or "(" in compact_text(topic.get("cognitive_density")):
            warnings.append(f"topics[{index}].cognitive_density contains a reason; script will normalize to select option")
    if missing and not allow_incomplete:
        raise PipelineError("Draft is incomplete: " + ", ".join(missing))
    for item in missing:
        warnings.append("incomplete: " + item)
    return warnings


def validate_draft_against_schema(
    draft: dict[str, Any],
    schemas: dict[str, TableSchema],
    *,
    allow_new_tag: bool,
    allow_incomplete: bool = False,
) -> list[str]:
    warnings = validate_draft_shape(draft, allow_incomplete=allow_incomplete)
    material_schema = schemas["material"]
    topic_schema = schemas["topic"]
    for logical, field_name in MATERIAL_FIELDS.items():
        if logical in {"linked_topics"}:
            continue
        if logical in {"topic_type"} and draft["material"].get(logical) is None:
            continue
        if field_name in material_schema.fields and logical in draft["material"]:
            coerce_cell(material_schema, field_name, draft["material"].get(logical), allow_new_tag=allow_new_tag, warnings=warnings)
    for index, topic in enumerate(draft["topics"]):
        for logical, field_name in TOPIC_FIELDS.items():
            if logical in {"source_material"}:
                continue
            value = topic.get(logical)
            if value is None or value == []:
                continue
            if field_name not in topic_schema.fields:
                if logical == "status":
                    warnings.append(f"topics[{index}].status skipped because topic table has no 状态 field")
                    continue
                raise SchemaError(f"Topic field missing in live table: {field_name}")
            coerce_cell(topic_schema, field_name, value, allow_new_tag=allow_new_tag, warnings=warnings)
    return warnings


def command_validate_draft(args: argparse.Namespace) -> int:
    draft = normalize_draft(read_json(Path(args.draft).expanduser()))
    schemas = load_live_schemas()
    schema_warnings = validate_expected_schema(schemas, strict=not args.allow_incomplete)
    warnings = schema_warnings + validate_draft_against_schema(
        draft,
        schemas,
        allow_new_tag=not args.strict_options,
        allow_incomplete=args.allow_incomplete,
    )
    print(json.dumps({"ok": True, "topics": len(draft["topics"]), "warnings": warnings}, ensure_ascii=False, indent=2))
    return 0


def select_existing_fields(schema: TableSchema, candidates: list[str]) -> list[str]:
    return [field for field in candidates if schema.has(field)]


def build_row(
    schema: TableSchema,
    fields: list[str],
    values: dict[str, Any],
    *,
    allow_new_tag: bool,
    warnings: list[str],
) -> list[Any]:
    row: list[Any] = []
    for field in fields:
        row.append(coerce_cell(schema, field, values.get(field), allow_new_tag=allow_new_tag, warnings=warnings))
    return row


def create_record(
    table_id: str,
    schema: TableSchema,
    values: dict[str, Any],
    fields: list[str],
    *,
    dry_run: bool,
    allow_new_tag: bool,
    warnings: list[str],
) -> str:
    row = build_row(schema, fields, values, allow_new_tag=allow_new_tag, warnings=warnings)
    body = {"fields": fields, "rows": [row]}
    data = run_lark(
        [
            "base",
            "+record-batch-create",
            "--base-token",
            BASE_TOKEN,
            "--table-id",
            table_id,
            "--json",
            json.dumps(body, ensure_ascii=False),
        ],
        dry_run=dry_run,
        timeout=120,
    )
    if dry_run:
        return "recDRYRUN"
    record_ids = (data.get("data") or {}).get("record_id_list") or []
    if not record_ids:
        raise PipelineError(f"No record_id returned for table {table_id}: {json.dumps(data, ensure_ascii=False)}")
    return str(record_ids[0])


def batch_create_records(
    table_id: str,
    schema: TableSchema,
    rows_values: list[dict[str, Any]],
    fields: list[str],
    *,
    dry_run: bool,
    allow_new_tag: bool,
    warnings: list[str],
) -> list[str]:
    rows = [
        build_row(schema, fields, values, allow_new_tag=allow_new_tag, warnings=warnings)
        for values in rows_values
    ]
    body = {"fields": fields, "rows": rows}
    data = run_lark(
        [
            "base",
            "+record-batch-create",
            "--base-token",
            BASE_TOKEN,
            "--table-id",
            table_id,
            "--json",
            json.dumps(body, ensure_ascii=False),
        ],
        dry_run=dry_run,
        timeout=180,
    )
    if dry_run:
        return [f"recDRYRUN{i + 1}" for i in range(len(rows_values))]
    record_ids = (data.get("data") or {}).get("record_id_list") or []
    if len(record_ids) != len(rows_values):
        raise PipelineError(f"Expected {len(rows_values)} record ids, got {len(record_ids)}")
    return [str(record_id) for record_id in record_ids]


def upsert_record(
    table_id: str,
    record_id: str,
    schema: TableSchema,
    values: dict[str, Any],
    *,
    dry_run: bool,
    allow_new_tag: bool,
    warnings: list[str],
) -> None:
    patch: dict[str, Any] = {}
    for field_name, value in values.items():
        if value is None or value == []:
            continue
        if not schema.has(field_name):
            warnings.append(f"{table_id}: skipped missing field {field_name}")
            continue
        patch[field_name] = coerce_cell(schema, field_name, value, allow_new_tag=allow_new_tag, warnings=warnings)
    if not patch:
        return
    run_lark(
        [
            "base",
            "+record-upsert",
            "--base-token",
            BASE_TOKEN,
            "--table-id",
            table_id,
            "--record-id",
            record_id,
            "--json",
            json.dumps(patch, ensure_ascii=False),
        ],
        dry_run=dry_run,
        timeout=120,
    )


def search_duplicates(draft: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    duplicates: list[dict[str, Any]] = []
    for topic in draft["topics"]:
        title = compact_text(topic.get("title"))
        keyword = title[:24] if len(title) >= 2 else compact_text(topic.get("angle"))[:24]
        if not keyword:
            continue
        body = {
            "keyword": keyword,
            "search_fields": ["选题标题", "选题角度"],
            "select_fields": ["选题标题", "选题角度", "潜力等级"],
            "limit": limit,
        }
        data = run_lark(
            [
                "base",
                "+record-search",
                "--base-token",
                BASE_TOKEN,
                "--table-id",
                TOPIC_TABLE,
                "--json",
                json.dumps(body, ensure_ascii=False),
                "--format",
                "json",
            ],
            timeout=120,
        )
        payload = data.get("data") or {}
        rows = payload.get("data") or []
        ids = payload.get("record_id_list") or []
        for record_id, row in zip(ids, rows):
            duplicates.append(
                {
                    "draft_title": title,
                    "keyword": keyword,
                    "record_id": record_id,
                    "existing_title": row[0] if len(row) > 0 else "",
                    "existing_angle": row[1] if len(row) > 1 else "",
                    "potential": row[2] if len(row) > 2 else "",
                }
            )
    return duplicates


def material_values(draft: dict[str, Any]) -> dict[str, Any]:
    material = draft["material"]
    title = compact_text(material.get("title"))
    if not title and draft["topics"]:
        title = compact_text(draft["topics"][0].get("title"))
    return {
        "VA7 选题灵感库": title or "未命名素材",
        "类型": material.get("type") or "外部内容",
        "来源链接": material.get("source_url") or "",
        "内容摘要": material.get("summary") or "",
        "金句": material.get("quotes") or "",
        "标签": material.get("tags") or [],
        "状态": "待拆解",
        "添加日期": material.get("date") or now_ms(),
        "选题类型": material.get("topic_type"),
    }


def topic_values(topic: dict[str, Any]) -> dict[str, Any]:
    return {
        "选题标题": topic.get("title"),
        "选题角度": topic.get("angle"),
        "认知密度": topic.get("cognitive_density"),
        "潜力等级": topic.get("potential"),
        "口播草稿": topic.get("script"),
        "人性钩子": topic.get("human_hook"),
        "目标平台": topic.get("platforms") or [],
        "标签": topic.get("tags") or [],
        "创建日期": topic.get("created_at") or now_ms(),
        "选题类型": topic.get("topic_type"),
        "状态": topic.get("status") or "待采访",
        "待做": topic.get("todo"),
    }


def create_material_record(
    draft: dict[str, Any],
    schema: TableSchema,
    *,
    dry_run: bool,
    allow_new_tag: bool,
    warnings: list[str],
) -> str:
    values = material_values(draft)
    create_fields = select_existing_fields(
        schema,
        [
            "VA7 选题灵感库",
            "类型",
            "来源链接",
            "状态",
            "添加日期",
            "内容摘要",
            "金句",
            "选题类型",
        ],
    )
    record_id = create_record(
        MATERIAL_TABLE,
        schema,
        values,
        create_fields,
        dry_run=dry_run,
        allow_new_tag=allow_new_tag,
        warnings=warnings,
    )
    upsert_record(
        MATERIAL_TABLE,
        record_id,
        schema,
        {"标签": values.get("标签")},
        dry_run=dry_run,
        allow_new_tag=allow_new_tag,
        warnings=warnings,
    )
    return record_id


def create_topic_records(
    draft: dict[str, Any],
    topic_schema: TableSchema,
    material_record_id: str,
    *,
    dry_run: bool,
    allow_new_tag: bool,
    warnings: list[str],
) -> list[str]:
    row_values = [topic_values(topic) for topic in draft["topics"]]
    create_fields = select_existing_fields(
        topic_schema,
        [
            "选题标题",
            "选题角度",
            "认知密度",
            "潜力等级",
            "口播草稿",
            "人性钩子",
            "选题类型",
            "创建日期",
            "待做",
            "状态",
        ],
    )
    record_ids = batch_create_records(
        TOPIC_TABLE,
        topic_schema,
        row_values,
        create_fields,
        dry_run=dry_run,
        allow_new_tag=allow_new_tag,
        warnings=warnings,
    )
    for record_id, values in zip(record_ids, row_values):
        upsert_record(
            TOPIC_TABLE,
            record_id,
            topic_schema,
            {
                "目标平台": values.get("目标平台"),
                "标签": values.get("标签"),
                "来源素材": [material_record_id],
            },
            dry_run=dry_run,
            allow_new_tag=allow_new_tag,
            warnings=warnings,
        )
    return record_ids


def verify_record_fields(table_id: str, record_id: str, required: list[str]) -> dict[str, Any]:
    data = run_lark(
        [
            "base",
            "+record-get",
            "--base-token",
            BASE_TOKEN,
            "--table-id",
            table_id,
            "--record-id",
            record_id,
            "--format",
            "json",
        ],
        timeout=120,
    )
    payload = data.get("data") or {}
    record = payload.get("record") or {}
    if not record:
        records, _ = normalize_record_list(data)
        record = records[0] if records else {}
    missing = []
    for field in required:
        value = record.get(field)
        if value in (None, "", []):
            missing.append(field)
    return {"record_id": record_id, "missing": missing, "record": record}


def get_record(table_id: str, record_id: str) -> dict[str, Any]:
    data = run_lark(
        [
            "base",
            "+record-get",
            "--base-token",
            BASE_TOKEN,
            "--table-id",
            table_id,
            "--record-id",
            record_id,
            "--format",
            "json",
        ],
        timeout=120,
    )
    payload = data.get("data") or {}
    record = payload.get("record") or {}
    if not record:
        records, _ = normalize_record_list(data)
        record = records[0] if records else {}
    if not isinstance(record, dict) or not record:
        raise PipelineError(f"Could not read record {record_id} from table {table_id}")
    return record


def is_empty_cell(value: Any) -> bool:
    if value in (None, "", []):
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return all(is_empty_cell(item) for item in value)
    return False


def first_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        for item in value:
            text = first_scalar(item)
            if text:
                return text
        return ""
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value.get("id") or value.get("record_id") or "")
    return str(value)


def cell_strings(value: Any) -> list[str]:
    values: list[str] = []
    for item in as_list(value):
        if isinstance(item, dict):
            item = item.get("text") or item.get("name") or item.get("value") or item.get("id") or item.get("record_id")
        text = str(item or "").strip()
        if text:
            values.append(text)
    return values


def unique_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def extract_record_ids(value: Any) -> list[str]:
    ids: list[str] = []
    for item in as_list(value):
        if isinstance(item, dict):
            item = item.get("record_id") or item.get("id")
        text = str(item or "").strip()
        if text:
            ids.append(text)
    return ids


def is_done_status(value: Any) -> bool:
    text = first_scalar(value).strip()
    return text.startswith("已拆解") or text in {"已用完", "已用"}


def normalize_record_list(data: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    payload = data.get("data") or {}
    fields = payload.get("fields") or []
    record_ids = payload.get("record_id_list") or []
    rows = payload.get("data") or []
    records: list[dict[str, Any]] = []
    for record_id, row in zip(record_ids, rows):
        record = {"record_id": str(record_id)}
        for index, field in enumerate(fields):
            record[str(field)] = row[index] if index < len(row) else None
        records.append(record)
    return records, bool(payload.get("has_more"))


def list_table_records(table_id: str, fields: list[str], *, limit: int = 200) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    offset = 0
    while True:
        cmd = [
            "base",
            "+record-list",
            "--base-token",
            BASE_TOKEN,
            "--table-id",
            table_id,
            "--limit",
            str(limit),
            "--offset",
            str(offset),
            "--format",
            "json",
        ]
        for field in fields:
            cmd.extend(["--field-id", field])
        page, has_more = normalize_record_list(run_lark(cmd, timeout=180))
        records.extend(page)
        if not has_more or not page:
            break
        offset += len(page)
    return records


def issue(
    severity: str,
    table: str,
    record_id: str,
    issue_name: str,
    **extra: Any,
) -> dict[str, Any]:
    item = {
        "severity": severity,
        "table": table,
        "record_id": record_id,
        "issue": issue_name,
    }
    item.update({key: value for key, value in extra.items() if value not in (None, "", [])})
    return item


def title_for(record: dict[str, Any], *fields: str) -> str:
    for field in fields:
        text = first_scalar(record.get(field)).strip()
        if text:
            return text
    return ""


def audit_material_records(materials: list[dict[str, Any]], topic_ids: set[str]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    core_required = ["VA7 选题灵感库", "类型", "状态", "添加日期"]
    enrichment_fields = ["内容摘要", "金句", "标签"]
    for record in materials:
        record_id = record["record_id"]
        title = title_for(record, "VA7 选题灵感库")
        non_empty = [field for field in MATERIAL_AUDIT_FIELDS if not is_empty_cell(record.get(field))]
        if not non_empty:
            issues.append(issue("P0", "material", record_id, "blank_record", auto="delete_or_ignore"))
            continue
        missing_core = [field for field in core_required if is_empty_cell(record.get(field))]
        if missing_core:
            issues.append(
                issue(
                    "P1",
                    "material",
                    record_id,
                    "missing_required_fields",
                    title=title,
                    fields=missing_core,
                    auto="recover_from_source_or_reingest",
                )
            )
        linked = extract_record_ids(record.get("关联选题"))
        status = first_scalar(record.get("状态"))
        missing_enrichment = [field for field in enrichment_fields if is_empty_cell(record.get(field))]
        if missing_enrichment:
            linked_or_done = bool(linked) or is_done_status(record.get("状态"))
            issues.append(
                issue(
                    "P1" if linked_or_done else "P2",
                    "material",
                    record_id,
                    "missing_enriched_fields" if linked_or_done else "backlog_incomplete_fields",
                    title=title,
                    fields=missing_enrichment,
                    linked_count=len(linked),
                    auto="infer_tags_or_reextract_quotes_from_source",
                )
            )
        missing_links = [record_id for record_id in linked if record_id not in topic_ids]
        if missing_links:
            issues.append(
                issue(
                    "P1",
                    "material",
                    record_id,
                    "linked_topic_not_found",
                    title=title,
                    linked_topic_ids=missing_links,
                    auto="remove_or_recreate_link_after_review",
                )
            )
        if is_done_status(record.get("状态")) and not linked:
            issues.append(
                issue(
                    "P1",
                    "material",
                    record_id,
                    "status_done_without_linked_topics",
                    title=title,
                    auto="link_topics_or_set_status_waiting",
                )
            )
        if linked and not is_done_status(record.get("状态")):
            issues.append(
                issue(
                    "P2",
                    "material",
                    record_id,
                    "has_topics_but_status_not_done",
                    title=title,
                    linked_count=len(linked),
                    auto="set_status_done_if_topics_are_valid",
                )
            )
    return issues


def audit_topic_records(topics: list[dict[str, Any]], material_ids: set[str]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    required = [
        "选题标题",
        "选题角度",
        "认知密度",
        "潜力等级",
        "口播草稿",
        "人性钩子",
        "目标平台",
        "标签",
        "来源素材",
        "创建日期",
    ]
    for record in topics:
        record_id = record["record_id"]
        title = title_for(record, "选题标题")
        non_empty = [field for field in TOPIC_AUDIT_FIELDS if not is_empty_cell(record.get(field))]
        if not non_empty:
            issues.append(issue("P0", "topic", record_id, "blank_record", auto="delete_or_ignore"))
            continue
        missing_required = [field for field in required if is_empty_cell(record.get(field))]
        if missing_required:
            issues.append(
                issue(
                    "P1",
                    "topic",
                    record_id,
                    "missing_required_fields",
                    title=title,
                    fields=missing_required,
                    auto="recover_from_draft_source_or_reingest",
                )
            )
        linked = extract_record_ids(record.get("来源素材"))
        missing_links = [record_id for record_id in linked if record_id not in material_ids]
        if missing_links:
            issues.append(
                issue(
                    "P1",
                    "topic",
                    record_id,
                    "source_material_not_found",
                    title=title,
                    source_material_ids=missing_links,
                    auto="remove_or_recreate_link_after_review",
                )
            )
    return issues


def audit_viral_topic_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    required = ["选题标题", "来源链接", "来源平台", "为什么爆", "可借鉴点", "潜力等级", "状态", "标签", "添加日期"]
    for record in records:
        record_id = record["record_id"]
        title = title_for(record, "选题标题")
        non_empty = [field for field in VIRAL_AUDIT_FIELDS if not is_empty_cell(record.get(field))]
        if not non_empty:
            issues.append(issue("P0", "viral_topic", record_id, "blank_record", auto="delete_or_ignore"))
            continue
        missing_required = [field for field in required if is_empty_cell(record.get(field))]
        if missing_required:
            issues.append(
                issue(
                    "P1",
                    "viral_topic",
                    record_id,
                    "missing_required_fields",
                    title=title,
                    fields=missing_required,
                    auto="recover_from_source_or_reingest",
                )
            )
    return issues


def audit_finished_content_records(records: list[dict[str, Any]], schedule_ids: set[str]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    core_required = ["标题", "平台", "状态", "发布日期", "链接", "正文描述"]
    enrichment_required = ["口播稿全文", "选题类型"]
    for record in records:
        record_id = record["record_id"]
        title = title_for(record, "标题", "ID")
        non_empty = [field for field in FINISHED_CONTENT_AUDIT_FIELDS if not is_empty_cell(record.get(field))]
        if not non_empty:
            issues.append(issue("P0", "finished_content", record_id, "blank_record", auto="delete_or_ignore"))
            continue
        missing_core = [field for field in core_required if is_empty_cell(record.get(field))]
        if missing_core:
            issues.append(
                issue(
                    "P1",
                    "finished_content",
                    record_id,
                    "missing_required_fields",
                    title=title,
                    fields=missing_core,
                    auto="recover_from_platform_export_or_schedule",
                )
            )
        schedule_links = extract_record_ids(record.get("关联内容排期"))
        if not schedule_links:
            issues.append(
                issue(
                    "P1",
                    "finished_content",
                    record_id,
                    "missing_schedule_link",
                    title=title,
                    auto="match_schedule_by_title_and_date",
                )
            )
        else:
            missing_links = [schedule_id for schedule_id in schedule_links if schedule_id not in schedule_ids]
            if missing_links:
                issues.append(
                    issue(
                        "P1",
                        "finished_content",
                        record_id,
                        "schedule_link_not_found",
                        title=title,
                        schedule_ids=missing_links,
                        auto="remove_or_recreate_link_after_review",
                    )
                )
        missing_enrichment = [field for field in enrichment_required if is_empty_cell(record.get(field))]
        if missing_enrichment:
            issues.append(
                issue(
                    "P1",
                    "finished_content",
                    record_id,
                    "missing_enriched_fields",
                    title=title,
                    fields=missing_enrichment,
                    auto="fill_from_linked_schedule_or_topic",
                )
            )
        optional_missing = [field for field in ["封面图", "IP属地"] if is_empty_cell(record.get(field))]
        if optional_missing:
            is_tikhub = is_tikhub_finished_record(record)
            cover_url_present = "封面图" in optional_missing and not is_empty_cell(record.get("封面图URL"))
            issues.append(
                issue(
                    "P1" if is_tikhub else "P2",
                    "finished_content",
                    record_id,
                    "missing_recoverable_platform_fields" if is_tikhub else "missing_optional_publish_fields",
                    title=title,
                    fields=optional_missing,
                    auto="fix_feishu_attachment_mobile_only_or_upload_from_mobile"
                    if is_tikhub and cover_url_present
                    else "repair-finished-from-tikhub"
                    if is_tikhub
                    else "recover_from_platform_export_if_available",
                    note="封面图URL already recovered from TikHub; attachment field is still empty"
                    if cover_url_present
                    else None,
                )
            )
    return issues


def audit_production_schedule_records(records: list[dict[str, Any]], finished_ids: set[str], topic_ids: set[str]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for record in records:
        record_id = record["record_id"]
        title = title_for(record, "内容标题", "视频标题", "公众号标题")
        non_empty = [field for field in PRODUCTION_SCHEDULE_AUDIT_FIELDS if not is_empty_cell(record.get(field))]
        if not non_empty:
            issues.append(issue("P0", "production_schedule", record_id, "blank_record", auto="delete_or_ignore"))
            continue
        if is_empty_cell(record.get("内容标题")):
            issues.append(
                issue(
                    "P1",
                    "production_schedule",
                    record_id,
                    "missing_required_fields",
                    title=title,
                    fields=["内容标题"],
                    auto="recover_from_linked_topic_or_finished_content",
                )
            )
        finished_links = extract_record_ids(record.get("平台发布记录"))
        if finished_links and is_empty_cell(record.get("选题类型")):
            issues.append(
                issue(
                    "P1",
                    "production_schedule",
                    record_id,
                    "missing_published_fields",
                    title=title,
                    fields=["选题类型"],
                    auto="fill_from_finished_content_or_topic",
                )
            )
        missing_finished = [finished_id for finished_id in finished_links if finished_id not in finished_ids]
        if missing_finished:
            issues.append(
                issue(
                    "P1",
                    "production_schedule",
                    record_id,
                    "finished_content_link_not_found",
                    title=title,
                    finished_content_ids=missing_finished,
                    auto="remove_or_recreate_link_after_review",
                )
            )
        topic_links = extract_record_ids(record.get("关联选题"))
        missing_topics = [topic_id for topic_id in topic_links if topic_id not in topic_ids]
        if missing_topics:
            issues.append(
                issue(
                    "P1",
                    "production_schedule",
                    record_id,
                    "topic_link_not_found",
                    title=title,
                    topic_ids=missing_topics,
                    auto="remove_or_recreate_link_after_review",
                )
            )
    return issues


def field_coverage(records: list[dict[str, Any]], fields: list[str], policy: dict[str, str]) -> dict[str, Any]:
    total = len(records)
    rows: list[dict[str, Any]] = []
    for field in fields:
        missing_records = []
        for record in records:
            if is_empty_cell(record.get(field)):
                missing_records.append(
                    {
                        "record_id": record.get("record_id"),
                        "title": title_for(record, "标题", "内容标题", "视频标题", "ID"),
                    }
                )
        present = total - len(missing_records)
        rows.append(
            {
                "field": field,
                "policy": policy.get(field, "unclassified"),
                "present": present,
                "missing": len(missing_records),
                "coverage": round(present / total, 4) if total else 1.0,
                "missing_records": missing_records[:20],
                "truncated": len(missing_records) > 20,
            }
        )
    return {"records": total, "fields": rows}


def summarize_issues(issues: list[dict[str, Any]]) -> dict[str, Any]:
    by_severity: dict[str, int] = {}
    by_issue: dict[str, int] = {}
    by_table: dict[str, int] = {}
    for item in issues:
        by_severity[item["severity"]] = by_severity.get(item["severity"], 0) + 1
        by_issue[item["issue"]] = by_issue.get(item["issue"], 0) + 1
        by_table[item["table"]] = by_table.get(item["table"], 0) + 1
    return {
        "total": len(issues),
        "by_severity": dict(sorted(by_severity.items())),
        "by_issue": dict(sorted(by_issue.items())),
        "by_table": dict(sorted(by_table.items())),
    }


def command_audit(args: argparse.Namespace) -> int:
    schemas = load_live_schemas()
    validate_expected_schema(schemas, strict=False)
    material_fields = select_existing_fields(schemas["material"], MATERIAL_AUDIT_FIELDS)
    topic_fields = select_existing_fields(schemas["topic"], TOPIC_AUDIT_FIELDS)
    finished_fields = list(schemas["finished_content"].fields)
    schedule_fields = list(schemas["production_schedule"].fields)
    viral_fields = select_existing_fields(schemas["viral_topic"], VIRAL_AUDIT_FIELDS)
    materials = list_table_records(MATERIAL_TABLE, material_fields)
    topics = list_table_records(TOPIC_TABLE, topic_fields)
    finished_contents = list_table_records(FINISHED_CONTENT_TABLE, finished_fields)
    schedules = list_table_records(PRODUCTION_SCHEDULE_TABLE, schedule_fields)
    viral_topics = list_table_records(VIRAL_TOPIC_TABLE, viral_fields) if args.include_viral else []

    material_ids = {record["record_id"] for record in materials}
    topic_ids = {record["record_id"] for record in topics}
    finished_ids = {record["record_id"] for record in finished_contents}
    schedule_ids = {record["record_id"] for record in schedules}
    issues: list[dict[str, Any]] = []
    issues.extend(audit_material_records(materials, topic_ids))
    issues.extend(audit_topic_records(topics, material_ids))
    issues.extend(audit_finished_content_records(finished_contents, schedule_ids))
    issues.extend(audit_production_schedule_records(schedules, finished_ids, topic_ids))
    if args.include_viral:
        issues.extend(audit_viral_topic_records(viral_topics))

    if not args.include_backlog:
        issues = [
            item
            for item in issues
            if item["issue"] != "backlog_incomplete_fields"
        ]

    severity_rank = {"P0": 0, "P1": 1, "P2": 2}
    issues.sort(key=lambda item: (severity_rank.get(item["severity"], 9), item["table"], item["issue"], item["record_id"]))
    result = {
        "ok": not any(item["severity"] in {"P0", "P1"} for item in issues),
        "base_url": BASE_URL,
        "counts": {
            "material": len(materials),
            "topic": len(topics),
            "finished_content": len(finished_contents),
            "production_schedule": len(schedules),
            "viral_topic": len(viral_topics),
        },
        "summary": summarize_issues(issues),
        "field_coverage": {
            "finished_content": field_coverage(
                finished_contents,
                finished_fields,
                FINISHED_CONTENT_FIELD_POLICY,
            ),
            "production_schedule": field_coverage(
                schedules,
                schedule_fields,
                PRODUCTION_SCHEDULE_FIELD_POLICY,
            ),
        },
        "issues": issues[: args.max_issues] if args.max_issues else issues,
        "truncated": bool(args.max_issues and len(issues) > args.max_issues),
    }
    if args.out:
        write_json(Path(args.out).expanduser(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] or args.warn_only else 2


def infer_material_tags_from_topics(material: dict[str, Any], topics_by_id: dict[str, dict[str, Any]]) -> list[str]:
    tags: list[str] = []
    for topic_id in extract_record_ids(material.get("关联选题")):
        topic = topics_by_id.get(topic_id)
        if topic:
            tags.extend(cell_strings(topic.get("标签")))
    return unique_keep_order(tags)


def build_safe_repairs(
    materials: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    finished_contents: list[dict[str, Any]] | None = None,
    schedules: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    material_by_id = {record["record_id"]: record for record in materials}
    topics_by_id = {record["record_id"]: record for record in topics}
    finished_contents = finished_contents or []
    schedules = schedules or []
    schedule_by_id = {record["record_id"]: record for record in schedules}
    schedule_by_finished_id: dict[str, dict[str, Any]] = {}
    for schedule in schedules:
        for finished_id in extract_record_ids(schedule.get("平台发布记录")):
            schedule_by_finished_id[finished_id] = schedule
    actions: list[dict[str, Any]] = []

    for material in materials:
        record_id = material["record_id"]
        patch: dict[str, Any] = {}
        linked_topics = extract_record_ids(material.get("关联选题"))
        if linked_topics and not is_done_status(material.get("状态")):
            patch["状态"] = "已拆解"
        if is_empty_cell(material.get("标签")) and linked_topics:
            tags = infer_material_tags_from_topics(material, topics_by_id)
            if tags:
                patch["标签"] = tags
        if patch:
            actions.append(
                {
                    "action": "upsert",
                    "table": "material",
                    "table_id": MATERIAL_TABLE,
                    "record_id": record_id,
                    "patch": patch,
                    "reason": "sync status/tags from linked topics",
                }
            )

    for topic in topics:
        record_id = topic["record_id"]
        source_ids = extract_record_ids(topic.get("来源素材"))
        patch = {}
        if is_empty_cell(topic.get("创建日期")):
            for source_id in source_ids:
                material = material_by_id.get(source_id)
                if not material:
                    continue
                title_date = date_from_text(material.get("VA7 选题灵感库"))
                if title_date:
                    patch["创建日期"] = title_date
                    break
                if not is_empty_cell(material.get("添加日期")):
                    patch["创建日期"] = material.get("添加日期")
                    break
        if patch:
            actions.append(
                {
                    "action": "upsert",
                    "table": "topic",
                    "table_id": TOPIC_TABLE,
                    "record_id": record_id,
                    "patch": patch,
                    "reason": "inherit missing topic date from source material",
                }
            )

    for finished in finished_contents:
        record_id = finished["record_id"]
        schedule_links = extract_record_ids(finished.get("关联内容排期"))
        finished_topic_type = first_scalar(finished.get("选题类型"))
        if schedule_links and finished_topic_type:
            for schedule_id in schedule_links:
                schedule = schedule_by_id.get(schedule_id)
                if schedule and is_empty_cell(schedule.get("选题类型")):
                    actions.append(
                        {
                            "action": "upsert",
                            "table": "production_schedule",
                            "table_id": PRODUCTION_SCHEDULE_TABLE,
                            "record_id": schedule_id,
                            "patch": {"选题类型": finished_topic_type},
                            "reason": "sync missing schedule topic type from linked finished content",
                        }
                    )
        if schedule_links:
            continue
        existing_schedule = schedule_by_finished_id.get(record_id)
        if existing_schedule:
            actions.append(
                {
                    "action": "upsert",
                    "table": "finished_content",
                    "table_id": FINISHED_CONTENT_TABLE,
                    "record_id": record_id,
                    "patch": {"关联内容排期": [existing_schedule["record_id"]]},
                    "reason": "backfill finished content schedule link from reverse schedule link",
                }
            )
            continue
        title = title_for(finished, "标题", "ID")
        if not title:
            continue
        publish_date = finished.get("发布日期")
        values = {
            "内容标题": title,
            "视频标题": title,
            "选题类型": first_scalar(finished.get("选题类型")) or None,
            "主发布日期": publish_date,
            "发布时间": publish_date,
            "视频文案介绍": finished.get("正文描述"),
            "备注": "由成品内容自动补建排期；" + (compact_text(finished.get("备注")) or "无原备注"),
            "平台发布记录": [record_id],
        }
        actions.append(
            {
                "action": "create_schedule_for_finished",
                "table": "production_schedule",
                "table_id": PRODUCTION_SCHEDULE_TABLE,
                "source_table": "finished_content",
                "source_record_id": record_id,
                "values": values,
                "reason": "create missing production schedule row for published finished content",
            }
        )
    return actions


def command_repair_safe(args: argparse.Namespace) -> int:
    schemas = load_live_schemas()
    validate_expected_schema(schemas, strict=False)
    material_fields = select_existing_fields(schemas["material"], MATERIAL_AUDIT_FIELDS)
    topic_fields = select_existing_fields(schemas["topic"], TOPIC_AUDIT_FIELDS)
    finished_fields = select_existing_fields(schemas["finished_content"], FINISHED_CONTENT_AUDIT_FIELDS)
    schedule_fields = select_existing_fields(schemas["production_schedule"], PRODUCTION_SCHEDULE_AUDIT_FIELDS)
    materials = list_table_records(MATERIAL_TABLE, material_fields)
    topics = list_table_records(TOPIC_TABLE, topic_fields)
    finished_contents = list_table_records(FINISHED_CONTENT_TABLE, finished_fields)
    schedules = list_table_records(PRODUCTION_SCHEDULE_TABLE, schedule_fields)
    actions = build_safe_repairs(materials, topics, finished_contents, schedules)
    if args.limit:
        actions = actions[: args.limit]
    if args.plan_out:
        write_json(Path(args.plan_out).expanduser(), {"apply": args.apply, "actions": actions})

    warnings: list[str] = []
    results: list[dict[str, Any]] = []
    for action in actions:
        if action["action"] == "upsert":
            schema = schemas[action["table"]]
            upsert_record(
                action["table_id"],
                action["record_id"],
                schema,
                action["patch"],
                dry_run=not args.apply,
                allow_new_tag=True,
                warnings=warnings,
            )
            results.append(
                {
                    "record_id": action["record_id"],
                    "table": action["table"],
                    "patch": action["patch"],
                    "reason": action["reason"],
                }
            )
        elif action["action"] == "create_schedule_for_finished":
            schedule_schema = schemas["production_schedule"]
            finished_schema = schemas["finished_content"]
            create_fields = select_existing_fields(
                schedule_schema,
                [
                    "内容标题",
                    "视频标题",
                    "选题类型",
                    "主发布日期",
                    "发布时间",
                    "视频文案介绍",
                    "备注",
                    "平台发布记录",
                ],
            )
            schedule_id = create_record(
                PRODUCTION_SCHEDULE_TABLE,
                schedule_schema,
                action["values"],
                create_fields,
                dry_run=not args.apply,
                allow_new_tag=True,
                warnings=warnings,
            )
            if args.apply:
                upsert_record(
                    FINISHED_CONTENT_TABLE,
                    action["source_record_id"],
                    finished_schema,
                    {"关联内容排期": [schedule_id]},
                    dry_run=False,
                    allow_new_tag=True,
                    warnings=warnings,
                )
            results.append(
                {
                    "record_id": schedule_id,
                    "table": "production_schedule",
                    "source_record_id": action["source_record_id"],
                    "values": action["values"],
                    "reason": action["reason"],
                }
            )
        else:
            raise PipelineError(f"Unsupported safe repair action: {action['action']}")

    print(
        json.dumps(
            {
                "ok": True,
                "apply": args.apply,
                "actions": len(actions),
                "warnings": warnings,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def iter_history_entries(paths: list[Path]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in paths:
        path = path.expanduser()
        if not path.exists():
            continue
        if path.is_dir():
            files = sorted(path.rglob("*.jsonl"))
        else:
            files = [path]
        for file_path in files:
            with file_path.open(encoding="utf-8", errors="replace") as handle:
                for line_no, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        raw = {"text": line}
                    text = compact_text(raw.get("text") or raw.get("message") or "")
                    if not text:
                        continue
                    entries.append(
                        {
                            "path": str(file_path),
                            "line": line_no,
                            "session_id": raw.get("session_id"),
                            "ts": raw.get("ts") or raw.get("timestamp") or 0,
                            "text": text,
                        }
                    )
    return entries


def extract_script_from_history(text: str, rule: dict[str, Any]) -> str:
    start_marker = str(rule["start_marker"])
    start = text.find(start_marker)
    if start == -1:
        return ""
    fragment = text[start:]
    end_positions = []
    for marker in rule.get("end_markers", []):
        pos = fragment.find(str(marker))
        if pos > 0:
            end_positions.append(pos)
    if end_positions:
        fragment = fragment[: min(end_positions)]
    fragment = fragment.replace("\u200b", "")
    return compact_text(fragment)


def find_finished_history_match(
    record: dict[str, Any],
    history_entries: list[dict[str, Any]],
) -> dict[str, Any] | None:
    title = title_for(record, "标题", "ID")
    for rule in FINISHED_HISTORY_RECOVERY_RULES:
        if str(rule["title_contains"]) not in title:
            continue
        candidates: list[dict[str, Any]] = []
        for entry in history_entries:
            text = entry["text"]
            if str(rule["start_marker"]) not in text:
                continue
            missing_terms = [term for term in rule.get("required_terms", []) if str(term) not in text]
            if missing_terms:
                continue
            script = extract_script_from_history(text, rule)
            if len(script) < 500:
                continue
            score = len(script)
            if "最终" in text:
                score += 5000
            if "存档" in text:
                score += 3000
            candidates.append(
                {
                    "script": script,
                    "topic_type": rule["topic_type"],
                    "score": score,
                    "source": {
                        "path": entry["path"],
                        "line": entry["line"],
                        "session_id": entry.get("session_id"),
                        "ts": entry.get("ts"),
                    },
                }
            )
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item["score"], str(item["source"].get("ts") or ""), item["source"]["line"]), reverse=True)
        return candidates[0]
    return None


def build_finished_history_repairs(
    finished_contents: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    history_entries: list[dict[str, Any]],
    *,
    record_ids: set[str],
    force: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    schedule_by_id = {record["record_id"]: record for record in schedules}
    actions: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for finished in finished_contents:
        record_id = finished["record_id"]
        if record_ids and record_id not in record_ids:
            continue
        missing_script = is_empty_cell(finished.get("口播稿全文"))
        missing_topic_type = is_empty_cell(finished.get("选题类型"))
        if not force and not (missing_script or missing_topic_type):
            continue
        match = find_finished_history_match(finished, history_entries)
        title = title_for(finished, "标题", "ID")
        if not match:
            unmatched.append(
                {
                    "record_id": record_id,
                    "title": title,
                    "missing": [
                        field
                        for field, missing in [("口播稿全文", missing_script), ("选题类型", missing_topic_type)]
                        if missing
                    ],
                }
            )
            continue
        patch: dict[str, Any] = {}
        if force or missing_script:
            patch["口播稿全文"] = match["script"]
        if force or missing_topic_type:
            patch["选题类型"] = match["topic_type"]
        if patch:
            actions.append(
                {
                    "action": "upsert",
                    "table": "finished_content",
                    "table_id": FINISHED_CONTENT_TABLE,
                    "record_id": record_id,
                    "title": title,
                    "patch": patch,
                    "source": match["source"],
                    "reason": "recover finished-content script/type from local Codex history with exact title rule",
                }
            )
        for schedule_id in extract_record_ids(finished.get("关联内容排期")):
            schedule = schedule_by_id.get(schedule_id)
            if not schedule:
                continue
            if force or is_empty_cell(schedule.get("选题类型")):
                actions.append(
                    {
                        "action": "upsert",
                        "table": "production_schedule",
                        "table_id": PRODUCTION_SCHEDULE_TABLE,
                        "record_id": schedule_id,
                        "title": title_for(schedule, "内容标题", "视频标题"),
                        "patch": {"选题类型": match["topic_type"]},
                        "source": match["source"],
                        "reason": "sync schedule topic type from recovered finished content history match",
                    }
            )
    return actions, unmatched


def is_tikhub_finished_record(record: dict[str, Any]) -> bool:
    note = compact_text(record.get("备注")).lower()
    url = normalize_url(record.get("链接"))
    return "tikhub" in note and "xiaohongshu.com" in url


def build_finished_tikhub_repairs(
    finished_contents: list[dict[str, Any]],
    *,
    record_ids: set[str],
    force: bool,
    cover_url_field: str,
    config: dict[str, Any],
    cache_dir: Path,
    cover_dir: Path,
    use_cache: bool,
    no_download: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for finished in finished_contents:
        record_id = finished["record_id"]
        title = title_for(finished, "标题", "ID")
        if record_ids and record_id not in record_ids:
            continue
        if not is_tikhub_finished_record(finished):
            if record_ids and record_id in record_ids:
                skipped.append(
                    {
                        "record_id": record_id,
                        "title": title,
                        "reason": "record is not marked as TikHub Xiaohongshu sync or has no Xiaohongshu link",
                    }
                )
            continue
        missing_cover = is_empty_cell(finished.get("封面图"))
        missing_ip = is_empty_cell(finished.get("IP属地"))
        if not force and not (missing_cover or missing_ip):
            skipped.append({"record_id": record_id, "title": title, "reason": "封面图/IP属地 already present"})
            continue

        url = normalize_url(finished.get("链接"))
        try:
            response = fetch_tikhub_note(url, config=config, cache_dir=cache_dir, use_cache=use_cache)
            note = find_tikhub_note(response)
            if not note:
                skipped.append({"record_id": record_id, "title": title, "reason": "TikHub response had no note_list item"})
                continue
            ip_location = normalize_xhs_ip_location(note.get("ip_location"))
            cover_urls = tikhub_cover_url_candidates(note)
            cover_path: Path | None = None
            download_errors: list[str] = []
            if (force or missing_cover) and cover_urls and not no_download:
                cover_path, download_errors = download_first_tikhub_cover(cover_urls, cover_dir, record_id)
        except PipelineError as exc:
            skipped.append({"record_id": record_id, "title": title, "reason": str(exc)})
            continue

        patch: dict[str, Any] = {}
        upload: dict[str, Any] | None = None
        if (force or missing_ip) and ip_location:
            patch["IP属地"] = ip_location
        if cover_url_field and cover_urls:
            if force or is_empty_cell(finished.get(cover_url_field)):
                patch[cover_url_field] = cover_urls[0]
        if force or missing_cover:
            if cover_path:
                upload = {
                    "field": "封面图",
                    "file": str(cover_path),
                    "name": f"{record_id}{cover_path.suffix}",
                    "cover_url": cover_urls[0],
                }
            elif cover_urls:
                skipped.append(
                    {
                        "record_id": record_id,
                        "title": title,
                        "reason": "cover URL found but download failed",
                        "cover_urls": cover_urls,
                        "download_errors": download_errors,
                    }
                )
            else:
                skipped.append({"record_id": record_id, "title": title, "reason": "TikHub note had no cover URL"})
        if not patch and not upload:
            skipped.append(
                {
                    "record_id": record_id,
                    "title": title,
                    "reason": "TikHub returned no recoverable missing fields",
                    "ip_location": ip_location,
                    "cover_urls": cover_urls,
                }
            )
            continue
        actions.append(
            {
                "action": "upsert_and_upload",
                "table": "finished_content",
                "table_id": FINISHED_CONTENT_TABLE,
                "record_id": record_id,
                "title": title,
                "source_url": url,
                "patch": patch,
                "upload": upload,
                "tikhub": {
                    "endpoint": response.get("_endpoint"),
                    "cache_file": response.get("_cache_file"),
                    "from_cache": bool(response.get("_from_cache")),
                    "request_id": ((response.get("data") or {}).get("request_id") if isinstance(response.get("data"), dict) else None),
                    "note_id": note.get("id") or note.get("note_id"),
                    "note_title": note.get("title"),
                    "ip_location_raw": note.get("ip_location"),
                    "cover_urls": cover_urls[:5],
                    "download_errors": download_errors,
                },
                "reason": "recover Xiaohongshu platform fields from TikHub export",
            }
        )
    return actions, skipped


def token_set(value: Any) -> set[str]:
    text = compact_text(value).lower()
    text = re.sub(r"https?://\S+", " ", text)
    return {item for item in re.split(r"[^0-9a-zA-Z\u4e00-\u9fff]+", text) if len(item) >= 2}


def title_similarity(left: str, right: str) -> float:
    left_norm = re.sub(r"\W+", "", left.lower())
    right_norm = re.sub(r"\W+", "", right.lower())
    if not left_norm or not right_norm:
        return 0.0
    if left_norm in right_norm or right_norm in left_norm:
        return 1.0
    left_tokens = token_set(left)
    right_tokens = token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))


def finished_tikhub_match_score(finished: dict[str, Any], note: dict[str, Any]) -> float:
    finished_title = title_for(finished, "标题")
    note_title = tikhub_note_title(note)
    score = title_similarity(finished_title, note_title) * 100
    finished_text = token_set(finished.get("正文描述"))
    note_text = token_set(tikhub_note_desc(note))
    if finished_text and note_text:
        score += min(30.0, 60.0 * len(finished_text & note_text) / max(1, min(len(finished_text), len(note_text))))
    return round(score, 2)


def tikhub_finished_patch(note: dict[str, Any], *, cover_url_field: str) -> dict[str, Any]:
    patch: dict[str, Any] = {
        "状态": "已发布",
        "链接": tikhub_note_url(note),
        "IP属地": normalize_xhs_ip_location(note.get("ip_location")),
        "点赞": tikhub_note_likes(note),
        "收藏": note.get("collected_count"),
        "评论": note.get("comments_count") if note.get("comments_count") is not None else note.get("comment_count"),
        "分享": note.get("share_count"),
        "视频时长(秒)": tikhub_note_video_duration(note),
    }
    published_at = tikhub_note_created_at(note)
    if published_at:
        patch["发布日期"] = published_at
    cover_urls = tikhub_cover_url_candidates(note)
    if cover_url_field and cover_urls:
        patch[cover_url_field] = cover_urls[0]
    note_id = tikhub_note_id(note)
    if note_id:
        patch["备注"] = f"TikHub 小红书同步；从 VA7 用户笔记列表回填 note_id={note_id}。"
    return {key: value for key, value in patch.items() if value not in (None, "", [])}


def build_finished_tikhub_user_sync(
    finished_contents: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    *,
    record_ids: set[str],
    force: bool,
    cover_url_field: str,
    cover_dir: Path,
    no_download: bool,
    min_score: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    used_note_ids: set[str] = set()
    for finished in finished_contents:
        record_id = finished["record_id"]
        title = title_for(finished, "标题", "ID")
        if record_ids and record_id not in record_ids:
            continue
        platform = first_scalar(finished.get("平台"))
        if platform and platform != "小红书":
            continue
        needs_sync = force or is_empty_cell(finished.get("链接")) or is_empty_cell(finished.get("封面图")) or is_empty_cell(finished.get("IP属地"))
        if not needs_sync:
            skipped.append({"record_id": record_id, "title": title, "reason": "already has publish link/cover/IP"})
            continue
        candidates = [
            (finished_tikhub_match_score(finished, note), note)
            for note in notes
            if tikhub_note_id(note) not in used_note_ids
        ]
        candidates.sort(key=lambda item: item[0], reverse=True)
        if not candidates or candidates[0][0] < min_score:
            skipped.append(
                {
                    "record_id": record_id,
                    "title": title,
                    "reason": "no confident TikHub user-note match",
                    "best_score": candidates[0][0] if candidates else 0,
                    "best_note_title": tikhub_note_title(candidates[0][1]) if candidates else "",
                }
            )
            continue
        score, note = candidates[0]
        used_note_ids.add(tikhub_note_id(note))
        patch = tikhub_finished_patch(note, cover_url_field=cover_url_field)
        if not force:
            patch = {key: value for key, value in patch.items() if is_empty_cell(finished.get(key)) or key in {"状态", "备注"}}
        cover_urls = tikhub_cover_url_candidates(note)
        upload: dict[str, Any] | None = None
        download_errors: list[str] = []
        if (force or is_empty_cell(finished.get("封面图"))) and cover_urls and not no_download:
            cover_path, download_errors = download_first_tikhub_cover(cover_urls, cover_dir, record_id)
            if cover_path:
                upload = {
                    "field": "封面图",
                    "file": str(cover_path),
                    "name": f"{record_id}{cover_path.suffix}",
                    "cover_url": cover_urls[0],
                }
        if not patch and not upload:
            skipped.append({"record_id": record_id, "title": title, "reason": "matched note but no missing fields", "score": score})
            continue
        actions.append(
            {
                "action": "upsert_and_upload",
                "table": "finished_content",
                "table_id": FINISHED_CONTENT_TABLE,
                "record_id": record_id,
                "title": title,
                "source_url": tikhub_note_url(note),
                "patch": patch,
                "upload": upload,
                "tikhub": {
                    "endpoint": note.get("_endpoint"),
                    "cache_file": note.get("_cache_file"),
                    "note_id": tikhub_note_id(note),
                    "note_title": tikhub_note_title(note),
                    "ip_location_raw": note.get("ip_location"),
                    "cover_urls": cover_urls[:5],
                    "download_errors": download_errors,
                    "match_score": score,
                },
                "reason": "sync published Xiaohongshu fields from VA7 TikHub user notes",
            }
        )
    return actions, skipped


def execute_finished_tikhub_actions(
    actions: list[dict[str, Any]],
    *,
    schemas: dict[str, TableSchema],
    apply: bool,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    warnings: list[str] = []
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for action in actions:
        patch = action.get("patch") or {}
        upload = action.get("upload")
        patched_fields: list[str] = []
        uploaded_fields: list[str] = []
        if patch:
            try:
                upsert_record(
                    action["table_id"],
                    action["record_id"],
                    schemas["finished_content"],
                    patch,
                    dry_run=not apply,
                    allow_new_tag=False,
                    warnings=warnings,
                )
                patched_fields = list(patch)
            except PipelineError as exc:
                failures.append(
                    {
                        "record_id": action["record_id"],
                        "title": action.get("title"),
                        "operation": "patch",
                        "fields": list(patch),
                        "error": str(exc),
                    }
                )
        if upload:
            try:
                upload_attachment(
                    action["table_id"],
                    action["record_id"],
                    str(upload["field"]),
                    Path(str(upload["file"])),
                    name=str(upload.get("name") or Path(str(upload["file"])).name),
                    dry_run=not apply,
                )
                if apply:
                    record = get_record(action["table_id"], action["record_id"])
                    if is_empty_cell(record.get(str(upload["field"]))):
                        raise PipelineError(f"post_upload_empty_cell: {upload['field']} is still empty after attachment upload")
                uploaded_fields = [upload["field"]]
            except PipelineError as exc:
                failures.append(
                    {
                        "record_id": action["record_id"],
                        "title": action.get("title"),
                        "operation": "upload_attachment",
                        "fields": [upload["field"]],
                        "file": upload.get("file"),
                        "cover_url": upload.get("cover_url"),
                        "error": str(exc),
                    }
                )
        results.append(
            {
                "record_id": action["record_id"],
                "title": action.get("title"),
                "patched_fields": patched_fields,
                "uploaded_fields": uploaded_fields,
                "source_url": action.get("source_url"),
                "match_score": (action.get("tikhub") or {}).get("match_score"),
            }
        )
    return warnings, results, failures


def command_repair_finished_from_tikhub(args: argparse.Namespace) -> int:
    schemas = load_live_schemas()
    validate_expected_schema(schemas, strict=False)
    config = load_tikhub_config(args.tikhub_config)
    cache_dir = Path(args.cache_dir).expanduser()
    cover_dir = Path(args.cover_dir).expanduser()
    cover_url_field = args.cover_url_field or ""
    if cover_url_field:
        ensure_text_field(
            FINISHED_CONTENT_TABLE,
            schemas["finished_content"],
            cover_url_field,
            dry_run=not args.apply or not args.create_cover_url_field,
        )
    finished_contents = list_table_records(FINISHED_CONTENT_TABLE, list(schemas["finished_content"].fields))
    actions, skipped = build_finished_tikhub_repairs(
        finished_contents,
        record_ids=set(args.record_id or []),
        force=args.force,
        cover_url_field=cover_url_field,
        config=config,
        cache_dir=cache_dir,
        cover_dir=cover_dir,
        use_cache=not args.no_cache,
        no_download=args.no_download,
    )
    if args.limit:
        actions = actions[: args.limit]
    plan = {
        "apply": args.apply,
        "config_path": config.get("config_path"),
        "base_url": config.get("base_url"),
        "cache_dir": str(cache_dir),
        "cover_dir": str(cover_dir),
        "cover_url_field": cover_url_field,
        "actions": actions,
        "skipped": skipped,
    }
    if args.plan_out:
        write_json(Path(args.plan_out).expanduser(), plan)

    warnings, results, failures = execute_finished_tikhub_actions(actions, schemas=schemas, apply=args.apply)

    result = {
        "ok": not failures,
        "apply": args.apply,
        "actions": len(actions),
        "failures": failures,
        "skipped": skipped,
        "warnings": warnings,
        "results": results,
    }
    if args.plan_out:
        plan["result"] = result
        write_json(Path(args.plan_out).expanduser(), plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 2


def command_sync_finished_from_tikhub_user(args: argparse.Namespace) -> int:
    schemas = load_live_schemas()
    validate_expected_schema(schemas, strict=False)
    config = load_tikhub_config(args.tikhub_config)
    cache_dir = Path(args.cache_dir).expanduser()
    cover_dir = Path(args.cover_dir).expanduser()
    cover_url_field = args.cover_url_field or ""
    if cover_url_field:
        ensure_text_field(
            FINISHED_CONTENT_TABLE,
            schemas["finished_content"],
            cover_url_field,
            dry_run=not args.apply or not args.create_cover_url_field,
        )
    finished_contents = list_table_records(FINISHED_CONTENT_TABLE, list(schemas["finished_content"].fields))
    notes, fetch_warnings = fetch_tikhub_user_notes(
        args.user_id,
        config=config,
        cache_dir=cache_dir,
        use_cache=not args.no_cache,
        pages=args.pages,
    )
    actions, skipped = build_finished_tikhub_user_sync(
        finished_contents,
        notes,
        record_ids=set(args.record_id or []),
        force=args.force,
        cover_url_field=cover_url_field,
        cover_dir=cover_dir,
        no_download=args.no_download,
        min_score=args.min_score,
    )
    if args.limit:
        actions = actions[: args.limit]
    plan = {
        "apply": args.apply,
        "config_path": config.get("config_path"),
        "base_url": config.get("base_url"),
        "user_id": args.user_id,
        "notes": len(notes),
        "cache_dir": str(cache_dir),
        "cover_dir": str(cover_dir),
        "cover_url_field": cover_url_field,
        "actions": actions,
        "skipped": skipped,
        "fetch_warnings": fetch_warnings,
    }
    if args.plan_out:
        write_json(Path(args.plan_out).expanduser(), plan)
    warnings, results, failures = execute_finished_tikhub_actions(actions, schemas=schemas, apply=args.apply)
    result = {
        "ok": not failures,
        "apply": args.apply,
        "notes": len(notes),
        "actions": len(actions),
        "failures": failures,
        "skipped": skipped,
        "warnings": fetch_warnings + warnings,
        "results": results,
    }
    if args.plan_out:
        plan["result"] = result
        write_json(Path(args.plan_out).expanduser(), plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 2


def command_repair_finished_from_history(args: argparse.Namespace) -> int:
    history_paths = [Path(item).expanduser() for item in (args.history_file or [])]
    if not history_paths:
        history_paths = [Path.home() / ".codex" / "history.jsonl"]
    history_entries = iter_history_entries(history_paths)
    schemas = load_live_schemas()
    validate_expected_schema(schemas, strict=False)
    finished_contents = list_table_records(FINISHED_CONTENT_TABLE, list(schemas["finished_content"].fields))
    schedules = list_table_records(PRODUCTION_SCHEDULE_TABLE, list(schemas["production_schedule"].fields))
    actions, unmatched = build_finished_history_repairs(
        finished_contents,
        schedules,
        history_entries,
        record_ids=set(args.record_id or []),
        force=args.force,
    )
    if args.limit:
        actions = actions[: args.limit]
    plan = {
        "apply": args.apply,
        "history_files": [str(path) for path in history_paths],
        "history_entries": len(history_entries),
        "actions": actions,
        "unmatched": unmatched,
    }
    if args.plan_out:
        write_json(Path(args.plan_out).expanduser(), plan)

    warnings: list[str] = []
    results: list[dict[str, Any]] = []
    for action in actions:
        schema = schemas[action["table"]]
        upsert_record(
            action["table_id"],
            action["record_id"],
            schema,
            action["patch"],
            dry_run=not args.apply,
            allow_new_tag=False,
            warnings=warnings,
        )
        results.append(
            {
                "record_id": action["record_id"],
                "table": action["table"],
                "title": action.get("title"),
                "patched_fields": list(action["patch"]),
                "source": action.get("source"),
            }
        )
    print(
        json.dumps(
            {
                "ok": True,
                "apply": args.apply,
                "history_entries": len(history_entries),
                "actions": len(actions),
                "unmatched": unmatched,
                "warnings": warnings,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_search_duplicates(args: argparse.Namespace) -> int:
    draft = normalize_draft(read_json(Path(args.draft).expanduser()))
    duplicates = search_duplicates(draft, limit=args.limit)
    print(json.dumps({"ok": True, "duplicates": duplicates}, ensure_ascii=False, indent=2))
    return 0


def command_upload(args: argparse.Namespace) -> int:
    draft = normalize_draft(read_json(Path(args.draft).expanduser()))
    schemas = load_live_schemas()
    warnings = validate_expected_schema(schemas, strict=True)
    warnings.extend(
        validate_draft_against_schema(
            draft,
            schemas,
            allow_new_tag=not args.strict_options,
            allow_incomplete=args.allow_incomplete,
        )
    )
    duplicates = search_duplicates(draft, limit=5) if args.check_duplicates else []
    if duplicates and args.duplicate_policy == "fail":
        print(json.dumps({"ok": False, "reason": "duplicates_found", "duplicates": duplicates}, ensure_ascii=False, indent=2))
        return 2
    if duplicates:
        warnings.append(f"duplicate candidates found: {len(duplicates)}")

    material_id = create_material_record(
        draft,
        schemas["material"],
        dry_run=args.dry_run,
        allow_new_tag=not args.strict_options,
        warnings=warnings,
    )
    topic_ids = create_topic_records(
        draft,
        schemas["topic"],
        material_id,
        dry_run=args.dry_run,
        allow_new_tag=not args.strict_options,
        warnings=warnings,
    )
    upsert_record(
        MATERIAL_TABLE,
        material_id,
        schemas["material"],
        {"关联选题": topic_ids, "状态": "已拆解"},
        dry_run=args.dry_run,
        allow_new_tag=not args.strict_options,
        warnings=warnings,
    )

    verification: list[dict[str, Any]] = []
    if not args.dry_run:
        for topic_id in topic_ids:
            verification.append(
                verify_record_fields(
                    TOPIC_TABLE,
                    topic_id,
                    ["目标平台", "标签", "来源素材", "口播草稿", "人性钩子"],
                )
            )
        verification.append(verify_record_fields(MATERIAL_TABLE, material_id, ["关联选题", "状态"]))
        failures = [item for item in verification if item["missing"]]
        if failures:
            raise PipelineError("Post-upload verification failed: " + json.dumps(failures, ensure_ascii=False, indent=2))

    result = {
        "ok": True,
        "dry_run": args.dry_run,
        "base_url": BASE_URL,
        "material_record_id": material_id,
        "topic_record_ids": topic_ids,
        "duplicates": duplicates,
        "warnings": warnings,
        "verification": [{"record_id": item["record_id"], "missing": item["missing"]} for item in verification],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_schema(args: argparse.Namespace) -> int:
    schemas = load_live_schemas()
    warnings = validate_expected_schema(schemas, strict=False)
    data = {
        "ok": True,
        "base_token": BASE_TOKEN,
        "base_url": BASE_URL,
        "warnings": warnings,
        "tables": {key: schema_to_json(schema) for key, schema in schemas.items()},
    }
    if args.out:
        write_json(Path(args.out).expanduser(), data)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    checks: list[dict[str, Any]] = []

    def check(name: str, fn, *, optional: bool = False) -> None:
        try:
            result = fn()
            status = "warn" if optional and result == "not configured" else "pass"
            checks.append({"name": name, "status": status, "detail": result})
        except Exception as exc:  # noqa: BLE001 - doctor must report all checks
            checks.append({"name": name, "status": "warn" if optional else "fail", "detail": str(exc)})

    check("lark-cli", lambda: require_tool("lark-cli"))
    check("ffmpeg", lambda: require_tool("ffmpeg"))
    check("lark-cli doctor", lambda: run_json(["lark-cli", "doctor"]))
    check("base schema", lambda: validate_expected_schema(load_live_schemas(), strict=True))
    check(
        "x fetch backend",
        lambda: "X_BEARER_TOKEN configured"
        if os.environ.get("X_BEARER_TOKEN") or os.environ.get("TWITTER_BEARER_TOKEN")
        else "INSPIRATION_X_FETCH_CMD configured"
        if os.environ.get("INSPIRATION_X_FETCH_CMD") or os.environ.get("INSPIRATION_T_FETCH_CMD")
        else "not configured",
        optional=True,
    )
    check(
        "transcription backend",
        lambda: "INSPIRATION_TRANSCRIBE_CMD configured"
        if os.environ.get("INSPIRATION_TRANSCRIBE_CMD")
        else "OPENAI_API_KEY configured"
        if os.environ.get("OPENAI_API_KEY")
        else "not configured",
        optional=True,
    )
    ok = all(item["status"] == "pass" for item in checks[:4])
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def command_run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    material_path = out_dir / "material.json"
    transcript_path = out_dir / "transcript.json"
    draft_path = out_dir / "draft.json"

    if args.media:
        audio_path = out_dir / "audio_16k.wav"
        command_prepare_audio(argparse.Namespace(input=args.media, out=str(audio_path)))
        command_transcribe(
            argparse.Namespace(
                audio=str(audio_path),
                out=str(transcript_path),
                provider=args.transcribe_provider,
                model=args.transcribe_model,
            )
        )

    if args.url or args.feishu_doc or args.x_handle or args.input_file:
        command_fetch(
            argparse.Namespace(
                url=args.url,
                feishu_doc=args.feishu_doc,
                x_handle=args.x_handle,
                input_file=args.input_file,
                limit=args.limit,
                out_dir=str(out_dir),
                out=str(material_path),
            )
        )
    elif not material_path.exists():
        write_json(material_path, {"source_type": "empty", "title": "未命名素材", "text": ""})

    if not args.upload_draft:
        command_make_draft(
            argparse.Namespace(
                material=str(material_path),
                transcript=str(transcript_path) if transcript_path.exists() else None,
                out=str(draft_path),
                prompt_out=str(out_dir / "draft.prompt.md"),
            )
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "next": "Fill draft.json with topics, then run validate-draft and upload.",
                    "draft": str(draft_path),
                    "prompt": str(out_dir / "draft.prompt.md"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    return command_upload(
        argparse.Namespace(
            draft=args.upload_draft,
            dry_run=args.dry_run,
            strict_options=args.strict_options,
            allow_incomplete=False,
            check_duplicates=True,
            duplicate_policy=args.duplicate_policy,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VA7 va7-library scripted pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="check local tools, Feishu auth, and live schema")
    p.set_defaults(func=command_doctor)

    p = sub.add_parser("schema", help="print live Feishu Base schema")
    p.add_argument("--out")
    p.set_defaults(func=command_schema)

    p = sub.add_parser("audit", help="scan library records for blank rows, missing fields, and broken links")
    p.add_argument("--out", help="write the audit JSON report to this path")
    p.add_argument("--include-backlog", action="store_true", help="include P2 backlog rows such as waiting materials without tags")
    p.add_argument("--include-viral", action="store_true", help="also audit the viral topic table")
    p.add_argument("--max-issues", type=int, default=0, help="limit issues printed to stdout; 0 means all")
    p.add_argument("--warn-only", action="store_true", help="return exit 0 even when P0/P1 issues exist")
    p.set_defaults(func=command_audit)

    p = sub.add_parser("repair-safe", help="apply deterministic repairs inferred from existing links")
    p.add_argument("--apply", action="store_true", help="execute writes; default is dry-run")
    p.add_argument("--plan-out", default="work/inspiration_repair_safe_plan.json")
    p.add_argument("--limit", type=int, default=0, help="limit number of planned actions for testing")
    p.set_defaults(func=command_repair_safe)

    p = sub.add_parser("repair-finished-from-history", help="recover finished-content scripts/types from local Codex history")
    p.add_argument("--apply", action="store_true", help="execute writes; default is dry-run")
    p.add_argument("--history-file", action="append", help="history jsonl file or directory; defaults to ~/.codex/history.jsonl")
    p.add_argument("--record-id", action="append", help="limit repair to one finished-content record id; can repeat")
    p.add_argument("--plan-out", default="work/inspiration_repair_finished_from_history_plan.json")
    p.add_argument("--limit", type=int, default=0, help="limit number of planned actions for testing")
    p.add_argument("--force", action="store_true", help="overwrite existing recovered fields when a rule matches")
    p.set_defaults(func=command_repair_finished_from_history)

    p = sub.add_parser("repair-finished-from-tikhub", help="recover Xiaohongshu cover/IP for TikHub-synced finished content")
    p.add_argument("--apply", action="store_true", help="execute Feishu writes; default is dry-run")
    p.add_argument("--record-id", action="append", help="limit repair to one finished-content record id; can repeat")
    p.add_argument("--plan-out", default="work/inspiration_repair_finished_from_tikhub_plan.json")
    p.add_argument("--limit", type=int, default=0, help="limit number of planned actions for testing")
    p.add_argument("--force", action="store_true", help="overwrite existing 封面图/IP属地 when TikHub returns values")
    p.add_argument("--tikhub-config", help="TikHub config JSON path; defaults to TIKHUB_API_KEY or known local config paths")
    p.add_argument("--cache-dir", default="work/tikhub-cache", help="local TikHub response cache directory")
    p.add_argument("--cover-dir", default="work/tikhub-covers", help="downloaded cover image directory")
    p.add_argument("--cover-url-field", default="封面图URL", help="text field for deterministic TikHub cover URL fallback; empty disables")
    p.add_argument("--create-cover-url-field", action="store_true", help="create --cover-url-field as a text field when missing and --apply is used")
    p.add_argument("--no-cache", action="store_true", help="fetch fresh TikHub responses")
    p.add_argument("--no-download", action="store_true", help="do not download cover files; useful for metadata-only planning")
    p.set_defaults(func=command_repair_finished_from_tikhub)

    p = sub.add_parser("sync-finished-from-tikhub-user", help="sync published Xiaohongshu finished content from VA7 TikHub user notes")
    p.add_argument("--apply", action="store_true", help="execute Feishu writes; default is dry-run")
    p.add_argument("--record-id", action="append", help="limit repair to one finished-content record id; can repeat")
    p.add_argument("--plan-out", default="work/inspiration_sync_finished_from_tikhub_user_plan.json")
    p.add_argument("--limit", type=int, default=0, help="limit number of planned actions for testing")
    p.add_argument("--force", action="store_true", help="overwrite existing publish/platform fields when TikHub returns values")
    p.add_argument("--tikhub-config", help="TikHub config JSON path; defaults to TIKHUB_API_KEY or known local config paths")
    p.add_argument("--user-id", default=os.environ.get("INSPIRATION_XHS_USER_ID", TIKHUB_VA7_USER_ID), help="Xiaohongshu user id to read published notes from")
    p.add_argument("--pages", type=int, default=1, help="number of user-note pages to fetch")
    p.add_argument("--min-score", type=float, default=60.0, help="minimum title/body match score required before writing")
    p.add_argument("--cache-dir", default="work/tikhub-cache", help="local TikHub response cache directory")
    p.add_argument("--cover-dir", default="work/tikhub-covers", help="downloaded cover image directory")
    p.add_argument("--cover-url-field", default="封面图URL", help="text field for deterministic TikHub cover URL fallback; empty disables")
    p.add_argument("--create-cover-url-field", action="store_true", help="create --cover-url-field as a text field when missing and --apply is used")
    p.add_argument("--no-cache", action="store_true", help="fetch fresh TikHub responses")
    p.add_argument("--no-download", action="store_true", help="do not download cover files; useful for metadata-only planning")
    p.set_defaults(func=command_sync_finished_from_tikhub_user)

    p = sub.add_parser("fetch", help="fetch material from URL, Feishu doc, X handle, or local file")
    p.add_argument("--url")
    p.add_argument("--feishu-doc")
    p.add_argument("--x-handle")
    p.add_argument("--input-file")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--out-dir", default="work/va7-library")
    p.add_argument("--out")
    p.set_defaults(func=command_fetch)

    p = sub.add_parser("prepare-audio", help="extract 16k mono WAV from media")
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=command_prepare_audio)

    p = sub.add_parser("transcribe", help="transcribe audio with external command or OpenAI API")
    p.add_argument("--audio", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--provider", choices=["auto", "external", "openai"], default="auto")
    p.add_argument("--model", default=os.environ.get("INSPIRATION_OPENAI_TRANSCRIBE_MODEL", "whisper-1"))
    p.set_defaults(func=command_transcribe)

    p = sub.add_parser("make-draft", help="make draft JSON scaffold and LLM fill prompt")
    p.add_argument("--material")
    p.add_argument("--transcript")
    p.add_argument("--out", required=True)
    p.add_argument("--prompt-out")
    p.set_defaults(func=command_make_draft)

    p = sub.add_parser("validate-draft", help="validate draft JSON against live schema")
    p.add_argument("--draft", required=True)
    p.add_argument("--strict-options", action="store_true", help="fail on new tag options instead of warning")
    p.add_argument("--allow-incomplete", action="store_true")
    p.set_defaults(func=command_validate_draft)

    p = sub.add_parser("search-duplicates", help="search existing topic rows for duplicate candidates")
    p.add_argument("--draft", required=True)
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=command_search_duplicates)

    p = sub.add_parser("upload", help="upload draft JSON to Feishu Base")
    p.add_argument("--draft", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--strict-options", action="store_true")
    p.add_argument("--allow-incomplete", action="store_true")
    p.add_argument("--check-duplicates", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--duplicate-policy", choices=["fail", "warn", "allow"], default="fail")
    p.set_defaults(func=command_upload)

    p = sub.add_parser("run", help="orchestrate fetch/transcribe into draft scaffold, or upload an existing draft")
    p.add_argument("--url")
    p.add_argument("--feishu-doc")
    p.add_argument("--x-handle")
    p.add_argument("--input-file")
    p.add_argument("--media")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--out-dir", default="work/va7-library")
    p.add_argument("--transcribe-provider", choices=["auto", "external", "openai"], default="auto")
    p.add_argument("--transcribe-model", default=os.environ.get("INSPIRATION_OPENAI_TRANSCRIBE_MODEL", "whisper-1"))
    p.add_argument("--upload-draft", help="skip scaffold and upload this filled draft JSON")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--strict-options", action="store_true")
    p.add_argument("--duplicate-policy", choices=["fail", "warn", "allow"], default="fail")
    p.set_defaults(func=command_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except PipelineError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""VA7 各环节共用的预检 / 交付闸门。

预检（preflight）：每环节开工前跑，把每一项的结果写进 <stage>_preflight.json；
    有任何一项 failed，文件整体 status=blocked，下游脚本拒绝运行。
下游检查（require_preflight）：渲染、写入等脚本启动时调用，缺文件或未通过就退出码 2。
交付（deliver）：最后一步核对必交清单，全部通过才输出校验码；交付消息末尾必须带这个码。
校验码 = sha256(环节名 + 预检文件内容 + 交付物内容) 前 8 位。交付物改一个字，码就变。
只能证明走过这些项，不能证明判断对不对；标 ◆ 的项（human_review）永远留人审。
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PASSED = "passed"
HUMAN = "human_review"  # ◆ 纯判断项：脚本只记录「已列出待人审」，不替人判断


def item(item_id: str, ok: bool, detail: str = "", *, human: bool = False) -> dict:
    status = HUMAN if human else (PASSED if ok else "failed")
    return {"id": item_id, "status": status, "detail": detail}


def write_preflight(path, stage: str, items: list, extra: dict | None = None) -> dict:
    failed = [i for i in items if i["status"] == "failed"]
    doc = {
        "stage": stage,
        "version": 3,
        "status": "blocked" if failed else PASSED,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "items": items,
        **(extra or {}),
    }
    Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


def stop(msg: str, code: int = 2):
    print(json.dumps({"passed": False, "error": msg}, ensure_ascii=False, indent=2))
    sys.exit(code)


def require_preflight(path, stage: str) -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        stop(f"缺少预检结果 {p}：先跑本环节的 preflight，再继续")
    doc = json.loads(p.read_text(encoding="utf-8"))
    if doc.get("version") != 3 or doc.get("stage") != stage:
        stop(f"预检文件 {p} 不是 {stage} 环节的新格式，重新跑预检")
    if doc.get("status") != PASSED:
        bad = [i["id"] for i in doc.get("items", []) if i["status"] == "failed"]
        stop(f"预检未通过，缺项：{', '.join(bad)}")
    return doc


def report(items: list, stage: str, extra: dict | None = None) -> int:
    failed = [i for i in items if i["status"] == "failed"]
    human = [i["id"] for i in items if i["status"] == HUMAN]
    out = {"passed": not failed, "stage": stage, "failed": failed, "human_review": human, "items": items}
    out.update(extra or {})
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not failed else 2


def check_code(stage: str, preflight_path, *deliverables) -> str:
    h = hashlib.sha256(stage.encode())
    h.update(Path(preflight_path).read_bytes())
    for d in deliverables:
        h.update(Path(d).read_bytes())
    return h.hexdigest()[:8]

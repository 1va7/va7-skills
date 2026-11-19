#!/usr/bin/env python3
"""发布物料环节的预检与交付检查。

preflight : 开工前。核对口播终稿、封面标题（没有则必须写明原因）、条件，写 publish_preflight.json
deliver   : 交付前。物料 JSON（和 apply_publish_materials.py 同格式，另带 title_alternatives）逐项核对，
            通过才输出校验码；apply_publish_materials.py --apply 前也应先过本检查。

章节默认是「标题 + 换章句」：换章句必须是口播终稿里能逐字找到的那一句，不带时间，不依赖 SRT。
有 SRT / ASR 时间来源时才补时间版（沿用 start/end/content 格式）。
标 ◆ 的项（标题好不好、正文有没有 hook）脚本不判断。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "va7-pipeline" / "scripts"))
import gatelib as g  # noqa: E402

STAGE = "publish"


def strip_ws(s: str) -> str:
    return re.sub(r"\s+", "", s)


def cmd_preflight(a) -> int:
    items = []
    sp = Path(a.script).expanduser() if a.script else None
    items.append(g.item("final_script_exists", bool(sp and sp.is_file() and sp.read_text(encoding="utf-8").strip()), str(sp)))
    cover_ok = bool(a.cover_title) or bool(a.no_cover_reason)
    items.append(g.item("cover_title_or_reason", cover_ok, a.cover_title or a.no_cover_reason or "缺 --cover-title，或用 --no-cover-reason 写明封面未做的原因"))
    items.append(g.item("script_confirmed_final", bool(a.script_confirmed), "口播稿经人确认定稿：--script-confirmed" if not a.script_confirmed else "已确认"))
    items.append(g.item("◆标题与正文是否有 hook", True, "判断项，留人审", human=True))
    g.write_preflight(a.out, STAGE, items, {"script": str(sp) if sp else None, "cover_title": a.cover_title, "no_cover_reason": a.no_cover_reason})
    return g.report(items, STAGE)


def cmd_deliver(a) -> int:
    pre = g.require_preflight(a.preflight, STAGE)
    script = strip_ws(Path(pre["script"]).read_text(encoding="utf-8"))
    mats = json.loads(Path(a.materials).read_text(encoding="utf-8"))
    items = []
    for n, m in enumerate(mats, 1):
        tag = f"#{n} "
        alts = m.get("title_alternatives") or []
        items.append(g.item(tag + "title_alternatives_3_to_5", 3 <= len(alts) <= 5, f"{len(alts)} 个备选"))
        items.append(g.item(tag + "title_chosen_from_alternatives", m.get("title") in alts, "title 必须是备选之一（人确认后）"))
        body = re.sub(r"#[^#\s]+\[话题\]#|#\S+", "", m.get("body", ""))
        blen = len(strip_ws(body))
        items.append(g.item(tag + "body_le_200", 0 < blen <= 200, f"正文 {blen} 字（不含话题标签与空白）"))
        tags = re.findall(r"#\S+", m.get("hashtag", ""))
        items.append(g.item(tag + "hashtag_5_to_8", 5 <= len(tags) <= 8, f"{len(tags)} 个"))
        chs = m.get("chapters")
        if not chs:
            reason = (m.get("chapters_missing_reason") or "").strip()
            items.append(g.item(tag + "chapters_present_or_reason", bool(reason), reason or "没有章节必须写 chapters_missing_reason"))
            continue
        limit = 5
        if m.get("video_duration_seconds"):
            limit = min(limit, math.ceil(float(m["video_duration_seconds"]) / 60))
        items.append(g.item(tag + "chapter_count", 1 <= len(chs) <= limit, f"{len(chs)} 个，上限 {limit}"))
        for i, c in enumerate(chs, 1):
            items.append(g.item(tag + f"chapter{i}_title_le_14", 0 < len(c.get("title", "")) <= 14, c.get("title", "")))
            if c.get("start") or c.get("end"):
                items.append(g.item(tag + f"chapter{i}_time_present", bool(c.get("start") and c.get("end")), "时间版需 start 和 end"))
            else:
                line = strip_ws(c.get("opening_line", ""))
                items.append(g.item(tag + f"chapter{i}_opening_in_script", bool(line) and line in script, "换章句必须是口播终稿里逐字存在的一句"))
        if len(chs) > 1 and not any(c.get("start") for c in chs):
            ordered = [script.find(strip_ws(c.get("opening_line", ""))) for c in chs]
            items.append(g.item(tag + "chapters_in_script_order", ordered == sorted(ordered) and -1 not in ordered, f"位置 {ordered}"))
    covers = mats[0].get("cover_options") if mats else None
    ok = isinstance(covers, list) and len(covers) == 5 and all(
        c.get("big") and 3 <= len(c.get("small") or []) <= 5 for c in covers)
    items.append(g.item("cover_options_5_big_yellow_small_white_3_to_5", ok,
                        "封面大小标题备选 5 套，每套 big（黄字）+ small（白字 3-5 个要点）" if ok else "缺 cover_options：要 5 套 {big, small:[3-5 条]}"))
    hz = mats[0].get("huazi_options") if mats else None
    ok = isinstance(hz, list) and len(hz) == 3 and all(len(c.get("tl", [])) == 2 and len(c.get("br", [])) == 2 for c in hz)
    items.append(g.item("huazi_options_3", ok, "花字备选 3 套（左上白 2 行、右下黄 2 行）" if ok else "缺 huazi_options：要 3 套 {tl:[2行], br:[2行]}"))
    items.append(g.item("cover_title_relation_noted", True, f"封面标题：{pre.get('cover_title') or '未做：' + str(pre.get('no_cover_reason'))}"))
    items.append(g.item("◆标题与正文", True, "判断项，留人审", human=True))
    rc = g.report(items, STAGE)
    if rc == 0:
        print(json.dumps({"校验码": g.check_code(STAGE, a.preflight, a.materials), "说明": "交付消息末尾必须带这个码；apply 前材料再改就要重跑"}, ensure_ascii=False))
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preflight")
    p.add_argument("--script", required=True, help="口播终稿文本文件")
    p.add_argument("--script-confirmed", action="store_true")
    p.add_argument("--cover-title")
    p.add_argument("--no-cover-reason")
    p.add_argument("--out", default="publish_preflight.json")
    p.set_defaults(fn=cmd_preflight)
    d = sub.add_parser("deliver")
    d.add_argument("--preflight", default="publish_preflight.json")
    d.add_argument("--materials", required=True)
    d.set_defaults(fn=cmd_deliver)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())

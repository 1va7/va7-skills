#!/usr/bin/env python3
"""封面环节的预检与交付检查。

preflight : 出图前。声明走哪个分支，核对底图、构图规范与案例库已读（脚本从规范文件解析本次阈值并写入预检），
            写 cover_preflight.json。渲染脚本和交付都要求它通过。
deliver   : 交付前。核对底图来源、严格 QA 结果、对照板、（若做了花字）花字预检，通过才输出校验码。

分支：
  direct_image : 用户直接给图。不做任何色彩判断和处理，原图就是最终底图；预检记下原图 sha256，
                 交付时渲染所用底图必须与它逐字节相同。
  video_frame  : 从视频抽帧。HDR/SDR 的色彩闸门只在这个分支生效（沿用原 Color Gate）。
标 ◆ 的项（人物构图好不好看、标题文案是否到位）脚本不判断，留人审。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1] / "va7-video-cover-maker"  # docs; these scripts live in va7-cover-tools
sys.path.insert(0, str(HERE.parents[1] / "va7-pipeline" / "scripts"))
sys.path.insert(0, str(HERE))
import cover_assets  # noqa: E402
import gatelib as g  # noqa: E402

STAGE = "cover"
COMPOSITION = SKILL / "references" / "composition-and-reference-qa.md"
STYLE = SKILL / "references" / "va7-cover-style.md"
CASES = cover_assets.CASES  # run cover_assets.py ensure first


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def parse_thresholds() -> dict:
    """从构图规范里解析数值阈值；解析不到就留空让预检失败，不用默认值糊弄。"""
    t = COMPOSITION.read_text(encoding="utf-8")
    out = {}
    m = re.search(r"主标题顶部：画布高度的 `([\d.]+)%-([\d.]+)%`", t)
    if m:
        out["title_top_pct"] = [float(m[1]), float(m[2])]
    m = re.search(r"主标题单行字号：画布高度的 `([\d.]+)%-([\d.]+)%`", t)
    if m:
        out["title_font_pct"] = [float(m[1]), float(m[2])]
    m = re.search(r"副标题字号：画布高度的 `([\d.]+)%-([\d.]+)%`", t)
    if m:
        out["subtitle_font_pct"] = [float(m[1]), float(m[2])]
    m = re.search(r"16:9 与 3:4 默认必须位于 `([\d.]+)-([\d.]+)`，4:3 不超过 `([\d.]+)`", t)
    if m:
        out["head_top_fraction"] = {"16:9": [float(m[1]), float(m[2])], "3:4": [float(m[1]), float(m[2])], "4:3": [0.0, float(m[3])]}
    m = re.search(r"16:9 与 4:3 默认至少 `([\d.]+)`，3:4 默认至少 `([\d.]+)`", t)
    if m:
        out["title_block_min"] = {"16:9": float(m[1]), "4:3": float(m[1]), "3:4": float(m[2])}
    return out


def cmd_preflight(a) -> int:
    items = []
    branch_ok = a.branch in {"direct_image", "video_frame"}
    items.append(g.item("branch_declared", branch_ok, a.branch))
    base = Path(a.base_image).expanduser() if a.base_image else None
    items.append(g.item("base_image_exists", bool(base and base.is_file()), str(base)))
    extra = {"branch": a.branch}
    if base and base.is_file():
        try:
            from PIL import Image
            w, h = Image.open(base).size
            extra["base_size"] = [w, h]
            items.append(g.item("base_size_recorded", True, f"{w}x{h}"))
        except Exception as exc:  # noqa: BLE001
            items.append(g.item("base_size_recorded", False, str(exc)))
        extra["base_sha256"] = sha256(base)
    if a.branch == "direct_image":
        items.append(g.item("direct_image_no_color_processing", True, "用户直接给图：原图就是最终底图，不做任何色彩判断和处理"))
    elif a.branch == "video_frame":
        ok = bool(a.color_check_note)
        items.append(g.item("video_frame_color_gate", ok, a.color_check_note or "抽帧分支需 --color-check-note：写明 raw vs SDR 对照结论"))
    th = parse_thresholds()
    need = {"title_top_pct", "title_font_pct", "subtitle_font_pct", "head_top_fraction", "title_block_min"}
    items.append(g.item("thresholds_parsed_from_spec", need <= set(th), f"解析到：{sorted(th)}"))
    items.append(g.item("spec_files_present", COMPOSITION.exists() and STYLE.exists() and CASES.exists(),
                        "composition-and-reference-qa.md / va7-cover-style.md / cover-case-library"))
    refs = [Path(r).expanduser() for r in (a.reference or [])]
    items.append(g.item("at_least_two_references", len([r for r in refs if r.is_file()]) >= 2, f"{len(refs)} 个参考图"))
    tok = "VA7-COVER-COPY-READ-END-2026-11-16"
    items.append(g.item("copy_patterns_read_to_end", a.copy_patterns_read_token == tok, "先读完 references/cover-copy-patterns.md，把末行读完标记传进来" if a.copy_patterns_read_token != tok else "已读到末行"))
    cj = json.loads(Path(a.copy_json).read_text(encoding="utf-8")) if a.copy_json else None
    if cj is None:
        items.append(g.item("copy_json_present", False, "缺 --copy-json：{title:[...], bullets:[...]}"))
    else:
        bl = [str(b).strip() for b in cj.get("bullets", [])]
        title_all = "".join(cj.get("title", []))
        items.append(g.item("bullets_3_to_4", 3 <= len(bl) <= 4, f"{len(bl)} 条"))
        items.append(g.item("bullets_2_to_5_chars", all(2 <= len(b) <= 5 for b in bl), f"{[b for b in bl if not 2 <= len(b) <= 5] or '各条字数合规'}"))
        def ov(x, y):
            sx, sy = set(x), set(y)
            return len(sx & sy) / max(1, min(len(sx), len(sy)))
        dup = [(x, y) for i, x in enumerate(bl) for y in bl[i + 1:] if ov(x, y) >= 0.6]
        items.append(g.item("bullets_not_overlapping", not dup, f"疑似重复改写同一点：{dup}" if dup else "彼此不重复"))
        td = [b for b in bl if b and b in title_all]
        items.append(g.item("bullets_not_repeat_title", not td, f"与主标题重复：{td}" if td else "不与主标题重复"))
        # 内容达标：每条小标题要声明来自哪个大纲层，层互不相同，且和该层的 label/judgment 有字面关联
        src = cj.get("bullet_sources") or []
        if not a.outline:
            items.append(g.item("bullets_trace_to_outline", False, "缺 --outline：小标题内容必须能追到已确认大纲的层"))
        else:
            ol = json.loads(Path(a.outline).read_text(encoding="utf-8"))
            layers = {l["id"]: l for l in ol.get("layers", [])}
            bad, seen = [], []
            for b in bl:
                m = next((x for x in src if x.get("bullet") == b), None)
                lid = m.get("layer_id") if m else None
                L = layers.get(lid)
                text = (L.get("label", "") + L.get("judgment", "")) if L else ""
                if not L or sum(1 for c in set(b) if c in text) < max(2, len(set(b)) // 2):
                    bad.append(b)
                seen.append(lid)
            items.append(g.item("bullets_trace_to_outline", not bad, f"这些小标题追不到大纲层或和该层无字面关联：{bad}；cover copy 里要给 bullet_sources=[{{bullet, layer_id}}]" if bad else "每条都对应一个大纲层"))
            items.append(g.item("bullets_distinct_layers", len(set(seen)) == len(seen), f"层：{seen}；两条不能来自同一层（同一点的重复改写）"))
        items.append(g.item("◆小标题平行/核心", True, "统一名词短语或动宾短语、删掉任一条都损失结构：脚本不判断，留人审", human=True))
    items.append(g.item("copy_confirmed_by_human", bool(a.copy_confirmed), "封面文案经人确认：--copy-confirmed '主标题/副标题'" if not a.copy_confirmed else a.copy_confirmed))
    items.append(g.item("◆构图好不好看", True, "判断项，留人审", human=True))
    g.write_preflight(a.out, STAGE, items, {**extra, "thresholds": th, "references": [str(r) for r in refs], "copy": a.copy_confirmed})
    return g.report(items, STAGE, {"thresholds": th})


def cmd_deliver(a) -> int:
    pre = g.require_preflight(a.preflight, STAGE)
    items = []
    frame = Path(a.frame).expanduser()
    if pre["branch"] == "direct_image":
        items.append(g.item("frame_is_original_image", frame.is_file() and sha256(frame) == pre["base_sha256"],
                            "渲染所用底图必须与预检时记录的原图逐字节相同"))
    else:
        items.append(g.item("frame_not_raw_hdr", "_raw" not in frame.stem, f"底图 {frame.name}：抽帧分支不得用 _raw"))
    qa = json.loads(Path(a.qa_report).read_text(encoding="utf-8")) if a.qa_report else None
    items.append(g.item("strict_qa_passed", bool(qa) and qa.get("passed") is True and qa.get("strict") is True, "qa_cover_set.py --strict 的 JSON 输出，passed 必须为 true" if not qa else f"passed={qa.get('passed')} strict={qa.get('strict')}"))
    items.append(g.item("compare_board_exists", bool(a.board) and Path(a.board).is_file(), "出图后必须附对照板，没有就不算交付"))
    if a.huazi_preflight:
        hp = json.loads(Path(a.huazi_preflight).read_text(encoding="utf-8"))
        items.append(g.item("huazi_preflight_passed", hp.get("status") == "passed" and hp.get("version") == 2, "花字预检"))
    hr = json.loads(a.human_review) if a.human_review else {}
    hr_ok = all(hr.get(k) for k in ("by", "message_id", "quote"))
    items.append(g.item("human_reviewed_composition_and_copy", hr_ok, "人已看过构图和文案" if hr_ok else "缺 --human-review {by,message_id,quote}：构图和文案要人看过说「行」，agent 不得自填"))
    rc = g.report(items, STAGE)
    if rc == 0:
        deliverables = [frame] + ([Path(a.board)] if a.board else [])
        print(json.dumps({"校验码": g.check_code(STAGE, a.preflight, *deliverables), "说明": "交付消息末尾必须带这个码"}, ensure_ascii=False))
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preflight")
    p.add_argument("--branch", required=True, choices=["direct_image", "video_frame"])
    p.add_argument("--base-image", required=True)
    p.add_argument("--color-check-note")
    p.add_argument("--reference", action="append")
    p.add_argument("--copy-confirmed")
    p.add_argument("--outline", help="已确认大纲 outline.json：小标题每条必须对应一个互不相同的大纲层")
    p.add_argument("--copy-json", help="封面文案：{title:[行...], bullets:[3-4条]}；脚本查条数、字数、平行性之外的重复")
    p.add_argument("--copy-patterns-read-token", help="cover-copy-patterns.md 末行「读完标记」；证明读到了末尾")
    p.add_argument("--out", default="cover_preflight.json")
    p.set_defaults(fn=cmd_preflight)
    d = sub.add_parser("deliver")
    d.add_argument("--preflight", default="cover_preflight.json")
    d.add_argument("--frame", required=True, help="渲染实际使用的底图")
    d.add_argument("--human-review", help="人逐项看过构图和文案：{by, message_id, quote}；agent 不得自填")
    d.add_argument("--qa-report", help="qa_cover_set.py 输出 JSON")
    d.add_argument("--board", help="对照板图片")
    d.add_argument("--huazi-preflight")
    d.set_defaults(fn=cmd_deliver)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())

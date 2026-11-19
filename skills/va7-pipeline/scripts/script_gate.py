#!/usr/bin/env python3
"""写稿环节的预检、备选 hook 校验、交付检查。

子命令（顺序）：
  preflight : 开工前。查文风档案、content brief、pre_draft_gate 结论、约束清单状态，写 script_preflight.json
  outline   : 登记大纲（outline.json）→ 人确认（--confirm --by --message-id --quote）。大纲是写全文的前提输入
  hooks     : 大纲确认之后、全文之前。校验 3 个备选 hook；人选定后用 --choose N 记录
  deliver   : 交稿前。要求预检通过、大纲已确认、hook 已选定；成稿须按大纲分段（--mapping），通过才输出校验码

标 ◆ 的判断项（张力是否打在观众身上、论点深度、立场是否真是 VA7 的、递进是否真实）脚本不判断，
只在输出的 human_review 里列出，由人审。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT_SKILL = HERE.parents[1] / "va7-script"  # this gate serves va7-script
sys.path.insert(0, str(HERE.parents[1] / "va7-interview" / "scripts"))
sys.path.insert(0, str(SCRIPT_SKILL / "scripts"))
sys.path.insert(0, str(HERE))
import gatelib as g  # noqa: E402
from count_script_chars import count_chars  # noqa: E402
import style_check  # noqa: E402

STAGE = "script"
VOICE_FALLBACK = SCRIPT_SKILL / "references" / "voice" / "va7.md"
HOOK_TYPES = {"痛点问句", "近身经历", "直接抛结论", "案例冲突", "具体问题", "反共识", "ABC"}
SOURCE_LABELS = {"VA7原话", "素材", "推断"}
TARGET_MIN, TARGET_MAX = 1800, 2200  # 目标区间，不是硬门槛；区间外必须在 --length-note 写原因
MD_PATTERNS = [r"^\s*[-*•]\s", r"^\s*\d+[.、)]\s", r"^#{1,6}\s", r"\*\*", r"`", r"^\s*>\s"]


ADD_KINDS = {"机制", "判别标准", "边界条件", "结构调整"}
OVERLAP_LIMIT = 0.6   # 成稿 8 字片段中有多大比例直接来自输入材料，超过就必须交「新增清单」
ANCHOR_NOVELTY = 0.3  # 新增锚点句与材料的片段重合比例须低于此值


def _norm(t: str) -> str:
    return re.sub(r"[\s\W_]+", "", t)


def _shingles(t: str, n: int = 8) -> set:
    t = _norm(t)
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def _overlap(t: str, source_shingles: set) -> float:
    sh = _shingles(t)
    return len(sh & source_shingles) / len(sh) if sh else 0.0


def additions_items(draft: str, source: str | None, additions_path: str | None, organize_only: bool) -> list:
    """相对输入材料的新增：整理不等于创作，没有新增必须明说「仅整理」。"""
    if not source:
        return []
    src = _shingles(Path(source).read_text(encoding="utf-8"))
    ratio = _overlap(draft, src)
    items = [g.item("overlap_with_source", True, f"成稿 8 字片段中 {ratio:.0%} 直接来自输入材料（阈值 {OVERLAP_LIMIT:.0%}）")]
    if ratio <= OVERLAP_LIMIT:
        return items
    if organize_only:
        items.append(g.item("declared_organize_only", True, "已声明仅整理，未新增论证；交付说明里必须写明", human=True))
        return items
    if not additions_path:
        items.append(g.item("additions_listed", False, "成稿与材料高度重合：交 --additions（新增了哪些机制/判别标准/边界条件/结构调整），或用 --organize-only 明说仅整理"))
        return items
    adds = json.loads(Path(additions_path).read_text(encoding="utf-8"))
    nd = _norm(draft)
    good = 0
    for i, ad in enumerate(adds, 1):
        anchor = ad.get("anchor", "")
        ok_kind = ad.get("kind") in ADD_KINDS
        in_draft = bool(anchor) and _norm(anchor) in nd
        novelty = _overlap(anchor, src) if anchor else 1.0
        ok = ok_kind and in_draft and novelty < ANCHOR_NOVELTY and len(_norm(anchor)) >= 15 and bool(ad.get("why"))
        good += ok
        items.append(g.item(f"addition{i}_{ad.get('kind')}", ok,
                            f"锚点在成稿中={in_draft}；与材料重合={novelty:.0%}；类型合法={ok_kind}；有 why={bool(ad.get('why'))}；锚点≥15字={len(_norm(anchor)) >= 15}"))
    items.append(g.item("at_least_one_real_addition", good >= 1, f"有效新增 {good} 条"))
    items.append(g.item("◆新增是否真是更深的论证", True, "脚本只能证明新增句存在且不是抄材料；是不是真有深度由人审", human=True))
    return items


def _para_by_layer(body: str, ol: dict, mapping_path: str):
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    mapping = {m["layer_id"]: m for m in json.loads(Path(mapping_path).read_text(encoding="utf-8"))}
    out = {}
    for ly in ol["layers"]:
        m = mapping.get(ly["id"])
        f = _norm(m.get("paragraph_first_sentence", "")) if m else ""
        out[ly["id"]] = next((i for i, p in enumerate(paras) if f and _norm(p).startswith(f)), -1)
    return paras, out


def _bigrams(t: str, stop: list) -> set:
    t = _norm(t)
    return {t[i:i + 2] for i in range(len(t) - 1) if t[i:i + 2] not in stop and not any(sw in t[i:i + 2] for sw in ("的", "了", "是", "我", "你", "他"))}


def selfcheck_items(body: str, ol: dict, mapping_path: str | None, path: str | None) -> list:
    """把原本只能留给人判断的四项变成「必须声明 + 脚本核对声明与成稿一致」：论据类型、局限与引出、结尾。
    声明里的每个句子必须是成稿逐字存在的一句；声明类型与句子特征必须匹配。对错仍由人审（见人逐项审过）。"""
    import json as _j
    rules = _j.loads(style_check.rules_file().read_text(encoding="utf-8"))
    if not mapping_path:
        return []
    if not path:
        return [g.item("style_selfcheck_given", False, "缺 --style-selfcheck：{layers:[…], ending:{…}, waivers?:[…]}，格式见 SKILL.md 强制流程第 5 步")]
    sc = json.loads(Path(path).read_text(encoding="utf-8"))
    paras, pos = _para_by_layer(body, ol, mapping_path)
    layers = ol["layers"]
    by = {x.get("layer_id"): x for x in sc.get("layers", [])}
    lim_r, ev_r = rules["limitation"], rules["evidence"]
    cw = rules["connector"]["words"]
    items = []

    def seg(idx):
        end = len(paras)
        for ly2 in layers:
            j = pos.get(ly2["id"], -1)
            if j > idx:
                end = min(end, j)
        return paras[idx:end]

    for k, ly in enumerate(layers):
        x = by.get(ly["id"])
        idx = pos.get(ly["id"], -1)
        if not x or idx < 0:
            items.append(g.item(f"selfcheck_{ly['id']}_present", False, "缺这一层的自检，或这一层没有对应段落"))
            continue
        segtxt = _norm("".join(seg(idx)))
        # 局限
        lim_s = x.get("limitation_sentence", "")
        ok = bool(_norm(lim_s)) and _norm(lim_s) in segtxt
        items.append(g.item(f"selfcheck_{ly['id']}_limitation_in_layer", ok, "局限句必须是这一层（段首到下一层段首之前）里逐字存在的一句"))
        items.append(g.item(f"selfcheck_{ly['id']}_limitation_type", x.get("limitation_type") in lim_r["types"], f"类型须是 {lim_r['types']}"))
        items.append(g.item(f"selfcheck_{ly['id']}_limitation_marker", any(m in lim_s for m in lim_r["markers"]), "局限句必须含局限词（只/不过/还没/有人会说…），不能是复述结论"))
        if k < len(layers) - 1:
            nxt = pos.get(layers[k + 1]["id"], -1)
            lead = _norm(x.get("leads_to_sentence", ""))
            ok_lead = nxt >= 0 and bool(lead) and _norm(paras[nxt]).startswith(lead)
            items.append(g.item(f"selfcheck_{ly['id']}_leads_to_next_layer", ok_lead, "引出句必须是下一层段落的第一句"))
            shared = _bigrams(lim_s, lim_r["bridge_stop"]) & _bigrams(split_first(paras[nxt]) if nxt >= 0 else "", lim_r["bridge_stop"])
            items.append(g.item(f"selfcheck_{ly['id']}_bridge_shared_words", bool(shared), f"局限句与下一层段首句的共同词：{sorted(shared)[:4]}；没有共同词说明引出是硬接的"))
        # 论据
        evs = x.get("evidence") or []
        items.append(g.item(f"selfcheck_{ly['id']}_evidence_declared", bool(evs), "每层至少声明一条论据（类型+成稿原句）"))
        for j, e in enumerate(evs, 1):
            t, sent = e.get("type"), e.get("sentence", "")
            in_seg = bool(_norm(sent)) and _norm(sent) in segtxt
            feat = {"亲历事实": "我" in sent, "具体数字": bool(re.search(r"[0-9]|[一二三四五六七八九十百千万两几]+(个|次|年|天|小时|分钟|倍|成|块|元|人|件|步|条|家|位|周|月)", sent)),
                    "客户案例": "客户" in sent, "机制因果链": any(w in sent for w in cw)}.get(t, False)
            items.append(g.item(f"selfcheck_{ly['id']}_evidence{j}", t in ev_r["types"] and in_seg and feat,
                                f"类型={t}（须是 {ev_r['types']}）；原句在本层={in_seg}；句子具备该类型特征={feat}"))
    # 结尾
    en = sc.get("ending") or {}
    er = rules["ending"]
    last = split_first_last(body)
    ok_type = en.get("type") in er["types"]
    same = bool(_norm(en.get("sentence", ""))) and _norm(en["sentence"]) == _norm(last)
    items.append(g.item("selfcheck_ending_type", ok_type, f"类型须是 {er['types']}"))
    items.append(g.item("selfcheck_ending_is_actual_last_sentence", same, "声明的结尾必须就是成稿的最后一句"))
    if en.get("type") == "用户指定修辞":
        okm = bool(en.get("message_id")) and bool(en.get("quote"))
        items.append(g.item("selfcheck_ending_user_specified", okm, "用户指定修辞必须附该用户的消息 id 和原话"))
    else:
        items.append(g.item("selfcheck_ending_len", len(_norm(last)) <= er["max_len"], f"末句 {len(_norm(last))} 字，上限 {er['max_len']}"))
    # 类比豁免
    for w in sc.get("waivers", []):
        items.append(g.item(f"waiver_{w.get('marker')}", bool(w.get("reason")), f"类比豁免：{w.get('reason')}（人审时重点看）", human=True))
    items.append(g.item("◆局限讲得对不对、引出自不自然", True, "脚本只核对声明与成稿一致；对错由人逐项审过", human=True))
    return items


def split_first(p: str) -> str:
    ss = [x for x in re.split(r"[。？！?!；]", p) if x.strip()]
    return ss[0] if ss else ""


def split_first_last(body: str) -> str:
    ps = [p for p in re.split(r"\n\s*\n", body.strip()) if p.strip()]
    ss = [x for x in re.split(r"[。？！?!；]", ps[-1]) if x.strip()] if ps else []
    return ss[-1].strip() if ss else ""


def constraints_items(pre: dict, body: str, result_path: str | None, style_items: list) -> list:
    """预检登记的每条约束，交付时必须逐条回写：已遵守（带证据）/ 不适用（带理由）；未遵守即不放行。"""
    cons = pre.get("constraints") or []
    if not result_path:
        return [g.item("constraints_written_back", False, "缺 --constraints-result：对预检登记的每条约束写 status 和 evidence")]
    res = {x.get("id"): x for x in json.loads(Path(result_path).read_text(encoding="utf-8"))}
    nb = _norm(body)
    passed_checks = {i["id"] for i in style_items if i["status"] == g.PASSED}
    items = []
    for c in cons:
        x = res.get(c["id"])
        if not x:
            items.append(g.item(f"constraint_{c['id']}", False, "没有回写"))
            continue
        st, ev = x.get("status"), (x.get("evidence") or "").strip()
        if st == "已遵守":
            if ev.startswith("check:"):
                ok, why = ev[6:] in passed_checks, f"引用脚本检查项 {ev[6:]}"
            else:
                ok, why = bool(ev) and _norm(ev) in nb, "证据必须是成稿里逐字存在的一句，或 check:<检查项id>"
        elif st == "不适用":
            ok, why = bool(ev), "不适用必须写理由"
        else:
            ok, why = False, f"状态 {st!r}：只允许 已遵守 / 不适用；未遵守不放行"
        items.append(g.item(f"constraint_{c['id']}", ok, why))
    return items


def voice_profile_path(config_path: str | None) -> Path | None:
    from va7config import load_config, resolve
    cfg, cfg_file = load_config(config_path)
    p = resolve(cfg_file, (cfg.get("voice_profile") or {}).get("path"))
    if p and p.exists():
        return p
    return VOICE_FALLBACK if VOICE_FALLBACK.exists() else None


def skill_end_token() -> str:
    for line in reversed((SCRIPT_SKILL / "SKILL.md").read_text(encoding="utf-8").splitlines()):
        if line.startswith("读完标记："):
            return line.split("：", 1)[1].strip()
    return ""


def cmd_preflight(a) -> int:
    items = []
    tok = skill_end_token()
    items.append(g.item("skill_read_to_end", bool(tok) and a.skill_read_token == tok,
                        "SKILL.md 必须读到最后一行，把末行「读完标记」传给 --skill-read-token"))
    vp = voice_profile_path(a.config)
    ok = bool(vp and vp.read_text(encoding="utf-8").strip())
    items.append(g.item("voice_profile_exists", ok, str(vp) if vp else "缺文风档案：停下，不许用笔记或记忆替代"))
    brief_ok, brief_detail = False, "未提供 --brief"
    if a.brief:
        from validate_content_brief import load_brief
        _, rep = load_brief(a.brief)
        brief_ok, brief_detail = rep.get("ok") is True, json.dumps(rep, ensure_ascii=False)[:300]
    items.append(g.item("content_brief_valid", brief_ok, brief_detail))
    gate_ok, gate_detail = False, "未提供 --gate-result（先跑 pre_draft_gate.py 并保存输出）"
    if a.gate_result:
        gr = json.loads(Path(a.gate_result).read_text(encoding="utf-8"))
        gate_ok = gr.get("ok") is True
        gate_detail = f"decision={gr.get('decision')} may_write_full_draft={gr.get('may_write_full_draft')}"
        if a.want == "full" and not gr.get("may_write_full_draft"):
            gate_ok, gate_detail = False, gate_detail + "；门控不允许写全文，本轮只能出大纲"
    items.append(g.item("pre_draft_gate_recorded", gate_ok, gate_detail))
    cons_ok, cons_detail = False, "未提供 --constraints"
    saved_cons = None
    if a.constraints:
        cons = json.loads(Path(a.constraints).read_text(encoding="utf-8"))
        saved_cons = cons
        missing = [c.get("id", "?") for c in cons if not c.get("status")]
        cons_ok = bool(cons) and not missing
        cons_detail = f"{len(cons)} 条约束；缺状态：{missing}" if cons else "约束清单为空"
    items.append(g.item("constraints_have_status", cons_ok, cons_detail))
    items.append(g.item("conflict_priority_acknowledged", True,
                        "冲突时：不编造和本次明确指令 > VA7 最近带日期的明确反馈 > 文风原档 > hook-patterns/writing-principles 清单", human=False))
    for hid in ["立场是否真是 VA7 的", "递进是否真实", "hook 张力是否打在观众身上", "论点深度"]:
        items.append(g.item(f"◆{hid}", True, "判断项，留人审", human=True))
    keep = {"hook_selected": None, "hook_candidates": None, "outline": None}
    prev = Path(a.out)
    if prev.exists():
        try:
            old_doc = json.loads(prev.read_text(encoding="utf-8"))
            keep = {k: old_doc.get(k) for k in keep}
        except Exception:  # noqa: BLE001
            pass
    doc = g.write_preflight(a.out, STAGE, items, {"want": a.want, "constraints": saved_cons, **keep})
    return g.report(items, STAGE, {"next": "出论证大纲存成 outline.json → script_gate.py outline --file outline.json → 人确认 → outline --confirm … → hooks → 写全文 → deliver"})


def _load_pre(path) -> dict:
    pre = json.loads(Path(path).read_text(encoding="utf-8"))
    if pre.get("stage") != STAGE or pre.get("version") != 3:
        g.stop("预检文件不是写稿环节新格式")
    return pre


def _save_pre(path, pre: dict) -> None:
    Path(path).write_text(json.dumps(pre, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_outline(a) -> int:
    """大纲是确认过的产物：登记 → 人确认 → 之后写全文、hook、交付都只认这一版。"""
    import hashlib
    pre = _load_pre(a.preflight)
    if a.confirm:
        ol = pre.get("outline")
        if not ol:
            g.stop("还没有登记大纲：先 outline --file outline.json")
        miss = [k for k in ("by", "message_id", "quote") if not getattr(a, k)]
        if miss:
            g.stop(f"确认大纲必须带 --by / --message-id / --quote（人的原话和消息 id），缺：{miss}")
        ol["confirmed"] = {"by": a.by, "message_id": a.message_id, "quote": a.quote, "version": ol["version"]}
        _save_pre(a.preflight, pre)
        print(json.dumps({"passed": True, "outline_version": ol["version"], "confirmed_by": a.by,
                          "next": "出 3 个备选 hook：script_gate.py hooks --candidates ...；确认记录的 message_id 与原话请人抽查"}, ensure_ascii=False, indent=2))
        return 0
    raw = Path(a.file).read_text(encoding="utf-8")
    ol = json.loads(raw)
    problems = []
    layers = ol.get("layers") or []
    if not ol.get("version"):
        problems.append("缺 version")
    if len(layers) < 2:
        problems.append("至少 2 层")
    ids = set()
    for i, ly in enumerate(layers, 1):
        if not ly.get("id") or ly["id"] in ids:
            problems.append(f"第 {i} 层缺 id 或 id 重复")
        ids.add(ly.get("id"))
        if not 0 < len(ly.get("label", "")) <= 8:
            problems.append(f"{ly.get('id')} 标签必须 1-8 字")
        if not ly.get("judgment"):
            problems.append(f"{ly.get('id')} 缺 judgment（这一层让观众多会的判断）")
        if not ly.get("anchor"):
            problems.append(f"{ly.get('id')} 缺 anchor（支撑这层的机制或事实锚点）")
        if ly.get("source") not in SOURCE_LABELS:
            problems.append(f"{ly.get('id')} source 必须是 {sorted(SOURCE_LABELS)} 之一")
        if not isinstance(ly.get("must_include", []), list):
            problems.append(f"{ly.get('id')} must_include 必须是词表")
    src_text = Path(a.source).read_text(encoding="utf-8") if getattr(a, "source", None) else None
    problems += outline_structure_problems(ol, src_text)
    if problems:
        g.stop("；".join(problems))
    pre["outline"] = {"version": ol["version"], "sha256": hashlib.sha256(raw.encode()).hexdigest()[:12], "layers": layers, "confirmed": None}
    _save_pre(a.preflight, pre)
    print(json.dumps({"passed": True, "outline_version": ol["version"], "layers": len(layers),
                      "next": "把大纲给人确认；人确认后：outline --confirm --by <人> --message-id <om_…> --quote <原话>。未确认前不放行 hook 和全文"}, ensure_ascii=False, indent=2))
    return 0


def outline_structure_problems(ol: dict, source_text: str | None) -> list:
    """大纲阶段的结构自检：删层测试 + 来源检查（speaking-outlines.md 自检两条）。
    删层测试：抽掉任何一层其余仍能讲通即为平铺——所以每层必须声明「谁依赖它」和「抽掉它哪句论断失去前提」，
              依赖只能指向更靠后的层或 thesis，且被依赖层的文字与本层有共同词；每层都被后面某层依赖才算环环相扣。
    来源检查：一层对应一个出处多半是按材料攒的，不是按逻辑挖的——所以每层声明来源，素材原话必须在材料里逐字存在；
              「每层恰一个出处且互不相同」判平铺；第二层起必须回答前一层声明的局限（answers_limit_of 等于前一层 limitation）。"""
    probs = []
    layers = ol.get("layers") or []
    ids = [ly.get("id") for ly in layers]
    stop = ["这个", "一个", "我们", "他们", "这是", "不是", "所以", "因为", "没有", "什么", "就是", "自己", "还是", "能够"]
    src_norm = _norm(source_text) if source_text else None
    all_refs = []
    for k, ly in enumerate(layers):
        lid = ly.get("id")
        nb = ly.get("needed_by") or []
        if not nb:
            probs.append(f"{lid} 没有声明 needed_by：抽掉这一层后面哪一层会失去前提？没人依赖它就是平铺")
        for d in nb:
            if d != "thesis" and (d not in ids or ids.index(d) <= k):
                probs.append(f"{lid} needed_by 里的 {d} 必须是更靠后的层或 thesis")
        if k == len(layers) - 1 and nb != ["thesis"]:
            probs.append(f"{lid} 是最后一层，needed_by 必须是 [\"thesis\"]")
        bw = ly.get("breaks_without", "")
        if len(_norm(bw)) < 10:
            probs.append(f"{lid} breaks_without 至少 10 字：抽掉这层，哪一句论断失去前提")
        mine = _bigrams(f"{ly.get('judgment','')}{ly.get('anchor','')}", stop)
        for d in nb:
            if d == "thesis":
                continue
            dep = layers[ids.index(d)] if d in ids else {}
            theirs = _bigrams(f"{dep.get('judgment','')}{dep.get('anchor','')}", stop)
            if not (mine & theirs):
                probs.append(f"{lid} 声称被 {d} 依赖，但两层的判断和锚点没有共同词，依赖关系站不住")
        srcs = ly.get("sources") or []
        if not srcs:
            probs.append(f"{lid} 没有声明 sources")
        for sc in srcs:
            kind = sc.get("kind")
            if kind not in ("素材原话", "口述", "推断"):
                probs.append(f"{lid} 来源 kind 必须是 素材原话/口述/推断")
            ref = sc.get("ref", "")
            if kind == "素材原话":
                if src_norm is None:
                    probs.append(f"{lid} 声明了素材原话但没有提供 --source 材料文件，无法核对")
                elif _norm(ref) not in src_norm or not _norm(ref):
                    probs.append(f"{lid} 的素材原话在材料里找不到：{ref[:20]}")
            if kind == "推断" and not sc.get("reason"):
                probs.append(f"{lid} 的推断必须写 reason")
            all_refs.append(_norm(ref))
        lim = ly.get("limitation", "")
        if len(_norm(lim)) < 6:
            probs.append(f"{lid} 缺 limitation：这一层讲完后还剩什么没解决")
        if k > 0:
            prev_lim = layers[k - 1].get("limitation", "")
            if _norm(ly.get("answers_limit_of", "")) != _norm(prev_lim) or not _norm(prev_lim):
                probs.append(f"{lid} 的 answers_limit_of 必须等于上一层的 limitation（逻辑挖出来的，不是按材料攒的）")
    for ly in layers:
        lid = ly.get("id")
        pts = ly.get("points") or []
        types = [x.get("type") for x in pts]
        if "观点" not in types:
            probs.append(f"{lid} points 里至少要有一条「观点」（这一层用什么观点）")
        if not ({"例子", "数据"} & set(types)):
            probs.append(f"{lid} points 里至少要有一条「例子」或「数据」（拿什么证明）")
        for j, x in enumerate(pts, 1):
            tag = f"{lid}.points[{j}]"
            if x.get("type") not in ("观点", "例子", "数据", "反方质疑"):
                probs.append(f"{tag} type 必须是 观点/例子/数据/反方质疑")
            if not (x.get("content") or "").strip():
                probs.append(f"{tag} 缺 content")
            kt = x.get("key_terms") or []
            if not kt:
                probs.append(f"{tag} 缺 key_terms：正文这一层里必须出现的词，用来核对这条真被写进去了")
            sk = x.get("source", {}).get("kind")
            ref = x.get("source", {}).get("ref", "")
            if sk not in ("素材原话", "推断", "待补"):
                probs.append(f"{tag} source.kind 必须是 素材原话/推断/待补")
            if sk == "素材原话":
                if src_norm is None:
                    probs.append(f"{tag} 声明素材原话但没提供 --source")
                elif not _norm(ref) or _norm(ref) not in src_norm:
                    probs.append(f"{tag} 素材原话在材料里找不到：{ref[:20]}")
            if sk == "推断" and not x.get("source", {}).get("reason"):
                probs.append(f"{tag} 推断必须写 reason")
            if x.get("type") == "数据" and sk == "推断":
                probs.append(f"{tag} 数据不能是推断：只能来自素材原话，或标「待补」让人补，不编数字")
    per = [sorted({_norm(sc.get('ref', '')) for sc in (ly.get('sources') or [])}) for ly in layers]
    if layers and all(len(x) == 1 for x in per) and len({x[0] for x in per}) == len(per):
        probs.append("每层恰好一个出处且互不相同：这是按材料攒的，不是按逻辑挖的；至少有一个出处要被两层共同使用，或某层有多个出处")
    return probs


def require_confirmed_outline(pre: dict) -> dict:
    ol = pre.get("outline")
    if not ol or not ol.get("confirmed") or ol["confirmed"].get("version") != ol["version"]:
        g.stop("没有已确认的大纲：先 outline --file，再由人确认 outline --confirm。大纲是写全文的前提输入")
    return ol


def outline_binding_items(body: str, ol: dict, mapping_path: str | None) -> list:
    """成稿必须按大纲写：每层一个段落，顺序一致，段首是映射的锚句，且含该层要求的词。"""
    items = [g.item("outline_version_cited", True, f"大纲 {ol['version']}，已由 {ol['confirmed']['by']} 确认（{ol['confirmed']['message_id']}）")]
    if not mapping_path:
        items.append(g.item("outline_mapping_given", False, "缺 --mapping：[{layer_id, paragraph_first_sentence}]，每层对应成稿里哪一段（段首句）"))
        return items
    mapping = {m.get("layer_id"): m for m in json.loads(Path(mapping_path).read_text(encoding="utf-8"))}
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    items.append(g.item("paragraphs_ge_layers", len(paras) >= len(ol["layers"]), f"成稿 {len(paras)} 段，大纲 {len(ol['layers'])} 层；必须分段"))
    last = -1
    for ly in ol["layers"]:
        m = mapping.get(ly["id"])
        if not m:
            items.append(g.item(f"layer_{ly['id']}_mapped", False, "这一层没有对应的成稿段"))
            continue
        first = _norm(m.get("paragraph_first_sentence", ""))
        idx = next((i for i, p in enumerate(paras) if first and _norm(p).startswith(first)), -1)
        items.append(g.item(f"layer_{ly['id']}_paragraph_found", idx >= 0, "映射的段首句必须是成稿某一段的开头"))
        if idx >= 0:
            items.append(g.item(f"layer_{ly['id']}_in_order", idx > last, f"位置 {idx}，上一层 {last}；顺序必须与大纲一致"))
            last = max(last, idx)
            nxt = [m2 for m2 in mapping.values() if m2 is not m]
            seg_end = len(paras)
            for ly2 in ol["layers"]:
                m2 = mapping.get(ly2["id"])
                if m2 and m2 is not m:
                    f2 = _norm(m2.get("paragraph_first_sentence", ""))
                    j = next((i for i, p in enumerate(paras) if f2 and _norm(p).startswith(f2)), -1)
                    if j > idx:
                        seg_end = min(seg_end, j)
            seg = _norm("".join(paras[idx:seg_end]))
            miss = [w for w in ly.get("must_include", []) if _norm(w) not in seg]
            items.append(g.item(f"layer_{ly['id']}_covers_anchor_terms", not miss, f"该层段落缺：{miss}" if miss else "该层要求的词都在"))
    paras_all = paras
    for ly in ol["layers"]:
        idx = next((i for i, p in enumerate(paras_all) if mapping.get(ly["id"]) and _norm(p).startswith(_norm(mapping[ly["id"]].get("paragraph_first_sentence", "")))), -1)
        if idx < 0:
            continue
        end = len(paras_all)
        for ly2 in ol["layers"]:
            m2 = mapping.get(ly2["id"])
            if m2 and ly2 is not ly:
                j = next((i for i, p in enumerate(paras_all) if _norm(p).startswith(_norm(m2.get("paragraph_first_sentence", "")))), -1)
                if j > idx:
                    end = min(end, j)
        segtxt = _norm("".join(paras_all[idx:end]))
        for k, x in enumerate(ly.get("points") or [], 1):
            miss = [t for t in x.get("key_terms", []) if _norm(t) not in segtxt]
            items.append(g.item(f"point_{ly['id']}_{k}_{x.get('type')}_written", not miss, f"大纲拟用的{x.get('type')}：{x.get('content','')[:20]}…；正文缺：{miss}" if miss else f"{x.get('type')}已写入"))
    items.append(g.item("◆各层段落是否真的在写这一层的判断", True, "脚本只核对对应、顺序和关键词；写得对不对留人审", human=True))
    return items


def cmd_plan(a) -> int:
    """hook 选定后，把「hook + 大纲」放在一起让人再看一次、确认，之后才开始写全文。"""
    pre = _load_pre(a.preflight)
    ol = require_confirmed_outline(pre)
    sel = pre.get("hook_selected")
    if not sel:
        g.stop("还没有选定 hook：先 hooks --choose N")
    if a.confirm:
        miss = [k for k in ("by", "message_id", "quote") if not getattr(a, k)]
        if miss:
            g.stop(f"确认必须带 --by / --message-id / --quote（人的原话和消息 id），缺：{miss}")
        pre["plan_confirmed"] = {"by": a.by, "message_id": a.message_id, "quote": a.quote,
                                 "outline_version": ol["version"], "hook_index": sel["index"], "hook_text": sel["text"]}
        _save_pre(a.preflight, pre)
        print(json.dumps({"passed": True, "plan_confirmed": pre["plan_confirmed"], "next": "可以写全文了：输入只有 hook + 大纲 + 素材池"}, ensure_ascii=False, indent=2))
        return 0
    show = {"hook": sel["text"], "hook_type": sel["type"], "outline_version": ol["version"],
            "layers": [{"id": ly["id"], "label": ly["label"], "judgment": ly["judgment"]} for ly in ol["layers"]]}
    print(json.dumps({"请把下面这份「hook + 大纲」发给人确认；人确认后：plan --confirm --by <人> --message-id <om_…> --quote <原话>": show}, ensure_ascii=False, indent=2))
    return 0


def require_plan(pre: dict, ol: dict) -> dict:
    pc, sel = pre.get("plan_confirmed"), pre.get("hook_selected")
    if not pc or not sel or pc.get("outline_version") != ol["version"] or pc.get("hook_index") != sel["index"] or pc.get("hook_text") != sel["text"]:
        g.stop("hook + 大纲还没有合并确认（或确认后又改过 hook / 大纲）：先 plan，人确认后 plan --confirm，再写全文")
    return pc


def cmd_hooks(a) -> int:
    pre = json.loads(Path(a.preflight).read_text(encoding="utf-8"))
    if pre.get("stage") != STAGE or pre.get("version") != 3:
        g.stop("预检文件不是写稿环节新格式")
    if a.choose is not None:
        cands = pre.get("hook_candidates")
        if not cands:
            g.stop("还没有通过校验的备选 hook，先跑 hooks --candidates")
        if not 1 <= a.choose <= len(cands):
            g.stop(f"--choose 必须在 1..{len(cands)}")
        pre["hook_selected"] = {"index": a.choose, **cands[a.choose - 1]}
        Path(a.preflight).write_text(json.dumps(pre, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"passed": True, "hook_selected": pre["hook_selected"]}, ensure_ascii=False, indent=2))
        return 0
    require_confirmed_outline(pre)
    cands = json.loads(Path(a.candidates).read_text(encoding="utf-8"))
    problems = []
    if len(cands) != 3:
        problems.append(f"必须正好 3 个备选，现在 {len(cands)} 个")
    for i, c in enumerate(cands, 1):
        text = c.get("text", "")
        if c.get("type") not in HOOK_TYPES:
            problems.append(f"#{i} type 必须是 {sorted(HOOK_TYPES)} 之一")
        if not c.get("basis"):
            problems.append(f"#{i} 缺 basis（依据：为什么这个开头能被正文兑现）")
        if c.get("source") not in SOURCE_LABELS:
            problems.append(f"#{i} source 必须是 {sorted(SOURCE_LABELS)} 之一")
        if re.search(r"\d", text) and not c.get("number_source"):
            problems.append(f"#{i} 含数字必须给 number_source（真实来源），或改掉数字")
        if len(text) < 8:
            problems.append(f"#{i} 太短")
    if len({c.get("type") for c in cands}) < 2:
        problems.append("3 个备选至少要覆盖 2 种类型")
    if problems:
        g.stop("；".join(problems))
    pre["hook_candidates"] = cands
    pre["hook_selected"] = None
    Path(a.preflight).write_text(json.dumps(pre, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": True, "next": "把 3 个候选给人，人选定后：hooks --preflight ... --choose N；没有选定，deliver 不放行"}, ensure_ascii=False, indent=2))
    return 0


def cmd_deliver(a) -> int:
    pre = g.require_preflight(a.preflight, STAGE)
    items = []
    ol = require_confirmed_outline(pre)
    pc = require_plan(pre, ol)
    items.append(g.item("plan_confirmed_hook_and_outline", True, f"hook + 大纲 {ol['version']} 已由 {pc['by']} 合并确认（{pc['message_id']}）"))
    sel = pre.get("hook_selected")
    items.append(g.item("hook_selected_by_human", bool(sel), "未选定 hook：不放行全文" if not sel else f"#{sel['index']} {sel['type']}"))
    text = Path(a.draft).read_text(encoding="utf-8")
    body = text.strip()
    if sel:
        head = re.sub(r"\s+", "", body)[:len(re.sub(r"\s+", "", sel["text"]))]
        items.append(g.item("opens_with_selected_hook", head == re.sub(r"\s+", "", sel["text"]), "稿件开头必须是选定的 hook 原文"))
    counts = count_chars(body)
    total = counts["total_chars"]
    in_range = TARGET_MIN <= total <= TARGET_MAX
    note = (a.length_note or "").strip()
    items.append(g.item("length_in_target_or_explained", in_range or bool(note),
                        f"字数 {total}，目标 {TARGET_MIN}-{TARGET_MAX}" + ("" if in_range else f"；区间外说明：{note or '缺 --length-note'}")))
    md_hits = [p for p in MD_PATTERNS if re.search(p, body, re.M)]
    items.append(g.item("no_markdown_or_bullets", not md_hits, f"命中：{md_hits}" if md_hits else "无"))
    if a.counted_file:
        same = Path(a.counted_file).read_text(encoding="utf-8").strip() == body
        items.append(g.item("count_matches_delivered_text", same, "字数统计用的文本必须和交付的是同一份"))
    else:
        items.append(g.item("count_matches_delivered_text", False, "缺 --counted-file：把统计字数用的那份文本传进来"))
    items.extend(outline_binding_items(body, ol, a.mapping))
    style_items = style_check.check(body)
    items.extend(style_items)
    items.extend(selfcheck_items(body, ol, a.mapping, a.style_selfcheck))
    items.extend(constraints_items(pre, body, a.constraints_result, items))
    items.extend(additions_items(body, a.source, a.additions, a.organize_only))
    items.append(g.item("ending_by_profile", True, "结尾以文风原档为准：可操作建议或利落判断，一句结束，不升华", human=True))
    rc = g.report(items, STAGE, {"total_chars": total})
    if rc == 0:
        need = [i["id"] for i in items if i["status"] == g.HUMAN and i["id"].startswith("◆")]
        rules = json.loads(style_check.rules_file().read_text(encoding="utf-8"))
        need += [f"◆{h['id']}" for h in rules["human_review"]]
        signed = {}
        if a.human_review:
            for x in json.loads(Path(a.human_review).read_text(encoding="utf-8")):
                if x.get("by") and x.get("message_id") and x.get("quote") and x.get("verdict") in ("通过", "不通过"):
                    signed[x.get("id")] = x
        need = list(dict.fromkeys(need))
        missing = [i for i in need if i not in signed]
        bad = [i for i, x in signed.items() if x["verdict"] != "通过"]
        if missing or bad:
            print(json.dumps({"待人审": missing, "人审不通过": bad,
                              "说明": "机器项已过，校验码暂不发放。把上面各项交给人，人逐项给「通过/不通过」，用 --human-review 记录 [{id, verdict, by, message_id, quote}]；agent 不得自填"}, ensure_ascii=False, indent=2))
            return 3
        code = g.check_code(STAGE, a.preflight, a.draft)
        print(json.dumps({"校验码": code, "说明": "交付消息末尾必须带这个码；稿件再改一个字就要重跑 deliver"}, ensure_ascii=False))
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preflight")
    p.add_argument("--skill-read-token", help="SKILL.md 最后一行「读完标记：」后面的字符串，证明读到了文件末尾")
    p.add_argument("--config", help="VA7_USER_CONFIG 指向的 config.json；缺省时按 va7config 查找顺序（VA7_USER_CONFIG → va7-config/default.json），再退到 va7-script/references/voice/va7.md")
    p.add_argument("--brief")
    p.add_argument("--gate-result", help="pre_draft_gate.py 的 JSON 输出")
    p.add_argument("--constraints", help="本次约束清单 JSON：[{id,text,status}]")
    p.add_argument("--want", choices=["outline", "full"], default="outline")
    p.add_argument("--out", default="script_preflight.json")
    p.set_defaults(fn=cmd_preflight)
    o = sub.add_parser("outline")
    o.add_argument("--preflight", default="script_preflight.json")
    o.add_argument("--source", help="输入材料文本文件：登记大纲时核对「素材原话」来源逐字存在")
    o.add_argument("--file", help="outline.json：{version, layers:[{id,label(≤8字),judgment,anchor,source,must_include?}]}")
    o.add_argument("--confirm", action="store_true", help="人确认当前登记的大纲（必须带下面三项）")
    o.add_argument("--by")
    o.add_argument("--message-id", dest="message_id")
    o.add_argument("--quote")
    o.set_defaults(fn=cmd_outline)
    pl = sub.add_parser("plan")
    pl.add_argument("--preflight", default="script_preflight.json")
    pl.add_argument("--confirm", action="store_true")
    pl.add_argument("--by")
    pl.add_argument("--message-id", dest="message_id")
    pl.add_argument("--quote")
    pl.set_defaults(fn=cmd_plan)
    h = sub.add_parser("hooks")
    h.add_argument("--preflight", default="script_preflight.json")
    h.add_argument("--candidates", help="[{text,type,basis,source,number_source?}] 正好 3 个")
    h.add_argument("--choose", type=int)
    h.set_defaults(fn=cmd_hooks)
    d = sub.add_parser("deliver")
    d.add_argument("--preflight", default="script_preflight.json")
    d.add_argument("--draft", required=True)
    d.add_argument("--counted-file")
    d.add_argument("--length-note")
    d.add_argument("--human-review", help="人逐项审过：[{id: ◆项id, verdict: 通过|不通过, by, message_id, quote}]；机器项全过后必须有，才发校验码")
    d.add_argument("--style-selfcheck", help="逐层引用成稿原句：[{layer_id, limitation_sentence, leads_to_sentence}]")
    d.add_argument("--constraints-result", help="预检登记的每条约束的结果：[{id, status: 已遵守|不适用, evidence}]")
    d.add_argument("--mapping", help="大纲每层对应成稿哪一段：[{layer_id, paragraph_first_sentence}]")
    d.add_argument("--source", help="输入材料（用户口述/原稿）文本文件；提供后核对成稿相对材料的新增")
    d.add_argument("--additions", help="新增清单 JSON：[{kind: 机制|判别标准|边界条件|结构调整, anchor: 成稿里的那句原文, why: 一句话}]")
    d.add_argument("--organize-only", action="store_true", help="明说本稿仅整理材料，没有新增论证")
    d.set_defaults(fn=cmd_deliver)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())

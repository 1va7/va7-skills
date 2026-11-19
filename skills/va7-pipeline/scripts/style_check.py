#!/usr/bin/env python3
"""按文风原档第八节检查成稿里「能机械核对」的写法约束。

规则与阈值全部来自 config 的 voice_profile.style_rules（缺省 va7-script/references/voice/style_rules.json）（由 va7.md 第八节转写），本脚本不写死数字。
不能机械核对的条目（论据类型、结尾、可念性、逐层局限与引出）不在这里判断，
列在 human_review 里，并要求交付时附 style_selfcheck（逐层引用成稿原句）。

用法：python3 style_check.py --draft draft.txt
退出码 0 = 机械项全过；2 = 有违反项。第一段默认是 hook，不参与段级规则。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "va7-pipeline" / "scripts"))
import gatelib as g  # noqa: E402

def rules_file() -> Path:
    from va7config import style_rules_path
    p = style_rules_path()
    if not p:
        raise SystemExit("缺文风机检规则 style_rules.json：在 config 的 voice_profile.style_rules 配置，或放到 va7-script/references/voice/")
    return p
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def n(t: str) -> int:
    return len(re.sub(r"[\s，、。？！；：“”\"'（）()\-—…,.?!;:]", "", t))


def split_sentences(t: str) -> list:
    return [s.strip() for s in re.split(r"[。？！?!；]", t) if s.strip()]


def check(draft: str, rules: dict | None = None) -> list:
    r = rules or json.loads(rules_file().read_text(encoding="utf-8"))
    paras = [p.strip() for p in re.split(r"\n\s*\n", draft.strip()) if p.strip()]
    body = paras[1:] if len(paras) > 1 else paras  # 第 1 段是 hook
    items = []

    sents = [s for p in body for s in split_sentences(p)]
    lens = [n(s) for s in sents] or [0]
    avg = sum(lens) / len(lens)
    sl = r["sentence_len"]
    long_ones = [s[:24] + "…" for s in sents if n(s) > sl["max_single"]]
    items.append(g.item("style_sentence_len_avg", sl["avg_min"] <= avg <= sl["avg_max"],
                        f"平均 {avg:.1f} 字，要求 {sl['avg_min']}-{sl['avg_max']}（{sl['rule']}）"))
    items.append(g.item("style_sentence_len_max", not long_ones,
                        f"超过 {sl['max_single']} 字的句子：{long_ones}；用句号收束，别把意群全串成一句" if long_ones else f"最长 {max(lens)} 字"))

    hits = [w for w in r["banned_words"]["words"] if w in draft]
    items.append(g.item("style_banned_words", not hits, f"命中：{hits}" if hits else "无"))
    bc = [c for c in r["banned_chars"]["chars"] if c in draft] + (["emoji"] if EMOJI.search(draft) else [])
    items.append(g.item("style_no_exclaim_emoji", not bc, f"命中：{bc}" if bc else "无"))
    pb = [c for c in r["particles"]["banned"] if c in draft]
    items.append(g.item("style_particles", not pb, f"出现不允许的语气词：{pb}（只允许 呢、吧、了）" if pb else "无"))
    fillers = sum(draft.count(w) for w in r["oral_filler"]["words"])
    items.append(g.item("style_oral_filler", fillers <= r["oral_filler"]["max_total"], f"「就是说/然后」共 {fillers} 次，上限 {r['oral_filler']['max_total']}"))

    cw = r["connector"]["words"]
    no_conn = [i + 2 for i, p in enumerate(body) if not any(w in p for w in cw)]
    items.append(g.item("style_connector_per_paragraph", not no_conn,
                        f"第 {no_conn} 段没有任何因果/转折连接词" if no_conn else "每段都有"))

    tw = r["layer_transition"]["words"]
    bad_tr = []
    for i, p in enumerate(body[1:], start=3):  # 第二个正文段起（整稿第 3 段起）
        first = split_sentences(p)[0] if split_sentences(p) else ""
        if not any(w in first for w in tw):
            bad_tr.append(f"第{i}段首句「{first[:18]}…」")
    items.append(g.item("style_layer_transition", not bad_tr,
                        "这些段首句没有承接上一层局限的词：" + "；".join(bad_tr) if bad_tr else "各层段首都有承接"))

    ps = r["paragraph_sentences"]
    bad_ps = []
    for i, p in enumerate(body, start=2):
        k = len(split_sentences(p))
        if (k < ps["min"] and n(p) > ps["short_para_chars"]) or k > ps["max"]:
            bad_ps.append(f"第{i}段 {k} 句")
    items.append(g.item("style_paragraph_sentences", not bad_ps, f"{bad_ps}（要求 {ps['min']}-{ps['max']} 句，金句除外）" if bad_ps else "各段句数合规"))

    ev = r["evidence"]
    q = [w for w in ev["banned_quote_patterns"] if w in draft]
    items.append(g.item("style_no_quotes", not q, f"疑似引用名言/名人：{q}" if q else "无"))
    sim = [w for w in ev["simile_markers"] if w in draft]
    items.append(g.item("style_no_simile", not sim, f"出现类比标记 {sim}：档案禁空洞类比，改成机制说明，或在 selfcheck.waivers 写明为什么不是空洞类比" if sim else "无"))
    sy = r["sayable"]
    wp = [w for w in sy["written_phrases"] if w in draft]
    items.append(g.item("style_no_written_phrases", not wp, f"书面腔：{wp}" if wp else "无"))
    pr = [c for c in sy["banned_chars"] if c in draft]
    items.append(g.item("style_no_parentheses", not pr, "档案四：少用括号，要补充就另起一句说" if pr else "无"))
    clauses = [c for p in body for c in re.split(r"[，、；：。？！?!]", p) if c.strip()]
    over = [c.strip()[:14] + "…" for c in clauses if n(c) > sy["max_clause_chars"]]
    items.append(g.item("style_clause_breath", not over, f"这些意群超过 {sy['max_clause_chars']} 字，一口气念不完：{over}" if over else f"最长意群 {max(n(c) for c in clauses)} 字"))
    en = r["ending"]
    last_sents = split_sentences(body[-1]) if body else []
    last = last_sents[-1] if last_sents else ""
    sub = [w for w in en["sublimation_words"] if w in last]
    items.append(g.item("style_ending_no_sublimation", not sub, f"末句含升华词 {sub}" if sub else f"末句：{last[:20]}"))
    for h in r["human_review"]:
        items.append(g.item(f"◆{h['id']}", True, h["rule"], human=True))
    return items


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--draft", required=True)
    a = ap.parse_args()
    return g.report(check(Path(a.draft).read_text(encoding="utf-8")), "style")


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""给定底图上量出的人物坐标和文字块，枚举满足 3:4 构图标准的 crop，输出最稳的一个（可行区间中心）。
用法：suggest_crop.py --subject subject.json --text-blocks blocks.json --source-size 1672x941
没有可行 crop 就明说，别硬凑：告诉人换帧。判定规则全部来自 qa_cover_set.check_subject，不另写一套。"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_cover_set as q


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True, help="JSON：head_top_y, hair_left_x, glasses_left_x, mouth_left_x, ear_left_x, chin_y（源图像素）")
    ap.add_argument("--text-blocks", required=True, help="JSON：[大标题块, 小标题块]，与 layout 里 text_blocks 同格式")
    ap.add_argument("--source-size", required=True, help="如 1672x941")
    a = ap.parse_args()
    subj = json.loads(Path(a.subject).read_text(encoding="utf-8"))
    blocks = json.loads(Path(a.text_blocks).read_text(encoding="utf-8"))
    sw, sh = map(int, a.source_size.lower().split("x"))
    ok = []
    for h in range(sh, int(sh * 0.7), -2):
        w = round(h * 0.75)
        if w > sw:
            continue
        for top in range(max(0, sh - h - 12), sh - h + 1, 2):
            lo = max(0, int(subj["glasses_left_x"] - 0.5 * w))  # 眼镜左缘 0.35-0.5 决定 left 的窄区间
            hi = min(sw - w, int(subj["glasses_left_x"] - 0.35 * w) + 1)
            for left in range(lo, hi + 1):
                crop = [left, top, left + w, top + h]
                r = q.check_subject("3x4", {"subject": subj, "text_blocks": blocks}, crop, (1620, 2160))[0]
                if r["ok"]:
                    ok.append((crop, r["measured"]))
    if not ok:
        print(json.dumps({"feasible": False, "说明": "这张底图放不下 3:4 的全部条件，先告诉人换人物更小或更高清的帧"}, ensure_ascii=False))
        return 2
    crop, m = ok[len(ok) // 2]
    print(json.dumps({"feasible": True, "count": len(ok), "crop": crop, "measured": m,
                      "说明": "取可行集合的中间值；写进 layout.specs.3x4.crop，再 render"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

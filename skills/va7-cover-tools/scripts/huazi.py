#!/usr/bin/env python3
"""开头花字：预检（check）与透明底 PNG 生成（render）。

版式来自 VA7 的花字样本（横屏 1920x1080）：
- 左上：白字两行（情绪/问题句）
- 右下：黄字两行（关键词），右对齐
- 每行 ≤7 字；字号约占画面高度 13%，行距约 15.7%

check  : 校验候选 JSON，通过才写 huazi_preflight.json（status=passed）；不通过退出码 2。
render : 要求 huazi_preflight.json 已 passed；生成透明底 PNG，可直接拖进剪映。
"""
import argparse, json, re, sys
from pathlib import Path

MAX_LINE = 7
LINES_PER_GROUP = 2
MIN_CANDIDATES = 2
WHITE = (255, 255, 255, 255)
YELLOW = (250, 220, 75, 255)  # 取自样本黄字
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cover_assets  # noqa: E402

FONT_DIR = cover_assets.FONT.parent  # run cover_assets.py ensure first
DEFAULT_FONT = "NotoSansSC-Bold.otf"


def fail(msg):
    print(json.dumps({"passed": False, "error": msg}, ensure_ascii=False, indent=2))
    sys.exit(2)


def check(args):
    data = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    cover = [s.strip() for s in data.get("cover_title_lines", []) if s.strip()]
    first = data.get("first_sentence", "").strip()
    cands = data.get("candidates", [])
    problems, warnings = [], []
    if not cover:
        problems.append("缺 cover_title_lines（已确认的封面主副标题）")
    if not first:
        problems.append("缺 first_sentence（口播稿第一句）")
    if len(cands) < MIN_CANDIDATES:
        problems.append(f"候选数 {len(cands)} < {MIN_CANDIDATES}")
    for i, c in enumerate(cands, 1):
        if not str(c.get("reason", "")).strip():
            problems.append(f"候选{i} 缺 reason")
        for group in ("tl", "br"):
            lines = c.get(group)
            if not isinstance(lines, list) or len(lines) != LINES_PER_GROUP:
                problems.append(f"候选{i}.{group} 必须正好 {LINES_PER_GROUP} 行")
                continue
            for text in lines:
                text = str(text)
                if not text.strip():
                    problems.append(f"候选{i}.{group} 有空行")
                if len(text) > MAX_LINE:
                    problems.append(f"候选{i}.{group} 行长 {len(text)} > {MAX_LINE}：{text}")
                if text in cover:
                    problems.append(f"候选{i}.{group} 与封面标题某一行完全相同：{text}")
                if re.search(r"\d", text) and not str(c.get("number_source", "")).strip():
                    problems.append(f"候选{i}.{group} 含数字但没有 number_source：{text}")
        joined = "".join(str(x) for g in ("tl", "br") for x in (c.get(g) or []))
        grams = {joined[j:j + 2] for j in range(len(joined) - 1)}
        if first and not any(g in first for g in grams):
            warnings.append(f"候选{i} 与开头第一句没有共同字词，请人工确认含义是否对应")
    result = {"passed": not problems, "problems": problems, "warnings": warnings, "candidate_count": len(cands)}
    if not problems:
        Path(args.out).write_text(json.dumps({**result, "status": "passed", "version": 2, "candidates": cands}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if not problems else 2)


def render(args):
    from PIL import Image, ImageDraw, ImageFont
    if not Path(args.preflight).exists():
        fail("没有预检结果文件，先跑 check")
    pre = json.loads(Path(args.preflight).read_text(encoding="utf-8"))
    if pre.get("status") != "passed":
        fail("预检未通过，不生成 PNG")
    if pre.get("version") != 2:
        fail("预检结果是旧版格式，重新跑 check")
    cand = pre["candidates"][args.choose - 1]
    font_path = args.font or str(FONT_DIR / args.weight)
    if not Path(font_path).exists():
        fail(f"找不到字体：{font_path}")
    W, H = (int(v) for v in args.size.split("x"))
    size, pitch = round(H * 0.13), round(H * 0.157)
    font = ImageFont.truetype(font_path, size)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def draw(text, x, y, fill):
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).text((x + 3, y + 4), text, font=font, fill=(0, 0, 0, 90))
        img.alpha_composite(shadow)
        ImageDraw.Draw(img).text((x, y), text, font=font, fill=fill)

    x0, y0 = round(W * 0.039), round(H * 0.064)
    for k, text in enumerate(cand["tl"]):
        draw(text, x0, y0 + k * pitch, WHITE)
    right, last_bottom = round(W * 0.964), round(H * 0.954)
    first_top = last_bottom - size - (LINES_PER_GROUP - 1) * pitch
    for k, text in enumerate(cand["br"]):
        draw(text, right - font.getlength(text), first_top + k * pitch, YELLOW)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    img.save(args.out)
    print(json.dumps({"passed": True, "png": args.out, "size": args.size, "font": font_path}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(required=True)
    c = sub.add_parser("check")
    c.add_argument("--candidates", required=True)
    c.add_argument("--out", default="huazi_preflight.json")
    c.set_defaults(fn=check)
    r = sub.add_parser("render")
    r.add_argument("--preflight", default="huazi_preflight.json")
    r.add_argument("--choose", type=int, required=True, help="第几套候选，从 1 开始")
    r.add_argument("--size", default="1920x1080")
    r.add_argument("--weight", default=DEFAULT_FONT, help="fonts/ 下的字体文件名")
    r.add_argument("--font")
    r.add_argument("--out", required=True)
    r.set_defaults(fn=render)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

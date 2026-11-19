#!/usr/bin/env python3
"""Check VA7 cover files, explicit crops, references, and visual review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


ALL_RATIOS = {
    "16x9": (3840, 2160),
    "4x3": (2880, 2160),
    "3x4": (1620, 2160),
}
EXPECTED = {"3x4": ALL_RATIOS["3x4"]}  # 封面默认只出竖版 3:4；要横版用 --ratios


def find_file(folder: Path, prefix: str, spec: str) -> Path | None:
    direct = folder / f"{prefix}_{spec}.jpg"
    if direct.exists():
        return direct
    matches = sorted(folder.glob(f"*{spec}*.jpg")) + sorted(folder.glob(f"*{spec}*.png"))
    return matches[0] if matches else None


def find_preview(folder: Path, prefix: str) -> Path | None:
    direct = folder / f"{prefix}_preview.jpg"
    if direct.exists():
        return direct
    matches = sorted(folder.glob(f"{prefix}*preview*.jpg")) + sorted(folder.glob(f"{prefix}*preview*.png"))
    return matches[0] if matches else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratios", default="3x4", help="要检查的比例，逗号分隔；封面固定竖版 3:4（王诗梦 2026-11-16 定），要出横版再写 3x4,4x3")
    parser.add_argument("--cover-dir", required=True, type=Path)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--out", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--strict", dest="strict", action="store_true", default=True)
    mode.add_argument(
        "--dimensions-only",
        dest="strict",
        action="store_false",
        help="diagnostic compatibility mode; never sufficient for final delivery",
    )
    parser.add_argument("--layout", type=Path)
    parser.add_argument("--source-frame", type=Path)
    parser.add_argument("--reference", action="append", default=[], type=Path)
    parser.add_argument("--qa-board", type=Path)
    parser.add_argument("--visual-review", type=Path)
    return parser.parse_args()


SUBJECT_KEYS = ("head_top_y", "hair_left_x", "glasses_left_x", "mouth_left_x", "ear_left_x", "chin_y")


def check_subject(spec: str, spec_data: dict, crop: list, expected: tuple) -> list[dict]:
    """用底图上量出的人物坐标（源图像素）核对 crop 后的人物位置，不靠目视。
    3:4 标准（0713 基准量化，王诗梦 2026-11-16 定）：头顶比例 0-0.08；眼镜左缘在 0.35-0.5；
    右边缘要切到耳朵（耳左缘在画内）；下巴在画内；文字右缘不压头发和嘴。"""
    if spec != "3x4":
        return []
    subj = spec_data.get("subject")
    if not isinstance(subj, dict) or any(not isinstance(subj.get(k), (int, float)) for k in SUBJECT_KEYS):
        return [{"spec": f"subject_{spec}", "ok": False,
                 "reason": f"layout 里缺 subject 量测（源图像素）：{list(SUBJECT_KEYS)}；先看底图量出来再写 crop，不许凭感觉"}]
    left, top, right, bottom = crop
    w, h = right - left, bottom - top
    scale = expected[0] / w
    head_top = (subj["head_top_y"] - top) / h
    glasses = (subj["glasses_left_x"] - left) / w
    ear_in = subj["ear_left_x"] <= right
    chin_in = subj["chin_y"] <= bottom
    problems = []
    if not 0 <= head_top <= 0.08:
        problems.append(f"头顶比例 {head_top:.3f}，要求 0-0.08")
    if not 0.35 <= glasses <= 0.5:
        problems.append(f"眼镜左缘在 {glasses:.3f}，要求 0.35-0.5")
    if not ear_in:
        problems.append("耳朵整个被裁掉，右边缘要切在耳朵上")
    if not chin_in:
        problems.append("下巴被裁掉")
    text_blocks = spec_data.get("text_blocks") or []
    for name, block in zip(("title", "subtitle"), text_blocks[:2]):
        lines = block.get("lines") or []
        size = int(block.get("font_size") or 0)
        x, y = (block.get("xy") or [0, 0])
        right_edge = x + max((len(ln) for ln in lines), default=0) * size
        bottom_edge = y + len(lines) * size
        hair_x = (subj["hair_left_x"] - left) * scale
        mouth_x = (subj["mouth_left_x"] - left) * scale
        head_y = (subj["head_top_y"] - top) * scale
        if name == "title" and bottom_edge > head_y and right_edge > hair_x:
            problems.append(f"大标题右缘 {right_edge:.0f} 压到头发（头发左缘 {hair_x:.0f}）")
        if name == "subtitle" and right_edge > mouth_x:
            problems.append(f"小标题右缘 {right_edge:.0f} 压到嘴（嘴左缘 {mouth_x:.0f}）")
    return [{"spec": f"subject_{spec}", "ok": not problems, "problems": problems,
             "measured": {"head_top_fraction": round(head_top, 3), "glasses_left_fraction": round(glasses, 3),
                          "ear_in_frame": ear_in, "chin_in_frame": chin_in}}]


def check_explicit_crops(layout_path: Path | None, source_path: Path | None) -> list[dict]:
    if not layout_path or not layout_path.expanduser().exists():
        return [{"spec": "layout", "ok": False, "reason": "missing_layout"}]
    if not source_path or not source_path.expanduser().exists():
        return [{"spec": "source_frame", "ok": False, "reason": "missing_source_frame"}]

    layout = json.loads(layout_path.expanduser().read_text(encoding="utf-8"))
    with Image.open(source_path.expanduser()) as source:
        source_size = source.size

    checks = []
    for spec, expected in EXPECTED.items():
        spec_data = (layout.get("specs") or {}).get(spec) or {}
        crop = spec_data.get("crop")
        check = {"spec": f"crop_{spec}", "crop": crop, "source_size": source_size}
        if not isinstance(crop, list) or len(crop) != 4:
            check.update(ok=False, reason="crop_must_be_explicit_non_null_box")
            checks.append(check)
            continue
        left, top, right, bottom = crop
        valid_bounds = 0 <= left < right <= source_size[0] and 0 <= top < bottom <= source_size[1]
        crop_ratio = (right - left) / (bottom - top)
        expected_ratio = expected[0] / expected[1]
        ratio_ok = abs(crop_ratio - expected_ratio) <= 0.005
        check.update(
            ok=valid_bounds and ratio_ok,
            valid_bounds=valid_bounds,
            ratio_ok=ratio_ok,
            crop_ratio=round(crop_ratio, 6),
            expected_ratio=round(expected_ratio, 6),
        )
        checks.append(check)

        checks.extend(check_subject(spec, spec_data, crop, expected))

        text_blocks = spec_data.get("text_blocks") or []
        title = text_blocks[0] if text_blocks else {}
        title_lines = title.get("lines") or []
        title_font_size = int(title.get("font_size") or 0)
        title_height_ratio = title_font_size * len(title_lines) / expected[1]
        minimum_ratio = 0.18 if spec == "3x4" else 0.16
        checks.append(
            {
                "spec": f"title_scale_{spec}",
                "ok": minimum_ratio <= title_height_ratio <= 0.34,
                "font_size": title_font_size,
                "line_count": len(title_lines),
                "estimated_height_ratio": round(title_height_ratio, 4),
                "allowed_range": [minimum_ratio, 0.34],
            }
        )

        if len(text_blocks) >= 2:
            sub_lines = text_blocks[1].get("lines") or []
            too_long = [ln for ln in sub_lines if len(ln) > 5]
            too_short = [ln for ln in sub_lines if len(ln) < 2]
            checks.append({"spec": f"subtitle_lines_{spec}", "ok": 3 <= len(sub_lines) <= 4 and not too_long and not too_short,
                           "line_count": len(sub_lines), "over_5_chars": too_long, "under_2_chars": too_short,
                           "rule": "白字小标题：3-4 条（原 skill：通常 3 条，第 4 条须是独立必要的核心点）、每行 2-5 字不换行（王诗梦 2026-11-16 把原 2-8 字收紧到 5 字）"})
            title_xy = title.get("xy") or [0, 0]
            subtitle = text_blocks[1]
            subtitle_xy = subtitle.get("xy") or [0, 0]
            title_left = title_xy[0] / expected[0]
            title_top = title_xy[1] / expected[1]
            subtitle_left = subtitle_xy[0] / expected[0]
            subtitle_top = subtitle_xy[1] / expected[1]
            title_font_fraction = title_font_size / expected[1]
            subtitle_font_fraction = int(subtitle.get("font_size") or 0) / expected[1]
            title_left_minimum = 0.05 if spec == "3x4" else 0.025
            subtitle_left_minimum = 0.06 if spec == "3x4" else 0.03
            checks.append(
                {
                    "spec": f"text_geometry_{spec}",
                    "ok": (
                        title_left >= title_left_minimum
                        and 0.04 <= title_top <= 0.10
                        and subtitle_left >= subtitle_left_minimum
                        and subtitle_left >= title_left
                        and 0.58 <= subtitle_top <= 0.72
                        and 0.085 <= title_font_fraction <= 0.13
                        and 0.055 <= subtitle_font_fraction <= 0.08
                    ),
                    "title_left_fraction": round(title_left, 4),
                    "title_top_fraction": round(title_top, 4),
                    "subtitle_left_fraction": round(subtitle_left, 4),
                    "subtitle_top_fraction": round(subtitle_top, 4),
                    "title_font_fraction": round(title_font_fraction, 4),
                    "subtitle_font_fraction": round(subtitle_font_fraction, 4),
                    "requirements": {
                        "title_left_minimum": title_left_minimum,
                        "title_top_range": [0.04, 0.10],
                        "subtitle_left_minimum": subtitle_left_minimum,
                        "subtitle_left_gte_title_left": True,
                        "subtitle_top_range": [0.58, 0.72],
                        "title_font_range": [0.085, 0.13],
                        "subtitle_font_range": [0.055, 0.08]
                    },
                }
            )
    return checks


VISUAL_FIELDS = (
    "subject_position",
    "subject_scale",
    "head_top_margin",
    "text_hierarchy",
    "text_subject_separation",
    "reference_match",
)


def check_visual_review(path: Path | None) -> list[dict]:
    if not path or not path.expanduser().exists():
        return [{"spec": "visual_review", "ok": False, "reason": "missing_visual_review_json"}]
    data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    checks = []
    refs = data.get("references") or []
    checks.append({"spec": "visual_review_references", "ok": len(refs) >= 2, "references": refs})
    for spec in EXPECTED:
        review = (data.get("specs") or {}).get(spec) or {}
        failed = [field for field in VISUAL_FIELDS if review.get(field) is not True]
        notes = str(review.get("notes") or "").strip()
        head_top_fraction = review.get("head_top_fraction_estimate")
        head_top_maximum = 0.15 if spec == "4x3" else 0.08
        head_top_ok = isinstance(head_top_fraction, (int, float)) and 0 <= head_top_fraction <= head_top_maximum
        checks.append(
            {
                "spec": f"visual_{spec}",
                "ok": not failed and head_top_ok and len(notes) >= 12,
                "failed_fields": failed,
                "head_top_fraction_estimate": head_top_fraction,
                "head_top_fraction_ok": head_top_ok,
                "head_top_fraction_allowed": [0, head_top_maximum],
                "notes": notes,
            }
        )
    return checks


def main() -> int:
    args = parse_args()
    wanted = [r.strip() for r in args.ratios.split(",") if r.strip()]
    EXPECTED.clear()
    EXPECTED.update({k: v for k, v in ALL_RATIOS.items() if k in wanted})
    folder = args.cover_dir.expanduser().resolve()
    checks = []
    for spec, expected in EXPECTED.items():
        path = find_file(folder, args.prefix, spec) if args.prefix else find_file(folder, "*", spec)
        if not path:
            checks.append({"spec": spec, "ok": False, "reason": "missing_file", "expected_size": expected})
            continue
        with Image.open(path) as im:
            size = im.size
        checks.append(
            {
                "spec": spec,
                "path": str(path),
                "ok": size == expected,
                "size": size,
                "expected_size": expected,
            }
        )
    preview = find_preview(folder, args.prefix)
    checks.append({"spec": "preview", "ok": bool(preview), "path": str(preview) if preview else None})

    if args.strict:
        checks.extend(check_explicit_crops(args.layout, args.source_frame))
        references = [path.expanduser().resolve() for path in args.reference]
        checks.append(
            {
                "spec": "historical_references",
                "ok": len(references) >= 2 and all(path.exists() for path in references),
                "paths": [str(path) for path in references],
            }
        )
        board = args.qa_board.expanduser().resolve() if args.qa_board else None
        checks.append(
            {
                "spec": "reference_qa_board",
                "ok": bool(board and board.exists()),
                "path": str(board) if board else None,
            }
        )
        checks.extend(check_visual_review(args.visual_review))
    result = {
        "cover_dir": str(folder),
        "checks": checks,
        "passed": all(check["ok"] for check in checks),
        "strict": args.strict,
        "model_gate": (
            "Strict QA requires explicit per-ratio crops, at least two historical references, "
            "a combined reference board, and a complete per-ratio visual review."
        ),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

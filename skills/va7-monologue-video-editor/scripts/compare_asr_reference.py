#!/usr/bin/env python3
"""Compare ASR output against a selected reference script for correction review."""

from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_TERMS = [
    "AI",
    "Agent",
    "Token",
    "Prompt Engineering",
    "Vibe Coding",
    "SOP",
    "evaluation",
    "trace",
    "loop",
    "one-off",
    "One API",
    "New API",
    "跨境电商",
    "端到端",
    "日均",
    "AI 原生",
    "自建网关",
]


def normalize(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text.lower(), flags=re.UNICODE)


def load_asr(path: Path) -> tuple[str, list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Unsupported ASR JSON shape: {path}")
    segments = data.get("segments") or []
    text = data.get("text") or "".join(str(seg.get("text", "")) for seg in segments if isinstance(seg, dict))
    return str(text), [seg for seg in segments if isinstance(seg, dict)]


def load_reference(path: Path) -> tuple[str, dict[str, Any] | None]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if isinstance(data.get("final_script"), str):
            return data["final_script"], data
        candidates = data.get("candidates")
        if isinstance(candidates, list) and candidates:
            first = candidates[0]
            if isinstance(first, dict) and isinstance(first.get("final_script"), str):
                return first["final_script"], first
    raise SystemExit("Reference JSON must include final_script or candidates[0].final_script. Rerun find_reference_script.py --include-script.")


def term_presence(text: str, terms: list[str]) -> dict[str, bool]:
    normalized_text = normalize(text)
    return {term: normalize(term) in normalized_text for term in terms}


def digit_tokens(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?\s*(?:亿|万|千|百|%|块|元|美金|刀|token|Token)?", text)


def has_digit(text: str) -> bool:
    return bool(re.search(r"\d", text))


def has_ascii_term(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]{2,}", text))


def nearest_reference(segment: str, ref_windows: list[str]) -> tuple[float, str]:
    segment_norm = normalize(segment)
    best = (0.0, "")
    for window in ref_windows:
        ratio = difflib.SequenceMatcher(None, segment_norm, normalize(window)).ratio()
        if ratio > best[0]:
            best = (ratio, window)
    return best


def build_windows(reference: str, size: int = 80, step: int = 28) -> list[str]:
    compact = re.sub(r"\s+", "", reference)
    if len(compact) <= size:
        return [compact]
    return [compact[i : i + size] for i in range(0, max(1, len(compact) - size + 1), step)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asr-json", required=True, type=Path)
    parser.add_argument("--reference-json", required=True, type=Path)
    parser.add_argument("--term", action="append", default=[], help="Additional protected term.")
    parser.add_argument("--low-ratio", type=float, default=0.18)
    parser.add_argument("--max-segment-reviews", type=int, default=40)
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    asr_text, segments = load_asr(args.asr_json)
    reference, ref_record = load_reference(args.reference_json)
    terms = DEFAULT_TERMS + [term for term in args.term if term not in DEFAULT_TERMS]
    asr_terms = term_presence(asr_text, terms)
    ref_terms = term_presence(reference, terms)
    term_mismatches = [
        {"term": term, "in_reference": ref_terms[term], "in_asr": asr_terms[term]}
        for term in terms
        if ref_terms[term] != asr_terms[term]
    ]

    asr_digits = digit_tokens(asr_text)
    ref_digits = digit_tokens(reference)
    ref_windows = build_windows(reference)
    segment_reviews = []
    for seg in segments:
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        ratio, ref_window = nearest_reference(text, ref_windows)
        normalized_segment = normalize(text)
        term_hit = any(normalize(term) in normalized_segment for term in terms)
        abnormal_low_similarity = ratio < args.low_ratio and len(normalize(text)) >= 14
        needs_review = term_hit or has_digit(text) or (has_ascii_term(text) and ratio < 0.5) or abnormal_low_similarity
        if needs_review:
            segment_reviews.append(
                {
                    "id": seg.get("id"),
                    "start": seg.get("start"),
                    "end": seg.get("end"),
                    "asr_text": text,
                    "nearest_reference_ratio": round(ratio, 3),
                    "nearest_reference_window": ref_window[:140],
                }
            )

    result = {
        "asr_json": str(args.asr_json),
        "reference_record": {
            "record_id": ref_record.get("record_id") if isinstance(ref_record, dict) else None,
            "title": ref_record.get("title") if isinstance(ref_record, dict) else None,
        },
        "asr_chars": len(asr_text),
        "reference_chars": len(reference),
        "overall_sequence_ratio": round(
            difflib.SequenceMatcher(None, normalize(asr_text[:2500]), normalize(reference[:2500])).ratio(),
            3,
        ),
        "term_mismatches": term_mismatches,
        "asr_numbers": asr_digits,
        "reference_numbers": ref_digits,
        "number_sets_match": set(asr_digits) == set(ref_digits),
        "segment_reviews": segment_reviews[: max(0, args.max_segment_reviews)],
        "model_gate": "Use this report to write corrections.json; final subtitles must still match retained audio, not the reference script blindly.",
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

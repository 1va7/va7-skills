#!/usr/bin/env python3
"""Deterministically count deliverable口播稿 characters.

The count is intended for va7-script deliverables. It excludes whitespace,
punctuation, and symbols, then counts all remaining Unicode characters. This
makes Chinese characters, Latin letters, and digits deterministic without
asking the model to estimate length.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path


def is_counted_char(char: str) -> bool:
    if char.isspace():
        return False
    category = unicodedata.category(char)
    return not (category.startswith("P") or category.startswith("S"))


def count_chars(text: str) -> dict[str, int]:
    counted = [char for char in text if is_counted_char(char)]
    cjk_chars = 0
    latin_letters = 0
    digits = 0
    other_chars = 0

    for char in counted:
        codepoint = ord(char)
        if (
            0x3400 <= codepoint <= 0x4DBF
            or 0x4E00 <= codepoint <= 0x9FFF
            or 0xF900 <= codepoint <= 0xFAFF
            or 0x20000 <= codepoint <= 0x2A6DF
            or 0x2A700 <= codepoint <= 0x2B73F
            or 0x2B740 <= codepoint <= 0x2B81F
            or 0x2B820 <= codepoint <= 0x2CEAF
            or 0x2CEB0 <= codepoint <= 0x2EBEF
            or 0x30000 <= codepoint <= 0x3134F
        ):
            cjk_chars += 1
        elif char.isdigit():
            digits += 1
        elif "A" <= char <= "Z" or "a" <= char <= "z":
            latin_letters += 1
        else:
            other_chars += 1

    return {
        "total_chars": len(counted),
        "cjk_chars": cjk_chars,
        "latin_letters": latin_letters,
        "digits": digits,
        "other_chars": other_chars,
    }


def read_input(path: str | None) -> str:
    if path:
        return Path(path).expanduser().read_text(encoding="utf-8")
    return sys.stdin.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", help="Plain text file containing only the口播正文")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of the human-readable summary")
    args = parser.parse_args()

    text = read_input(args.file)
    result = count_chars(text)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"total_chars={result['total_chars']}")
        print(
            "breakdown="
            f"cjk:{result['cjk_chars']},"
            f"latin:{result['latin_letters']},"
            f"digits:{result['digits']},"
            f"other:{result['other_chars']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

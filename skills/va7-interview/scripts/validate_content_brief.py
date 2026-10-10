#!/usr/bin/env python3
"""Validate a VA7 content interview brief before drafting."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from writing_intent import validate_writing_state


REQUIRED_STRING_FIELDS = [
    "idea",
    "library_status",
    "user_position",
    "audience",
    "viewer_payoff",
    "key_tension",
    "mechanism",
]

VALID_LIBRARY_STATUS = {"existing_ready", "existing_needs_interview", "new_topic"}


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_data(data: object, *, allow_unconfirmed: bool = False) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return {"ok": False, "errors": ["content brief must be a JSON object"], "warnings": []}

    for field in REQUIRED_STRING_FIELDS:
        if not nonempty(data.get(field)):
            errors.append(f"missing non-empty field: {field}")

    if data.get("library_status") not in VALID_LIBRARY_STATUS:
        errors.append(f"library_status must be one of {sorted(VALID_LIBRARY_STATUS)}")

    direction = data.get("selected_direction")
    if not isinstance(direction, dict):
        errors.append("selected_direction must be an object")
    else:
        for field in ["name", "thesis", "why_va7_specific"]:
            if not nonempty(direction.get(field)):
                errors.append(f"selected_direction.{field} is required")

    evidence = data.get("personal_evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("personal_evidence must contain at least one item")
    else:
        concrete = 0
        for idx, item in enumerate(evidence):
            if not isinstance(item, dict):
                errors.append(f"personal_evidence[{idx}] must be an object")
                continue
            if nonempty(item.get("detail")):
                concrete += 1
        if concrete == 0:
            errors.append("personal_evidence must include at least one non-empty detail")

    for list_field in ["non_goals", "claims_to_avoid"]:
        value = data.get(list_field)
        if not isinstance(value, list) or not value:
            errors.append(f"{list_field} must contain at least one item")

    if data.get("confirmed_by_user") is not True and not allow_unconfirmed:
        errors.append("confirmed_by_user must be true for a confirmed content direction")

    state_errors, state_warnings = validate_writing_state(data.get("writing_state"))
    errors.extend(state_errors)
    warnings.extend(state_warnings)

    if data.get("open_questions"):
        warnings.append("open_questions is not empty; downstream writing must preserve these caveats")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "scope": "content_direction_only",
    }


def load_brief(path: str) -> tuple[dict[str, object], dict[str, object]]:
    resolved = Path(path).expanduser()
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, {"ok": False, "errors": [f"failed to read JSON: {exc}"], "warnings": [], "brief": str(resolved)}
    return (data if isinstance(data, dict) else {}), validate_data(data) | {"brief": str(resolved)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", required=True, help="Path to content_brief.json")
    parser.add_argument("--allow-unconfirmed", action="store_true")
    args = parser.parse_args()
    data, result = load_brief(args.brief)
    if args.allow_unconfirmed and data:
        result = validate_data(data, allow_unconfirmed=True) | {"brief": str(Path(args.brief).expanduser())}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

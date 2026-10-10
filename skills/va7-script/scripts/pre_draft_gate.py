#!/usr/bin/env python3
"""Identify the requested writing artifact before allowing a full draft."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "va7-interview" / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))
from validate_content_brief import load_brief  # noqa: E402
from writing_intent import decide_writing_request  # noqa: E402


def read_text(path: str | None, inline: str | None) -> str:
    chunks = [inline] if inline else []
    if path:
        chunks.append(Path(path).expanduser().read_text(encoding="utf-8"))
    return "\n".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="Current user request, not a pasted conversation history")
    parser.add_argument("--input-file", help="File containing the current user request")
    parser.add_argument("--brief", help="Optional content brief and version-specific writing_state")
    parser.add_argument("--feishu-record", help="Context locator only; a record id is not writing authorization")
    parser.add_argument("--user-confirmed-skip", action="store_true", help="User waived interview, not artifact or scope constraints")
    args = parser.parse_args()

    try:
        text = read_text(args.input_file, args.input).strip()
    except OSError as exc:
        print(json.dumps({"ok": False, "decision": "needs_context", "may_write_full_draft": False, "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    brief, report = load_brief(args.brief) if args.brief else ({}, {})
    result = decide_writing_request(
        text,
        brief_ready=report.get("ok") is True,
        writing_state=brief.get("writing_state"),
        has_brief=bool(args.brief),
        user_confirmed_skip=args.user_confirmed_skip,
    )
    if args.brief:
        result.update(brief=str(Path(args.brief).expanduser()), validator_report=report)
    if args.feishu_record:
        result["feishu_record"] = args.feishu_record
        result["warnings"].append("Feishu record id locates context only; inspect its actual content and confirmation evidence")
    if result["decision"] == "route_to_interview":
        result["required_next_skill"] = "va7-interview"
        result["required_next_steps"] = ["recover existing topic context", "ask only for missing stance, evidence, or direction"]
    elif result["decision"] == "needs_context":
        result["required_next_steps"] = ["recover current request, artifact, and prior confirmation from conversation", "ask one targeted question only if still necessary"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

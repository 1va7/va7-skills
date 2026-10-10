"""Conservative writing-stage hints, not a natural-language authorization engine."""

from __future__ import annotations

import re
from typing import Any


OUTLINE = r"(?:bullet(?:\s*points?)?|大纲|提纲|outline)"
FULL = r"(?:完整(?:的)?(?:口播)?稿(?:子)?|完整(?:的)?正文|全文|整稿|正文|口播稿|full\s+draft)"
NEGATION = r"(?:不要|不用|不需要|不能|不想|禁止|先别|别|暂不|无需|不|do\s+not|don't)"
CONTINUE = r"(?:^|[，,。\s])(?:继续|接着|接下来|往下做|做到哪|现在.*阶段|continue)(?:[吧啊呀\s。！!]*$|做|写)"
RAW_IDEA = r"我有个?灵感|这个选题|选题是|主题是|帮我想.*方向|能不能写成|围绕.{0,60}写|写.{0,40}(?:口播稿|小红书)"
STAGES = {"outline", "full_draft", "revise"}
CLAUSE_BOUNDARY = r"[，,。；;！？!?\n]"
AMBIGUOUS = (
    r"不是不|并非不|不能不|不只是|不是只|为什么.{0,16}(?:写|出)|为何.{0,16}(?:写|出)"
    r"|是否|要不要|(?:能不能|可以吗).{0,12}(?:全文|完整稿|大纲)|unless|whether"
    r"|(?:如果|除非|等|待).{0,24}(?:确认|通过)"
)


def instruction_text(text: str) -> str:
    """Exclude visibly quoted examples/history from positive instruction matches."""
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"(?m)^\s*>.*$", " ", text)
    for pattern in [r'"[^"\n]*"', r"“[^”]*”", r"「[^」]*」", r"『[^』]*』", r"‘[^’]*’"]:
        text = re.sub(pattern, " ", text)
    return text.strip()


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def _positive(pattern: str, text: str) -> bool:
    # A prohibition in one clause must not consume a later affirmative command.
    for clause in re.split(CLAUSE_BOUNDARY, text):
        if _has(AMBIGUOUS, clause):
            continue
        for match in re.finditer(pattern, clause, re.IGNORECASE):
            prefix = clause[max(0, match.start() - 18):match.start()]
            if not _has(NEGATION + r"(?:\s|再|直接|继续|先|急着|给我|现在){0,5}$", prefix):
                return True
    return False


def _in_clause(pattern: str, text: str) -> bool:
    return any(_has(pattern, clause) for clause in re.split(CLAUSE_BOUNDARY, text))


def active_signal_matches(text: str, patterns: list[str]) -> list[str]:
    """Ignore explicitly negated or deferred routing targets within each clause."""
    matches = []
    for pattern in patterns:
        for clause in re.split(CLAUSE_BOUNDARY, text):
            if _has(r"(?:后面|以后|之后|稍后).{0,3}再", clause):
                continue
            for match in re.finditer(pattern, clause, re.IGNORECASE):
                if not _has(NEGATION, clause[:match.start()]):
                    matches.append(pattern)
                    break
            if pattern in matches:
                break
    return matches


def _evidence_valid(value: Any, *, version: str | None = None) -> bool:
    if not isinstance(value, dict):
        return False
    if not all(isinstance(value.get(key), str) and value[key].strip() for key in ["source", "quote"]):
        return False
    return version is None or value.get("outline_version") == version


def validate_writing_state(state: Any) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if state is None:
        return errors, warnings
    if not isinstance(state, dict):
        return ["writing_state must be an object"], warnings
    if state.get("stage") not in STAGES:
        errors.append("writing_state.stage must be outline, full_draft, or revise")
    version = state.get("outline_version")
    if version is not None and (not isinstance(version, str) or not version.strip()):
        errors.append("writing_state.outline_version must be a non-empty string")
    for field in ["outline_confirmation", "full_draft_authorization"]:
        value = state.get(field)
        if value is None:
            continue
        if not _evidence_valid(value) or not isinstance(value.get("outline_version"), str) or not value["outline_version"].strip():
            errors.append(f"writing_state.{field} requires outline_version, source, and quote")
        elif not version or value["outline_version"] != version:
            warnings.append(f"writing_state.{field} is stale or has no current outline_version")
    if "draft_source" in state and not _evidence_valid(state["draft_source"]):
        errors.append("writing_state.draft_source requires source and quote")
    return errors, warnings


def _state_can_continue_draft(state: dict[str, Any]) -> bool:
    version = state.get("outline_version")
    return bool(
        isinstance(version, str)
        and version.strip()
        and _evidence_valid(state.get("outline_confirmation"), version=version)
        and _evidence_valid(state.get("full_draft_authorization"), version=version)
    )


def decide_writing_request(
    text: str,
    *,
    brief_ready: bool = False,
    writing_state: Any = None,
    has_brief: bool = False,
    user_confirmed_skip: bool = False,
) -> dict[str, Any]:
    clean = instruction_text(text)
    state_errors, state_warnings = validate_writing_state(writing_state)
    state = writing_state if isinstance(writing_state, dict) and not state_errors else {}

    def result(decision: str, artifact: str | None, reason: str, **extra: Any) -> dict[str, Any]:
        return {
            "ok": decision.startswith("ready_to_"),
            "decision": decision,
            "requested_artifact": artifact,
            "may_write_full_draft": decision == "ready_to_draft",
            "reason": reason,
            "advisory": True,
            "explicit_request": bool(outline_command or full_command or revise_command),
            "warnings": state_errors + state_warnings,
            **extra,
        }

    outline_command = _positive(
        r"(?:先|只|仅)(?:要|给我|给|出|列|看|做|整理|提供|写|一个|一份|\s){0,8}" + OUTLINE
        + r"|(?:给我|给|提供|列出|整理|输出|写|做|draft|write).{0,10}" + OUTLINE,
        clean,
    )
    prohibits_full = _in_clause(NEGATION + r".{0,10}" + FULL, clean)
    full_command = _positive(
        r"(?:写|出|给|生成|起草|产出|write|draft).{0,10}" + FULL
        + r"|直接(?:给我|帮我|\s){0,3}写(?:(?:一篇|一版|一份)(?:口播稿|稿子|正文|稿)?|口播稿|稿子|正文|稿)",
        clean,
    )
    revise_command = _positive(r"(?:改稿|修改|重写|改写|润色|清洗|精简|压缩|扩写|补上衔接|补齐|修错字|去口癖|revise|rewrite|clean\s+up)", clean)

    # Explicit limits win before the brief, prior permissions, or interview waiver.
    if outline_command:
        return result("ready_to_outline", "outline", "current request asks for an outline; do not produce a full draft")
    if prohibits_full:
        if revise_command:
            return result("ready_to_revise", "revise", "revise the requested existing passage only; full drafting is prohibited", scope="requested_passage_only")
        return result("needs_context", None, "current request prohibits a full draft; recover the requested next artifact")

    ambiguous = _has(AMBIGUOUS, clean)
    if ambiguous and (full_command or revise_command or _has(OUTLINE + "|" + FULL, clean)):
        return result("needs_context", None, "conditional, quoted, or ambiguous wording requires conversational interpretation")

    outline_confirmed_now = _positive(
        OUTLINE + r"(?:\s*[A-Za-z0-9_.-]+)?(?:已经|已|都|就|是|\s){0,4}(?:确认|通过|没问题)"
        + r"|(?:已经|已)确认(?:的)?" + OUTLINE,
        clean,
    ) and not _has(OUTLINE + r".{0,8}(?:还没|未|没有|尚未|不算|不予)确认", clean)
    direction_confirmed_now = _positive(r"(?:已|已经)确认.{0,5}(?:方向|brief)|(?:方向|brief).{0,5}(?:已|已经)确认", clean)
    explicit_bypass = _positive(r"直接(?:给我|帮我|为我|\s){0,3}(?:写|出|生成)|draft\s+directly", clean)
    interview_waived = user_confirmed_skip or _positive(r"跳过采访|不用采访|不用调研|skip\s+(?:interview|research)", clean)
    outline_unconfirmed_now = _in_clause(
        OUTLINE + r".{0,8}(?:还没|未|没有|尚未|不算|不予)确认"
        + r"|(?:还没|未|没有|尚未|不算|不予)确认(?:的)?" + OUTLINE,
        clean,
    )
    expands_outline = full_command and _has(OUTLINE, clean) and _positive(r"(?:扩写|展开|写成|转成).{0,6}" + FULL, clean)

    if revise_command and not expands_outline:
        if _has(r"(?:这|上|原|现有|已有|用户|我写|我说|以下|下面).{0,10}(?:稿|段|版|文|内容|口述)|改稿|改写|润色|清洗|revise|rewrite", clean) or _evidence_valid(state.get("draft_source")):
            return result("ready_to_revise", "revise", "edit the existing user-identified text; preserve its authorship and requested scope")
        return result("needs_context", "revise", "recover the source passage and requested edit; do not restart a full interview")

    if outline_unconfirmed_now and not (full_command and explicit_bypass):
        return result("needs_context", None, "current outline is explicitly unconfirmed; old authorization cannot select the next artifact")

    if full_command:
        if outline_confirmed_now or brief_ready or explicit_bypass or _state_can_continue_draft(state):
            return result(
                "ready_to_draft", "full_draft", "current user request explicitly authorizes a full draft",
                authorization={"source": "current_request", "quote": text.strip()},
                outline_confirmation_source=(
                    "current_request" if outline_confirmed_now
                    else state["outline_confirmation"]["source"] if _state_can_continue_draft(state)
                    else None
                ),
            )
        if not has_brief and not writing_state and _has(RAW_IDEA, clean):
            if interview_waived:
                return result("ready_to_outline", "outline", "interview waiver permits outlining the raw topic; full drafting is not yet supported by its direction")
            return result("route_to_interview", None, "raw idea needs focused direction and first-hand evidence before outlining")
        return result("needs_context", "full_draft", "full draft requested; recover existing direction, outline, and evidence before asking only for missing context")

    if _has(CONTINUE, clean):
        if state.get("stage") == "full_draft" and _state_can_continue_draft(state):
            return result("ready_to_draft", "full_draft", "resume the authorized full draft for the same confirmed outline version", authorization=state["full_draft_authorization"])
        if state.get("stage") == "revise" and _evidence_valid(state.get("draft_source")):
            return result("ready_to_revise", "revise", "resume editing the identified source draft")
        if state.get("stage") == "outline" or (brief_ready and not state):
            return result("ready_to_outline", "outline", "resume the outline stage; direction approval alone is not full-draft authorization")
        return result("needs_context", None, "recover the current artifact and version-specific user authorization; do not restart the interview", recovered_stage=state.get("stage"))

    if outline_confirmed_now:
        return result("needs_context", None, "outline approval recorded in the request; approval alone does not choose the next writing action")
    if brief_ready or direction_confirmed_now:
        return result("ready_to_outline", "outline", "confirmed content direction supports outlining, not automatic full drafting")
    if has_brief or state_errors:
        return result("needs_context", None, "recover missing or invalid brief fields and current stage without repeating completed discovery")
    if _has(RAW_IDEA, clean):
        if interview_waived:
            return result("ready_to_outline", "outline", "interview waiver permits an outline from available evidence, not unrequested full prose")
        return result("route_to_interview", None, "raw idea needs focused direction and first-hand evidence before outlining")
    return result("needs_context", None, "identify the requested artifact from conversation; a regex result cannot supply missing intent")

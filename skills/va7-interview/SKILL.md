---
name: va7-interview
description: Clarify a rough VA7 content idea when the user's stance, audience, mechanism or first-hand evidence is missing. Recover existing decisions first and interview only for real gaps, then hand a confirmed brief to va7-script for a speaking outline. A missing JSON file or unlisted topic alone is not a reason to repeat an interview.
metadata:
  version: 0.1.0
---

# VA7 Content Interview

Turn a raw content idea into a usable VA7 content brief. Recover already-confirmed material before asking new questions. This prepares the argument; `va7-script` owns outlines, full scripts and revisions.

## Core Rule

Do not write a full口播稿 from a raw idea.

When the user gives only a topic, rough inspiration, link, claim, phrase, or vague direction, the next step is not drafting. The next step is:

1. Check whether this idea already exists in the VA7 inspiration library.
2. Understand what the topic actually means.
3. Do lightweight research only to map the terrain and avoid false claims.
4. Offer 3-5 possible content directions.
5. Interview the user to lock their real position, personal evidence, tension, audience, and boundaries.
6. Produce a `content_brief.json` and validate it.
7. After direction confirmation, hand off to `va7-script` for a speaking outline by default. Direction approval is not automatically approval to generate a full script.

The purpose is original content, not remixing public research. Research provides terrain; the interview provides the thesis.

## When To Use

Use this skill before writing when:

- the topic lacks usable stance or evidence in both the current/recovered conversation and available records;
- the user gives a new idea, complaint, observation, meeting fragment, or rough claim;
- the user's real stance is unclear;
- the topic could become multiple different videos;
- the idea needs personal examples, numbers, stories, or operating details;
- the draft would otherwise be based mainly on external research.

Reuse the current conversation, an approved outline, an existing user draft or a confirmed brief when they already supply the needed material. Missing serialization is not missing user knowledge: restore the brief and its confirmation source without asking the user to repeat it. Respect an explicit request to skip interview or directly draft, while keeping factual gaps visible. An outline-only or cleanup request should not automatically trigger a full interview.

## Workflow

### 0. Intake And Library Check

First recover the current request, prior decisions, outline/draft and source evidence. Then identify relevant records in the VA7 Base when context is still needed.

Use `va7-library` / `lark-base` to search:

- `选题库`: similar `选题标题`, `选题角度`, `口播草稿`, `口播终稿`, tags.
- `原始素材库`: related source materials, meeting notes, quotes.
- `成品内容`: whether a similar topic has already been published.
- `写作复盘任务`: whether past writing feedback already touched this topic.

Classify:

- `existing_ready`: existing topic has enough material and a confirmed direction.
- `existing_needs_interview`: topic exists, but stance/evidence/direction is weak.
- `new_topic`: no suitable record exists.

If `existing_ready`, follow the user's existing choice and proceed to the requested artifact. Ask which record to use only when selection is genuinely unresolved.

### 1. Terrain Research

Do lightweight research before interviewing only when it helps ask better questions.

Research should answer:

- What does this topic mean in the market / technical / cultural context?
- What are the common shallow takes?
- What would be dangerous to claim?
- What terms, projects, events, or examples need verification?
- What are the possible content angles?

Do not let research decide the thesis. Research is for mapping and pressure-testing.

If the topic contains a broad negative claim such as "市面上 X 都不行", "没人做 Y", "整个赛道错了", follow `va7-script/references/adversarial-research-protocol.md` before recommending a public-facing claim.

### 2. Direction Alternatives

If the direction is unresolved, present a small set of alternatives (usually 3-5). Do not reopen a direction the user has already selected. Each alternative must include:

- angle name;
- one-sentence thesis candidate;
- why this could be VA7-specific;
- what personal evidence is needed;
- risk if written without user interview.

Recommend one direction, but leave exactly one decision for the user: accept the recommendation, pick another direction, or ask for a different set.

### 3. Deep Interview

Interview for original thought. Ask one focused question per turn unless the user asks for a full questionnaire. Check the dimensions below against known evidence first; ask only about gaps that matter for this piece.

Minimum dimensions:

- **Real stance**: what does the user actually believe, not what sounds punchiest?
- **Personal evidence**: what did the user personally see, build, debug, spend, decide, or change?
- **Audience**: who should this video help or challenge?
- **Tension**: what common belief, behavior, or workflow is wrong or incomplete?
- **Mechanism**: why does the problem happen?
- **Boundary**: what is explicitly not being claimed?
- **Story material**: concrete scene, number, person, date, tool, customer, failure, or turning point.
- **Viewer payoff**: what does the viewer understand or do differently after watching?

Good interview questions are concrete:

- "你自己是在哪个具体场景里意识到这件事的？给我一个时间、工具、人物或数字。"
- "如果我把这个观点写成『全行业都错了』，你会反感吗？更准确的边界是什么？"
- "这个选题最容易被写成二手资料拼贴。你这里独有的一手经验是什么？"
- "观众看完到底少踩哪个坑，或者多一个什么判断框架？"

### 4. Content Brief

After research and interview, produce a brief, not a draft.

Use this shape:

```json
{
  "status": "ready_for_outline",
  "idea": "",
  "library_status": "existing_ready|existing_needs_interview|new_topic",
  "selected_direction": {
    "name": "",
    "thesis": "",
    "why_va7_specific": ""
  },
  "user_position": "",
  "audience": "",
  "viewer_payoff": "",
  "key_tension": "",
  "mechanism": "",
  "personal_evidence": [
    {"type": "scene|number|decision|failure|customer|tool", "detail": ""}
  ],
  "story_material": [],
  "non_goals": [],
  "claims_to_avoid": [],
  "research_notes": [],
  "open_questions": [],
  "confirmed_by_user": false
}
```

Run:

```bash
python3 ~/.claude/skills/va7-interview/scripts/validate_content_brief.py \
  --brief work/content_brief.json
```

For a confirmed brief handoff, validation must pass and `confirmed_by_user` must reflect an actual user message, including a confirmation recovered from the conversation. This confirms the brief, not an unseen outline. The legacy `ready_for_draft` status may be retained in existing files but does not by itself authorize full prose. Outline-only work may expose unresolved facts as placeholders rather than restart the entire interview.

### 5. Handoff To Writing

Only after validation and confirmation, hand off to `va7-script` with:

- the validated `content_brief.json`;
- relevant Base record IDs;
- research caveats;
- exact user quotes or paraphrased interview answers;
- the one selected direction;
- what not to claim.

`va7-script` should then produce the requested artifact from this context, normally a speaking outline. Preserve any approved outline version, confirmation source and revision scope; do not reset them during handoff. See its entrypoint for the optional `writing_state` format and stage decisions.

## Output Contract

During this skill, output one of:

- `方向方案`: 3-5 alternatives and one recommended next interview focus.
- `采访问题`: one high-leverage question.
- `内容创作 Brief`: validated brief for user confirmation.

Never output a complete口播稿 from this skill.

## Related Skills

- `va7-library`: read/write topic and material records.
- `wechat-topic-research` / `wearesellers-topic-research` / `content-topic-research-pipeline`: optional terrain research.
- `va7-script`: downstream writing only after brief confirmation.
- `agent-writing-rl-dataset`: post-hoc learning from accepted/rejected versions.

---
name: va7-pipeline
description: This skill should be used when the user asks to start or continue any VA7 content creation workflow, says "做内容", "内容创作", "这个选题", "我有个灵感", "继续这个内容", "查一下这个做到哪了", "启动 VA7 产线", "做口播/剪视频/做封面/发布物料/公众号/复盘", or wants one large orchestrating skill to route across va7-library, va7-interview, va7-script, video editing, cover making, publishing materials, WeChat publishing, and writing RL dataset workflows.
metadata:
  version: 0.1.0
---

# VA7 Content Pipeline

Use this as the single entrypoint for VA7 content production. It is an orchestrator, not a replacement for the specialized skills.

The job is to inspect the user's request, recover context, query the VA7 inspiration Base, determine the current production stage, then route to the smallest correct downstream skill. Do not write, edit, publish, cut video, or sync Base records directly when a specialized skill owns that step.

## OTA Check (once per day, before routing)

On the first invocation each day (check `work/va7-pipeline/ota-last-check` for today's date; skip if present), run:

```bash
bash <repo>/scripts/ota_check.sh
```

where `<repo>` is the local clone of `1va7/va7-skills` (default `~/.claude/skills-va7`; env `VA7_SKILLS_REPO`).

- If `up_to_date: true` → write today's date to `ota-last-check` and continue routing silently. Never mention the check to the user.
- If `up_to_date: false` → tell the user in one short message: "skillset 有更新（N 个提交）"，list the commit subjects and changed files, and ask "要不要更新？"。Only on explicit confirmation run `git pull` in the clone and re-sync changed skill files. Never pull silently.
- On any error (offline, no clone) → skip silently, do not block content work, and still write today's date to `ota-last-check` so the check isn't retried all day.

## Multi-User Config

Scripts in this skillset default to VA7's own production base. For any other user, set `VA7_USER_CONFIG` to their `config.json` (created by va7-onboarding) before running scripts — all reads/writes then go to that user's own base. Non-VA7 usage without this variable is a bug: stop and run va7-onboarding first.

## Core Rule

Never treat a raw topic as a drafting request.

For a rough idea with missing stance or evidence, route to `va7-interview` to fill those gaps. First recover existing user decisions: a missing brief file is not a reason to repeat an interview. `va7-script` owns speaking outlines, full scripts and revisions. A confirmed brief normally leads to an outline; full prose requires the user's request for it. An explicit request to draft directly can bypass outline review, while an outline-only request cannot be overridden by old approval.

## First Action: Run The Router

Run the scripted router before choosing a downstream skill:

```bash
python3 ~/.claude/skills/va7-pipeline/scripts/route_content_task.py \
  --input "<用户本轮原始请求>" \
  --out work/va7-pipeline/route.json
```

If the user provided a local file/folder/video path, pass it too:

```bash
python3 ~/.claude/skills/va7-pipeline/scripts/route_content_task.py \
  --input "<用户本轮原始请求>" \
  --path "<local path>" \
  --out work/va7-pipeline/route.json
```

When a local content brief already exists, also pass `--brief <path>`. It can include the optional version-specific `writing_state` documented by `va7-script`; do not create or repeat confirmations just to satisfy a file field.

Read `recommended_skill`, `required_checks`, and `next_actions`. The classifier is advisory: preserve the current request, negation, quoted examples and known stage. When it returns `needs_context`, recover the specific missing artifact or decision instead of automatically restarting interview. A known record ID is context, not approval.

## Context Recovery Order

Recover context in this order:

1. Current user request, confirmed decisions in this conversation, and any attached path or URL.
2. Existing local brief, route, manifest, or recent working files under `work/va7-pipeline/`, `work/va7-library/`, `work/writing-rl-datasets/`, and source media folders.
3. Live Feishu Base records in the VA7 inspiration library.
4. Existing Codex / Claude session logs only when the task is "continue", "复盘", or "找之前上下文".

Do not rely on memory when the Base or local files can be checked.

## Base Lookup

Use `lark-base` or the router script's generated CLI commands to inspect:

- `原始素材库` `<materials 表 id，见 config.json>`
- `选题库` `<topics 表 id，见 config.json>`
- `内容生产排期` `<schedules 表 id，见 config.json>`
- `成品内容` `<finished 表 id，见 config.json>`
- `写作复盘任务` `<writing_runs 表 id，见 config.json>`

Classify the request as:

- `new_raw_topic`: no matching topic or only weak material exists.
- `topic_needs_interview`: matching topic exists but lacks confirmed stance / personal evidence / content brief.
- `outline_stage` (gate: `ready_to_outline`): the user asks for an outline, or a confirmed brief is ready for one. Missing factual details can be marked for completion.
- `draft_stage` (gate: `ready_to_draft`): the user requests full prose from usable context, or gives explicit permission to draft directly.
- `revision_stage` (gate: `ready_to_revise`): an existing draft is being rewritten, continued, cleaned or locally edited. Recover the source and requested scope.
- `script_done`: draft/final口播 exists and user is asking for revision, video, cover, publishing materials, or WeChat conversion.
- `media_stage`: source video/folder exists and user wants editing or cover work.
- `publish_stage`: title/body/hashtag/chapter/成品内容 sync needed.
- `review_stage`: writing process has finished and user wants version tracking or RL dataset.

## Routing Table

Read `references/stage-routing.md` for details. Default routing:

| Stage | Route To | Gate |
|-|-|-|
| raw topic / new idea | `va7-interview` | Must not draft |
| broad unclear requirement | `deep-interview` then `va7-interview` if content | Do not implement inside deep-interview |
| outline request / confirmed content brief | `va7-script` | `ready_to_outline`; do not silently expand to full prose |
| approved outline + request for full prose | `va7-script` | `ready_to_draft`; preserve confirmation evidence |
| existing script / user oral rewrite | `va7-script` | `ready_to_revise`; preserve source and edit scope |
| raw material ingestion | `va7-library` | Upload via script and readback |
| video editing | `va7-monologue-video-editor` | Fast preflight first |
| cover design | `va7-video-cover-maker` | Candidate frame/copy gate |
| publish title/body/hashtag/chapters | `va7-publish` | Dry-run before apply |
| WeChat article | `wechat-converter` then `wechat-cover` then `wechat-draft-publisher` | Preserve images, pass inline-style audit, inspect actual WeChat preview |
| post-hoc learning | `agent-writing-rl-dataset` | scan/export/validate/sync |

## Deep Interview Role

Use `deep-interview` for broad ambiguity and intent clarification. It is a general Socratic requirements tool. For content topics, use it only to clarify intent and boundaries, then hand off to `va7-interview` to produce a VA7-specific content brief.

Do not let `deep-interview` hand off directly to `va7-script`.

## Output Contract

After routing, report briefly:

- detected stage;
- matched local/Base evidence, or "no match found";
- selected downstream skill;
- next gate or confirmation needed;
- exact command/output path when a script was run.

Then continue into the downstream skill. Ask for confirmation only when the user has not already authorized the next artifact; do not repeat a confirmation because it was absent from a local file.

## Red Lines

- Do not write a full口播稿 from raw topic input.
- Do not skip Feishu/Base lookup when the user asks to continue or asks where a content item stands.
- Do not treat `选题库.口播草稿` from ingestion as final writing evidence unless it is explicitly confirmed.
- Do not mix `interview-short-video-editor` into this pipeline; interview video editing is a different content type.
- Do not overwrite Base fields by hand when a downstream skill has a script.

## Routing Regression Checks

After changing writing-stage routing or the shared brief/intent helper, run:

```bash
python3 -B -m unittest discover \
  -s ~/.claude/skills/va7-pipeline/tests \
  -p 'test_*.py' -v
```

These checks cover artifact selection and confirmation handling, not the editorial quality of an outline. Also review representative outlines against `va7-script/references/speaking-outlines.md`.

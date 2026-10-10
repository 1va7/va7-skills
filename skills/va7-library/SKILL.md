---
name: va7-library
description: This skill should be used when the user asks to "加到灵感库", "记到灵感库", "这个可以做选题", "抓 T 号入灵感库", "转录后入灵感库", or wants to fetch Feishu docs, web/T/X material, audio/video transcripts, and upload structured inspiration topics into the VA7 Feishu Bitable inspiration library.
version: 0.2.0
---

# 选题灵感库

Build a scripted, schema-checked ingestion pipeline for VA7's content inspiration library. Do not manually improvise Bitable cell formats. Use the bundled script for fetching, transcription handoff, schema validation, duplicate search, upload, and post-upload verification.

## Default Workflow

Use the script first:

```bash
SKILL=~/.claude/skills/va7-library
OUT=work/va7-library/$(date +%Y%m%d-%H%M%S)

python3 "$SKILL/scripts/inspiration_pipeline.py" doctor
python3 "$SKILL/scripts/inspiration_pipeline.py" audit --out "$OUT/audit.json" --warn-only
```

Then choose the source:

```bash
# Feishu doc
python3 "$SKILL/scripts/inspiration_pipeline.py" fetch --feishu-doc '<doc-url>' --out-dir "$OUT"

# Web article
python3 "$SKILL/scripts/inspiration_pipeline.py" fetch --url '<url>' --out-dir "$OUT"

# T/X account
python3 "$SKILL/scripts/inspiration_pipeline.py" fetch --x-handle '<handle>' --limit 30 --out-dir "$OUT"

# Local exported text/json/jsonl
python3 "$SKILL/scripts/inspiration_pipeline.py" fetch --input-file '<path>' --out-dir "$OUT"
```

For audio/video material:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" prepare-audio --input '<media-path>' --out "$OUT/audio_16k.wav"
python3 "$SKILL/scripts/inspiration_pipeline.py" transcribe --audio "$OUT/audio_16k.wav" --out "$OUT/transcript.json"
```

Create the LLM fill scaffold:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" make-draft \
  --material "$OUT/material.json" \
  --transcript "$OUT/transcript.json" \
  --out "$OUT/draft.json"
```

Fill `draft.json` from `draft.prompt.md`, then:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" validate-draft --draft "$OUT/draft.json"
python3 "$SKILL/scripts/inspiration_pipeline.py" search-duplicates --draft "$OUT/draft.json"
python3 "$SKILL/scripts/inspiration_pipeline.py" upload --draft "$OUT/draft.json" --dry-run
python3 "$SKILL/scripts/inspiration_pipeline.py" upload --draft "$OUT/draft.json" --duplicate-policy warn
python3 "$SKILL/scripts/inspiration_pipeline.py" audit --out "$OUT/audit.after.json" --warn-only
```

Read `references/pipeline-usage.md` for backend configuration and examples.

## Script Ownership

Let `scripts/inspiration_pipeline.py` own deterministic operations:

- Read live Feishu schema before every upload.
- Convert date/select/link/text-url cell values.
- Normalize common select-value variants.
- Skip fields that are not present only when documented as optional.
- Search duplicate topic candidates before writing.
- Create material and topic records.
- Patch multi-select and link fields per row.
- Backfill material `关联选题`.
- Re-read created records and fail if required fields are empty.
- Audit live records across 原始素材库, 选题库, 成品内容, 内容生产排期, and optional 爆款选题库.
- Include field coverage and field policy in audit output so visible empty columns are classified as required, recommended, optional assets, metrics, or planning-only fields.
- Repair safe sync drift with `repair-safe`: linked-topic tags, linked material status, topic dates inferred from source material titles, missing published schedule links, and schedule topic type drift from linked finished content.
- Recover finished-content scripts from local Codex history with `repair-finished-from-history` only when an exact recovery rule matches.
- Sync newly published Xiaohongshu finished content from the VA7 account with `sync-finished-from-tikhub-user`: fetch the TikHub user posted-note list, match draft/scheduled finished-content rows by title/body, then write `链接`, platform `发布日期`, metrics, `IP属地`, `封面图URL`, upload `封面图`, and verify readback through audit. Use this before link-based TikHub repair when published rows naturally do not have links yet.
- Recover TikHub-synced Xiaohongshu platform fields with `repair-finished-from-tikhub`: fetch the note detail through TikHub, normalize `IP属地`, download the cover image, upload it to `封面图`, and fail loudly if Feishu ignores the attachment write.

Use the model for creative extraction only:

- Summarize the source material.
- Extract quotes.
- Split topics.
- Write `选题角度`, `人性钩子`, and a brief `口播草稿` seed only when it is clearly labeled as not final.
- Grade `认知密度` and `潜力等级`.
- For new or unconfirmed ideas, the upload output should prepare `va7-interview`, not bypass it. Do not treat the library draft as a publishable口播稿.

## Quality Bar

This library is not a notes archive. Each topic should be usable as content ammunition.

Material row:

- `内容摘要`: 5-10 concrete points with data, stories, cases, decisions, and tensions.
- `金句`: 5-10 memorable quotes or near-quotes with speaker/context where available.

Topic row:

- `选题角度`: one angle sentence, target <= 50 Chinese chars.
- `认知密度`: select value only: `高`, `中高`, `中`, `低`.
- `潜力等级`: `🔥高潜力`, `⚠️中等潜力`, or `💡素材向`.
- `人性钩子`: name the human trigger and include 1-2 concrete hook sentences.
- `口播草稿`: for unconfirmed or new topics, write a 200-500 Chinese character brief seed: candidate thesis, why it may matter, missing first-hand evidence, and 2-3 interview questions. Do not write a complete publishable口播稿 here. Full scripts belong after `va7-interview` produces a confirmed `content_brief.json`.
- `目标平台` and `标签`: never leave empty.

## Source Rules

For Feishu meeting notes, fetch the visible doc first and look for a transcript link. If the meeting note links to a full transcript doc, fetch that transcript too and use both as material. Do not rely only on the AI summary when a transcript exists.

For T/X accounts, prefer `X_BEARER_TOKEN`. If that is unavailable, configure `INSPIRATION_X_FETCH_CMD` so the script can call a known crawler. Do not manually paste partial timelines unless the user explicitly gives a limited sample.

For TikHub Xiaohongshu sync rows, do not treat missing `封面图` or `IP属地` as editorial optional fields. TikHub note detail can provide `ip_location` and cover media URLs. Use `repair-finished-from-tikhub` and review its plan/failures. The current `成品内容.封面图` field is API-writable; the old blocked field is preserved as `封面图旧_MOBILE_ONLY` for history.

For transcription, prefer a configured `INSPIRATION_TRANSCRIBE_CMD` for the user's accepted ASR stack. If absent, the script can use OpenAI audio transcription when `OPENAI_API_KEY` is set. If no backend is configured, stop after audio extraction and report the missing backend.

## Feishu Schema

Base token: `<base_token，见 config.json>`

Tables:

- 原始素材库: `<materials 表 id，见 config.json>`
- 选题库: `<topics 表 id，见 config.json>`
- 成品内容: `<finished 表 id，见 config.json>`
- 内容生产排期: `<schedules 表 id，见 config.json>`
- 爆款选题库: `<viral_topics 表 id，见 config.json>`

Do not rely on the field list in memory. It has drifted. Run:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" schema
```

Read `references/feishu-schema.md` when debugging field/type mismatches.

Critical current facts:

- `选题库` currently has no `状态` field, so topic status is optional and skipped by the script.
- `来源链接` is a text field styled as URL; write plain URL strings.
- Link fields use record ID string arrays through `lark-cli base`, e.g. `["recxxx"]`.
- Select fields must receive option names only, not explanations.
- Published `成品内容` rows must have `标题`, `平台`, `状态`, `发布日期`, `链接`, `正文描述`, `口播稿全文`, `选题类型`, and `关联内容排期`.
- `成品内容.封面图` and `成品内容.IP属地` are recoverable platform-export fields for TikHub rows, not fields to invent. The repair command verifies readback after attachment upload instead of trusting upload success.

## Auditing Existing Rows

When old runs produced empty or wrong fields, run:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" audit \
  --out "work/inspiration_audit_$(date +%Y%m%d-%H%M%S).json" \
  --warn-only
```

Use `--include-backlog` only when inspecting all `待拆解` materials with missing tags. The default audit focuses on structural failures: empty rows, required material/topic/finished-content fields, broken links, `已拆解` rows without linked topics, and published finished content without linked schedule/script/type. It also writes `field_coverage` so you can see all visibly empty columns and their policy.

For deterministic sync drift, use the safe repair command:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" repair-safe
python3 "$SKILL/scripts/inspiration_pipeline.py" repair-safe --apply
```

For finished content whose script/type is missing but exists in local Codex history, use the history recovery command. Always review the plan before applying:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" repair-finished-from-history \
  --plan-out "work/inspiration_repair_finished_from_history_plan.json"

python3 "$SKILL/scripts/inspiration_pipeline.py" repair-finished-from-history \
  --apply \
  --plan-out "work/inspiration_repair_finished_from_history_plan_applied.json"
```

For newly published Xiaohongshu content, links are expected to be absent in `成品内容` before sync. Do not manually search the account or hand-map fields. Use the TikHub user-note sync command first; always review the dry-run plan before applying:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" sync-finished-from-tikhub-user \
  --plan-out "work/inspiration_sync_finished_from_tikhub_user_plan.json"

python3 "$SKILL/scripts/inspiration_pipeline.py" sync-finished-from-tikhub-user \
  --apply \
  --plan-out "work/inspiration_sync_finished_from_tikhub_user_plan_applied.json"
```

Use `--record-id recxxx` to limit a run to known new rows, `--pages 2` if the new notes are not on the first account page, and `--min-score` only when reviewing a dry-run match. The command should own TikHub field extraction, cover download/upload, and metric/date normalization.

For TikHub-synced Xiaohongshu finished content missing cover/IP, use the TikHub recovery command. Dry-run fetches TikHub and downloads covers locally, but does not write Feishu:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" repair-finished-from-tikhub \
  --plan-out "work/inspiration_repair_finished_from_tikhub_plan.json"

python3 "$SKILL/scripts/inspiration_pipeline.py" repair-finished-from-tikhub \
  --apply \
  --plan-out "work/inspiration_repair_finished_from_tikhub_plan_applied.json"
```

By default the command also writes TikHub's cover media URL to `封面图URL` when that text field exists. Use `--create-cover-url-field --apply` to create it. If `failures[].error` contains `MOBILE_ONLY`, the command has hit an old or blocked attachment field; do not treat `封面图` as complete until readback passes.

For already-identified historical bad rows that need hard-coded recovery, use `scripts/repair_library_records.py` after reviewing its plan.

Do not auto-fix backlog materials just because tags are empty; most `待拆解` rows need editorial judgment.

## Reporting

After upload, report:

- material record ID
- topic record IDs
- high/mid/material topic titles with one-line angles
- duplicate candidates if any
- warnings from schema normalization
- whether post-upload verification passed

If upload was not run, report the generated `draft.json` and `draft.prompt.md` paths and the exact next command.

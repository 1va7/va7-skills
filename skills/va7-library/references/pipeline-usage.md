# Inspiration Library Pipeline Usage

Use `scripts/inspiration_pipeline.py` as the source of truth for deterministic work. The normal flow is:

```bash
SKILL=~/.claude/skills/va7-library
OUT=work/va7-library/$(date +%Y%m%d-%H%M%S)

python3 "$SKILL/scripts/inspiration_pipeline.py" doctor
python3 "$SKILL/scripts/inspiration_pipeline.py" audit --out "$OUT/audit.json" --warn-only
python3 "$SKILL/scripts/inspiration_pipeline.py" fetch --feishu-doc '<doc-url>' --out-dir "$OUT"
python3 "$SKILL/scripts/inspiration_pipeline.py" make-draft \
  --material "$OUT/material.json" \
  --out "$OUT/draft.json"
```

Fill `draft.json` with an LLM using `draft.prompt.md`, then run:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" validate-draft --draft "$OUT/draft.json"
python3 "$SKILL/scripts/inspiration_pipeline.py" search-duplicates --draft "$OUT/draft.json"
python3 "$SKILL/scripts/inspiration_pipeline.py" upload --draft "$OUT/draft.json" --dry-run
python3 "$SKILL/scripts/inspiration_pipeline.py" upload --draft "$OUT/draft.json" --duplicate-policy warn
python3 "$SKILL/scripts/inspiration_pipeline.py" audit --out "$OUT/audit.after.json" --warn-only
```

## Inputs

### Feishu document

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" fetch \
  --feishu-doc 'https://<你的飞书域名>.feishu.cn/docx/...' \
  --out-dir "$OUT"
```

The script uses `lark-cli docs +fetch --doc ... --format json`.

### Web URL

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" fetch \
  --url 'https://example.com/article' \
  --out-dir "$OUT"
```

This is a simple static fetch. If a page requires login or heavy rendering, use an appropriate browser/web skill first, save text to a file, then pass `--input-file`.

### T/X account

Preferred: configure X API v2.

```bash
export X_BEARER_TOKEN='...'
python3 "$SKILL/scripts/inspiration_pipeline.py" fetch --x-handle 'some_handle' --limit 30 --out-dir "$OUT"
```

Fallback: configure an external command that writes JSONL or text.

```bash
export INSPIRATION_X_FETCH_CMD='your-command --handle {handle} --limit {limit} --out {out}'
python3 "$SKILL/scripts/inspiration_pipeline.py" fetch --x-handle 'some_handle' --limit 30 --out-dir "$OUT"
```

The external command may write `{out}` as JSONL with rows containing `text`, `url`, `created_at`, and `metrics`, or print plain text to stdout.

### Local text/JSON/JSONL

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" fetch \
  --input-file '/path/to/source.jsonl' \
  --out-dir "$OUT"
```

### Audio/video transcription

First extract audio:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" prepare-audio \
  --input '/path/to/video_or_audio.mov' \
  --out "$OUT/audio_16k.wav"
```

Then transcribe. Preferred fallback is a project-specific external command:

```bash
export INSPIRATION_TRANSCRIBE_CMD='your-asr --audio {audio} --json {out}'
python3 "$SKILL/scripts/inspiration_pipeline.py" transcribe \
  --audio "$OUT/audio_16k.wav" \
  --out "$OUT/transcript.json"
```

OpenAI API fallback:

```bash
export OPENAI_API_KEY='...'
python3 "$SKILL/scripts/inspiration_pipeline.py" transcribe \
  --provider openai \
  --audio "$OUT/audio_16k.wav" \
  --out "$OUT/transcript.json"
```

Then combine material and transcript:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" make-draft \
  --material "$OUT/material.json" \
  --transcript "$OUT/transcript.json" \
  --out "$OUT/draft.json"
```

## Draft JSON Contract

`upload` accepts English keys or Chinese field names. Preferred shape:

```json
{
  "material": {
    "title": "素材标题",
    "type": "外部内容",
    "source_url": "https://...",
    "summary": "5-10个核心要点...",
    "quotes": "5-10条金句...",
    "tags": ["AI", "方法论"]
  },
  "topics": [
    {
      "title": "选题标题",
      "angle": "一句话角度，不超过50字",
      "cognitive_density": "高",
      "potential": "🔥高潜力",
      "script": "待采访确认的 brief seed：候选 thesis、缺失的一手证据、采访问题...",
      "human_hook": "恐惧/FOMO/反直觉 + 具体钩子句",
      "platforms": ["小红书", "视频号"],
      "tags": ["AI", "交付稳定性"],
      "topic_type": "专业性"
    }
  ]
}
```

Rules:

- `cognitive_density` must be a select value only: `高`, `中高`, `中`, `低`. Do not include the reason in the value.
- Put the reason inside `angle`, `human_hook`, or `script`.
- `script` is not a final口播稿 for new/unconfirmed topics. It should be a 200-500 Chinese character seed for `va7-interview`: candidate thesis, missing first-hand evidence, and interview questions.
- `potential` must match the live option. The script normalizes common variants such as `🔥 高潜力` to `🔥高潜力`.
- `source_url` is written as a plain URL string because the live `来源链接` field is text with URL style.
- `status` is intentionally optional for topics because the live topic table currently has no `状态` field.

## Upload Safety

`upload` always:

1. Reads live table fields with `base +field-list`.
2. Validates required fields and select values.
3. Searches duplicate candidates unless disabled.
4. Creates the material row.
5. Creates topic rows.
6. Updates per-topic multi-select/link fields one row at a time.
7. Backfills material `关联选题` and `状态`.
8. Re-reads created records and fails if required fields are empty.

Use `--dry-run` before real upload. Use `--duplicate-policy warn` only after reviewing duplicate candidates.

## Audit And Repair

Run structural audit after old or suspicious ingestions:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" audit \
  --out "work/inspiration_audit_$(date +%Y%m%d-%H%M%S).json" \
  --warn-only
```

The audit covers 原始素材库, 选题库, 成品内容, and 内容生产排期 by default. It reports:

- `issues`: action-oriented P0/P1/P2 problems.
- `field_coverage`: every live field's coverage plus a policy label, so large visible empty areas can be separated into required gaps, recommended fields, optional assets, metrics, and planning-only fields.

Default audit hides backlog enrichment gaps. To inspect all waiting materials missing tags or quotes:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" audit --include-backlog --warn-only
```

Apply only deterministic sync repairs with:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" repair-safe
python3 "$SKILL/scripts/inspiration_pipeline.py" repair-safe --apply
```

`repair-safe` only patches values inferable from existing links: material tags from linked topics, material status from existing linked topics, missing topic dates from source material titles or dates, missing finished-content schedule links, and missing schedule `选题类型` from linked finished content. It does not invent quotes, summaries, hooks, scripts, covers, or IP locations.

For published finished-content rows missing `口播稿全文` or `选题类型`, use local-history recovery only when a deterministic rule matches title and script markers:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" repair-finished-from-history \
  --plan-out "work/inspiration_repair_finished_from_history_plan.json"
```

Review `actions[].source` and script starts in the plan. Apply only after confirming the match:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" repair-finished-from-history \
  --apply \
  --plan-out "work/inspiration_repair_finished_from_history_plan_applied.json"
```

Use `--record-id rec...` to limit recovery to specific finished-content records. Use `--history-file /path/to/history.jsonl` only when the default `~/.codex/history.jsonl` is insufficient.

For TikHub-synced Xiaohongshu rows, `封面图` and `IP属地` should be recovered from TikHub rather than treated as optional blanks:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" repair-finished-from-tikhub \
  --plan-out "work/inspiration_repair_finished_from_tikhub_plan.json"

python3 "$SKILL/scripts/inspiration_pipeline.py" repair-finished-from-tikhub \
  --apply \
  --plan-out "work/inspiration_repair_finished_from_tikhub_plan_applied.json"
```

The command reads `TIKHUB_API_KEY` first, then known local TikHub `config.json` paths. Dry-run still fetches TikHub and downloads cover files to `work/tikhub-covers`, but does not write Feishu.

By default the command writes TikHub's cover media URL to `封面图URL` if that text field exists. To add the fallback field and write it in one run:

```bash
python3 "$SKILL/scripts/inspiration_pipeline.py" repair-finished-from-tikhub \
  --apply \
  --create-cover-url-field
```

Important: always keep the readback check. An older `成品内容` attachment field returned `MOBILE_ONLY: attachment field input is limited to mobile upload` and was preserved as `封面图旧_MOBILE_ONLY`; the current `封面图` field was rebuilt as an API-writable attachment field. If this error returns, the repair command reports it in `failures` and exits non-zero.

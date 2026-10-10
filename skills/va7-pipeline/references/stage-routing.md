# VA7 Content Pipeline Stage Routing

## Stage Signals

### `new_raw_topic`

Signals:

- "我有个灵感"
- "这个选题"
- "能不能写成口播"
- "帮我写小红书口播稿"
- A topic phrase with no brief, no record ID, and no confirmed user stance

Action:

- Search Base for similar topic and finished content.
- If no strong existing match, route to `va7-interview`.
- Offer direction alternatives before drafting.

### `topic_needs_interview`

Signals:

- Topic exists but only has source summary, rough angle, or ingestion-generated `口播草稿`
- No confirmed `content_brief.json`
- Missing personal evidence, user stance, non-goals, or viewer payoff

Action:

- Route to `va7-interview`.
- Use the existing Base record as context, not as permission to draft.

### `outline_stage` (Gate: `ready_to_outline`)

Signals:

- User asks for a speaking outline or bullet points.
- Confirmed brief/direction with enough context to map the argument.

Action:

- Route to `va7-script`, run its artifact-aware gate, and read `references/speaking-outlines.md` there.
- Deliver a checkable argument outline. Mark missing evidence rather than inventing it.
- Brief confirmation does not authorize a full script; current outline-only intent takes precedence.

### `draft_stage` (Gate: `ready_to_draft`)

Signals:

- User requests full prose from the current approved outline or other usable context.
- User explicitly asks to draft directly.

Action:

- Run `pre_draft_gate.py` with the original request and available brief.
- Recover confirmation from the conversation when absent from files; preserve the outline version and source.
- If the script reports `needs_context`, inspect the relevant artifact or decision. Do not equate missing JSON with a need to repeat interview.

### `revision_stage` (Gate: `ready_to_revise`)

Signals:

- User supplies an opening to continue, a whole oral rewrite to clean, or a passage to change.

Action:

- Recover the original text and edit scope; use `va7-script`.
- Preserve user contributions and approved boundaries. Requested local changes do not authorize unrelated rewrites.

### `media_stage`

Signals:

- User provides a folder/MOV/video path
- User asks "剪视频", "加字幕", "做封面", "抽帧", "候选帧"

Action:

- Video edit: route to `va7-monologue-video-editor`.
- Cover: route to `va7-video-cover-maker`.
- If both are requested, run preflight/frame extraction in parallel where practical.

### `publish_stage`

Signals:

- "发布物料", "标题正文 hashtag", "章节", "同步到灵感库", "成品内容"

Action:

- Route to `va7-publish`.
- Require dry-run and readback before applying writes.

### `wechat_stage`

Signals:

- "公众号", "公众号封面", "上传草稿箱", "WeChat draft"

Action:

- Convert article with `wechat-converter`.
- Generate cover with `wechat-cover`.
- Publish draft with `wechat-draft-publisher`.
- Require `style_audit.format_ok=true` before upload.
- Inspect the actual rendered draft in the logged-in WeChat backend; local HTML preview and API success are insufficient.

### `review_stage`

Signals:

- "复盘", "写作版本", "RL 数据集", "训练数据", "整理 session"

Action:

- Route to `agent-writing-rl-dataset`.
- Run scan/export/validate before Feishu sync.

## Ambiguity Handling

Use `deep-interview` when the user is asking for a broad plan, product/process design, or unclear meta-requirement. For content topics, immediately hand off from `deep-interview` to `va7-interview` before writing.

## Evidence Discipline

Treat these as evidence:

- Feishu record IDs and readback fields
- Validated `content_brief.json`
- Local route/manifest files
- Source media metadata and source-folder files
- User explicit confirmation in current or recovered session logs

Treat these as hints only:

- Old workspace drafts
- Ingestion-generated `口播草稿`
- Unconfirmed LLM summaries
- Agent memory without record IDs or files

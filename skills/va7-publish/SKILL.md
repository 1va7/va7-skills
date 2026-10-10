---
name: va7-publish
description: This skill should be used when the user asks to prepare or sync publishing materials for the VA7 inspiration library, including "发布物料", "文字标题", "正文", "Hashtag", "章节", "把标题正文 hashtag 同步到灵感库", "根据封面标题写发布标题", "小红书/抖音/视频号标题", or platform chapter timestamps.
version: 0.2.0
---

# Inspiration Publish Materials

Prepare platform publishing materials for VA7 videos from va7-library topics and sync approved copy into Feishu Base.

Use this skill together with `va7-library` and `lark-base` whenever the task touches the VA7 灵感库 / 成品内容 / 内容生产排期 tables.

## Core Principle

Separate the jobs of cover title and text title:

- Cover title stops the scroll. It can be punchier, shorter, and more emotional.
- Text title helps platform retrieval and recommendation. It must include searchable keywords, entities, target audience, and content category.
- Body copy explains the video promise in 2-4 compact paragraphs and embeds platform topic tags such as `#AI转型[话题]#`.
- Hashtag is a separate plain list, not a duplicate of the body. Use `#关键词` format.
- Chapters are timestamped platform metadata. Generate them from actual edited-video or subtitle timestamps, not guessed script positions.

Never write a final title by feel alone. Derive it from:

1. Existing published rows in `成品内容`.
2. The current cover title or cover image text.
3. The topic's `口播终稿`.
4. Current platform title patterns when the user asks for platform optimization or the topic is not obvious.

## Workflow

1. Load live schema with the va7-library script:

```bash
python3 ~/.claude/skills/va7-library/scripts/inspiration_pipeline.py schema
```

2. Read candidate topics from `选题库`. For current production work, filter for:

- `待做 == true`
- `发布排期` not empty
- `口播终稿` not empty

Read these fields at minimum: `选题标题`, `选题角度`, `待做`, `发布排期`, `口播终稿`, `文字标题`, `视频正文`, `Hashtag`, `章节`, `标签`, `目标平台`, `选题类型`, `关联内容排期`.

3. Write approved publishing material back to `选题库` first. The canonical topic fields are:

- `文字标题`
- `视频正文`
- `Hashtag`
- `章节`

4. Read related `内容生产排期` records through `关联内容排期`. The write targets are:

- `视频标题`: approved text title
- `视频文案介绍`: approved body copy
- `备注`: may hold a `[发布物料]` block with Hashtag for quick visibility
- `平台发布记录`: link to created or updated `成品内容`

5. Read related or existing `成品内容` rows. The canonical publishing material targets are:

- `标题`
- `正文描述`
- `Hashtag`
- `状态` as `草稿` for newly prepared material
- `平台` normally `小红书` unless the user specifies another platform
- `关联内容排期`
- `口播稿全文`

6. Draft title alternatives before writing. Always present 3-5 alternatives per video and wait for user approval unless the user explicitly provides final titles. For each alternative, include:

- intended platform(s)
- keywords being indexed
- relationship to cover title
- one short rationale

7. Draft chapters only when timestamp evidence exists. Use actual timestamps from the edited video, subtitle SRT, ASR JSON, or a user-provided timing list. If no timestamp source is available, ask the user for it before drafting chapters.

Chapter output for user review must be plain text in this exact block format:

```text
【章节标题】
00:01-00:56
章节内容
```

Rules:

- `章节标题` must be <= 14 characters. Chinese characters count as one character.
- `章节内容` must be <= 20 characters.
- Chapter count must be <= the video's duration in minutes, rounded up. Example: 2m30s allows at most 3 chapters.
- Use actual ranges, normally starting at the first retained spoken second, not necessarily `00:00`.
- Chapters must be sequential and non-overlapping.
- Do not invent timestamps from the written script alone.

8. After approval, write a JSON parameter file shaped like:

```json
[
  {
    "topic_record_id": "rec...",
    "title": "approved title",
    "body": "approved body copy with #话题[话题]# tags",
    "hashtag": "#AI #Agent #...",
    "chapters": [
      {
        "title": "章节标题",
        "start": "00:01",
        "end": "00:56",
        "content": "章节内容"
      }
    ],
    "video_duration_seconds": 150.0
  }
]
```

`chapters` is optional. It may also be a preformatted string using the exact three-line block format.

9. Run the bundled script first in dry-run mode:

```bash
python3 ~/.claude/skills/va7-publish/scripts/apply_publish_materials.py \
  --input work/materials.json \
  --plan-out work/plan.dry-run.json
```

Review the plan. It should update one schedule per topic and update or create one finished-content draft per schedule.

10. Apply only after the dry-run plan is correct:

```bash
python3 ~/.claude/skills/va7-publish/scripts/apply_publish_materials.py \
  --input work/materials.json \
  --apply \
  --plan-out work/plan.applied.json
```

The script performs readback checks for topic fields, topic chapters, schedule title, finished-content title, and Hashtag.

## Copy Rules

Read `references/platform-title-patterns.md` before drafting titles for 小红书, 抖音, or 视频号. Use the relevant platform section only.

Minimum title requirements:

- Include at least one domain keyword: `AI转型`, `Agent`, `AI创业`, `跨境电商`, `数字员工`, etc.
- Include at least one search/entity keyword when relevant: `token`, `英伟达`, `Claude Code`, `OpenClaw`, etc.
- Do not simply repeat the cover title. Complement it.
- Avoid empty slogans. Prefer searchable questions, concrete claims, or clear user problems.
- Keep the title natural enough to be user-facing.

Body copy requirements:

- Start with the search/interest frame in the first sentence.
- Compress the口播终稿, do not paste it wholesale.
- Preserve the core tension or data structure from the script.
- Use 4-6 in-body topic tags for 小红书-style copy.
- Keep it truthful to the script; do not introduce unsupported claims.

Hashtag requirements:

- 5-8 tags for most videos.
- Mix entity, domain, use case, audience, and method tags.
- Use plain hashtag format: `#AI创业 #早期创业者 #英伟达`.
- Avoid low-signal tags that are not in the title/body/script.

Chapter requirements:

- Prefer 3-6 chapters for normal short videos; fewer is fine for short/simple stories.
- Enforce `chapter_count <= ceil(video_duration_seconds / 60)`.
- Title describes the section's job, not just a noun.
- Content line summarizes what happens in that section.
- Use `references/chapter-format.md` for detailed examples and timestamp-source handling.

## Safety

- Do not overwrite `选题库.选题标题` just to store publishing titles.
- Do not write formula fields such as `发布排期`.
- Do not create duplicate `成品内容` rows if one is already linked to the schedule; update the existing row.
- Keep write operations script-driven and parameterized.
- If chapter timestamps are unavailable, ask the user for SRT/ASR JSON/video timing before generating chapters.
- If schema has drifted, stop and inspect live fields before writing.

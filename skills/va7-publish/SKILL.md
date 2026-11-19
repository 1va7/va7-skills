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

7. Draft chapters. **默认交文字版，每次都出，不需要时间，不依赖 SRT**：5 个以内的「章节标题（≤14 字）+ 换章句（该章第一句原话，必须能在口播终稿里逐字找到）」，格式：

```text
【章节标题】
换章句：该章第一句原话
```

   - 章节顺序必须与口播终稿中的出现顺序一致；成片有删改时标注「需对成片核对」。
   - **时间版是可选项**：只有已有剪辑环节产出的 SRT / ASR JSON / 用户给的时间点时，才补成「【标题】/起止时间/章节内容(≤20 字)」三行块，沿用原格式和规则（数量 ≤ 视频分钟数向上取整，顺序不重叠，不凭稿子编时间）。SRT 来自剪辑环节（`va7-monologue-video-editor` 的 `subtitles/` 目录），不是发布物料的前置条件。

8. After approval, write a JSON parameter file shaped like:

```json
[
  {
    "topic_record_id": "rec...",
    "title": "approved title",
    "body": "approved body copy with #话题[话题]# tags",
    "hashtag": "#AI #Agent #...",
    "title_alternatives": ["approved title", "alt 2", "alt 3"],
    "chapters": [
      {"title": "章节标题", "opening_line": "该章第一句原话"}
    ],
    "chapters_missing_reason": "仅当没有章节时填写",
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
- 正文控制在 200 字以内（不含话题标签与空白；VA7 2026-10-14 定版）。写法像论文摘要：开头一句 hook 交代为什么做这条内容，中间每段一个点、要点句领起加凝练短词排比推进，结尾一句判断收束、至多一句互动邀请。正文不加 emoji，破折号尽量不用（VA7 真实发布文案规律，语料提炼）。

Hashtag requirements:

- 5-8 tags for most videos.
- Mix entity, domain, use case, audience, and method tags.
- Use plain hashtag format: `#AI创业 #早期创业者 #英伟达`.
- Avoid low-signal tags that are not in the title/body/script.

Chapter requirements:

- Prefer 3-6 chapters for normal short videos; fewer is fine for short/simple stories.
- Enforce `chapter_count <= ceil(video_duration_seconds / 60)`.
- Title naming follows `references/chapter-format.md`「章节命名原则」（4-6 字，写这章交给观众的对象或判断，用稿子里的词）。
- Content line summarizes what happens in that section.
- Use `references/chapter-format.md` for detailed examples and timestamp-source handling.

## Safety

- Do not overwrite `选题库.选题标题` just to store publishing titles.
- Do not write formula fields such as `发布排期`.
- Do not create duplicate `成品内容` rows if one is already linked to the schedule; update the existing row.
- Keep write operations script-driven and parameterized.
- If chapter timestamps are unavailable, ask the user for SRT/ASR JSON/video timing before generating chapters.
- If schema has drifted, stop and inspect live fields before writing.

## 闸门（2026-11-16 定）

脚本：`scripts/publish_gate.py`（共用 `../va7-pipeline/scripts/gatelib.py`）。

1. 预检：`publish_gate.py preflight --script <口播终稿> --script-confirmed --cover-title <封面标题>`；封面没做必须用 `--no-cover-reason` 写明原因。
2. 交付：`apply_publish_materials.py --apply` 之前先跑 `publish_gate.py deliver --materials <json>`。核对：标题备选 3-5 个且 title 是其一、正文 ≤200 字、Hashtag 5-8 个、章节 ≤5 个且每章换章句在终稿里逐字存在并按顺序、没有章节必须写原因。通过输出校验码，交付消息末尾必须带。
3. 物料一次性交齐：标题备选、正文、Hashtag、章节（文字版）、封面标题备选（封面未做时）；缺哪样写明原因，不留空。

## 物料交付顺序与封面文案（王诗梦 2026-11-16 定）

出物料时按此顺序，一条消息交齐：

1. **封面大小标题备选 ×5**：每套 = 大标题（黄字）+ 小标题（白字，3-5 个要点）。要点用稿子里的判断或机制，不加稿子没有的数字。
2. **开头花字备选 ×3**：左上白字 2 行、右下黄字 2 行，每行 ≤7 字，用 `va7-video-cover-maker/scripts/huazi.py check` 检查，与封面标题不重复。
3. **文字标题备选 ×5**。
4. **正文**（≤200 字，带话题标签）。
5. **Hashtag**（5-8 个）。
6. **章节**（文字版，命名见 `references/chapter-format.md`）。
7. 一次交齐，不简写。

封面文案和花字人选定后，交给 va7-video-cover-maker 渲染；文字标题要与选定的封面大标题互补，不重复。

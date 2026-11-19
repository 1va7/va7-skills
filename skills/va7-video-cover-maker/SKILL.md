---
name: va7-video-cover-maker
description: This skill should be used when the user asks to make VA7口播视频封面图, create covers from an iPhone MOV/raw monologue video, generate 3:4/4:3/16:9 thumbnails, extract and score candidate frames from long videos, pick handsome frames, add 花字/title text, match previous VA7 cover style, handle HDR/SDR frame extraction on Mac/Linux, or revise a cover image based on feedback about face crop, font size, weight, shadow, or no outline.
---

# VA7 Video Cover Maker

## Scope

Use this for VA7口播视频封面图 made from raw MOV footage or a selected frame. The default deliverable is three finished JPG/PNG covers:

- vertical `3:4`
- horizontal `4:3`
- horizontal `16:9`（默认不做，见下）

**VA7 2026-10-14 定版**：默认只做 `3:4` 和 `4:3` 两种比例，`16:9` 仅在用户明确要求时制作。当用户直接发来一张图作为底图时，直接使用该图作为底图制作，不需要回到原视频里查找对应帧再截取。

The normal style is a strong frame from the original footage with large, bold Chinese title text. This is cover design, not video editing. Do not cut the video, add subtitles, or export a video unless explicitly asked.

If the user also asks to preserve or transplant metadata on a MOV deliverable, that is out of scope for this skill; route that part to `$iphone-mov-metadata-preserver` or the calling video-editing skill.

**First step in any sandbox（每次开工先跑，幂等，已就绪时秒过）**：`python3 <skills_root>/va7-cover-tools/scripts/cover_assets.py ensure`。它会装 Pillow、下载字体（NotoSansSC-Bold，来自 notofonts/noto-cjk 官方）和历史封面样本（1va7/va7-skills Release `cover-assets-v1`），都按 sha256 校验，缓存在 `$VA7_COVER_ASSETS`（缺省 `~/.cache/va7-cover-assets`）。输出 JSON 里的 `assets` 就是下文的 `<assets>`。所有脚本在 `<skills_root>/va7-cover-tools/scripts/`（下文写作 `../va7-cover-tools/scripts/`）；本技能目录只放说明和规则。

Read `references/va7-cover-style.md` before doing visual design or revisions.
Read `references/composition-and-reference-qa.md` before choosing crop boxes or reviewing any rendered cover.
Read `references/cover-copy-patterns.md` before proposing or revising cover copy.
Read `references/cover-case-library/index.md` when comparing historical patterns or selecting a precedent. Open only the relevant linked images, not the entire library by default.
Read `references/frame-extraction-performance.md` when the video is long, the host is unfamiliar, HDR color looks wrong, or candidate extraction needs to run in parallel with video editing.

## Save Location Rule

Final cover images must be saved inside the original source folder, in a subfolder named `cover/`.

Example:

- source: `~/Desktop/0611 创业信仰/IMG_5986.MOV`
- final folder: `~/Desktop/0611 创业信仰/cover/`
- final files:
  - `~/Desktop/0611 创业信仰/cover/创业信仰_封面_16x9.jpg`
  - `~/Desktop/0611 创业信仰/cover/创业信仰_封面_4x3.jpg`
  - `~/Desktop/0611 创业信仰/cover/创业信仰_封面_3x4.jpg`
  - `~/Desktop/0611 创业信仰/cover/创业信仰_封面_preview.jpg`

Use the Codex workspace only for temporary notes, scripts, rough comparisons, or backups. Do not leave the only final deliverables under workspace `outputs/`.

## Source Branches（先声明走哪个分支，写进预检）

封面有两个并列的主分支，开工前用 `../va7-cover-tools/scripts/cover_gate.py preflight --branch <direct_image|video_frame>` 声明：

- **direct_image（用户直接给图，实际最常见）**：不做任何色彩判断和处理，原图就是最终底图。不检查 HDR/SDR，不重新抽帧，不转色彩空间。预检记下原图 sha256，交付时 `cover_gate.py deliver` 要求渲染所用底图与它逐字节相同。
- **video_frame（从视频抽帧）**：下面的 Color Gate、HDR/SDR 规则只在这个分支生效。

构图阈值（头顶占比、标题字号、标题位置、左 padding 等）由预检从 `references/composition-and-reference-qa.md` 解析后写入 `cover_preflight.json`，不靠记忆。至少两张历史参考图、封面文案经人确认，缺一项预检不通过，渲染不得开始。

交付：严格 QA（`qa_cover_set.py --strict`）通过 + 对照板存在 + `cover_gate.py deliver` 输出校验码；交付消息末尾必须带校验码。人物构图好不好看、文案到不到位是 ◆ 判断项，留人审。

## Source Priority And Color Gate（仅 video_frame 分支）

When a folder contains both an original iPhone `.MOV` and an edited/exported video, use the original iPhone `.MOV` as the authoritative cover-frame source unless the user explicitly says otherwise. The edited video may be used for timing and subtitle reference, but it often has different color metadata, compression, and export tags.

Before generating cover candidates from iPhone HDR/HLG material, produce a raw vs SDR-managed comparison frame from the original video and visually verify the color path. On macOS, prefer the AVFoundation SDR extraction path for candidate and final frames. Do not continue to polished cover generation until the color path is confirmed. If the candidate sheet looks washed out, gray, cyan/green shifted, or unlike QuickTime/Photos playback, discard it and re-extract from the original source.

## Scripted Decision Gates

Do not infer source, copy, or final QA by memory or local cache alone. Use scripts first:

- source video selection, when ambiguous: `<skills_root>/va7-monologue-video-editor/scripts/find_source_video.py`
- title/copy reference candidates: `<skills_root>/va7-monologue-video-editor/scripts/find_reference_script.py`
- frame candidates: `../va7-cover-tools/scripts/extract_candidates.py`
- selected HDR/iPhone frame extraction on macOS: `../va7-cover-tools/scripts/extract_avfoundation_frame.swift`
- cover rendering: `../va7-cover-tools/scripts/render_cover_set.py`
- historical comparison board: `../va7-cover-tools/scripts/build_reference_qa_board.py`
- cover dimension QA: `../va7-cover-tools/scripts/qa_cover_set.py`

Historical cover previews and old workspace files are cache hints only. The authoritative title/copy source, when using 灵感库, is the live `选题库` row returned by `find_reference_script.py` after filtering `待做` checked, `发布排期` non-empty, and `口播终稿` non-empty.

For iPhone HDR/HLG sources (`color_transfer=arib-std-b67` or `color_primaries=bt2020`), the final cover frame must be an SDR-managed still produced by script. Do not use a `_raw` HDR JPEG/PNG as the final `--frame`; `render_cover_set.py` is expected to reject that unless explicitly overridden for diagnostics.

## First-Turn Rules

Do a fast preflight before polished design:

- source: exact video/still path, duration, resolution, frame rate, HDR/color tags
- host: macOS Apple Silicon / Linux NVIDIA / CPU-only / unknown
- copy/title: approved title / candidate titles from reference稿 or ASR / missing
- frame gate: candidate sheet ready for user selection
- output: ratios and source-folder `cover/` save location

Ask the user before final cover generation when:

- no approved frame exists
- no title/copy exists or multiple口播稿 candidates match
- HDR/SDR extraction produces visibly different candidate sheets and the better color path is uncertain
- the user has pointed to a reference style that has not been located

Do not treat a self-selected frame as final acceptance. Present candidates first unless the user explicitly says to pick and finalize without review.

## Performance Defaults

- Extract low-res candidate sheets first; extract full-res frames only after shortlist selection.
- Use `-ss` before `-i` for individual timestamp grabs.
- For long videos, sample frames in parallel from multiple timestamp ranges instead of decoding the entire 4K video at full resolution.
- If the monologue editing skill is also active, run frame extraction while ASR/render preflight runs; cover selection does not need to wait for final video export.
- On Linux or remote hosts, detect available fonts and image libraries before designing final covers.

## Required Inputs

Collect or infer these before making final covers:

- source video or approved still frame
- intended title/copy; if using 灵感库, run `find_reference_script.py` and select from eligible `口播终稿` candidates
- content type (`选题类型`); use the live 灵感库 field when available, otherwise infer it from the final script
- previous cover references, ideally the exact files the user points to
- output aspect ratios, defaulting to `3:4` and `4:3` (`16:9` only on explicit request)
- source color profile/HDR status from `ffprobe`
- target save location; default and preferred final location is `<source folder>/cover/`

If any of source video, title/copy, or output ratios are missing and cannot be inferred, ask a concise question before generating final covers.

## Workflow

### 1. Inventory

Locate the source folder and source `.MOV`/video file. If there is any ambiguity, run:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/find_source_video.py \
  --folder "$SOURCE_FOLDER" --out work/source_candidates.json
```

Proceed only when `ambiguous` is false, or after the user chooses one candidate. Inspect metadata:

```bash
ffprobe -hide_banner -i "$SRC"
```

Record duration, resolution, frame rate, codec, pixel format, and color tags. iPhone MOV files are often HDR/HLG; plan the still extraction accordingly.

Also detect extraction capabilities:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/preflight_media_pipeline.py \
  --src "$SRC" --pretty
uname -a
ffmpeg -hide_banner -hwaccels
ffmpeg -hide_banner -filters | rg 'zscale|colorspace|tonemap|scale' || true
fc-match 'Noto Sans CJK SC' 2>/dev/null || true
```

### 2. Study References

Open the user's reference covers and compare:

- face size and placement
- whether ears/hairline are visible in vertical crops
- text size relative to the face
- main/subtitle hierarchy
- color, shadow, stroke, and font weight
- where text avoids eyes, mouth, and important face contours

Select at least two same-type historical multi-ratio previews before designing. For professional knowledge covers with a core concept plus three points, prefer `0704-skill2loop`, `0623-loop-engineering`, and another environment-similar case. Record the exact reference paths in the layout or work notes. Do not guess the style from memory when reference files are available.

Use `0713-skills-sync-approved-composition-preview.jpg` as the default subject-position and crop-scale reference unless the user approves a different composition reference. Treat its v3 subject framing as accepted; do not drift back toward a lower or smaller person.

Use `0713-skills-sync-approved-layout-preview.jpg` as the default full-layout reference for main-title/subtitle geometry and padding.

### 3. Extract Frame Candidates

Extract multiple candidate frames from the source. Use the script first unless there is a clear reason not to:

```bash
python3 <skills_root>/va7-cover-tools/scripts/extract_candidates.py \
  --src "$SRC" --count 24 --mode sdr --workers 4
```

The script writes candidates and `contact_sheet.jpg` into `<source folder>/cover/candidates/`. Present that sheet for user selection.

Use the correct color pipeline:

- For iPhone HDR/HLG source, use the scripted SDR path. On macOS, prefer AVFoundation because it matches the system/iPhone color management more closely than raw ffmpeg JPEG extraction:

```bash
swift <skills_root>/va7-cover-tools/scripts/extract_avfoundation_frame.swift \
  "$SRC" "$TS" work/selected_frame_sdr.jpg 3840
```

- `extract_candidates.py --mode sdr` now detects HLG/HDR metadata and will prefer AVFoundation on macOS, then `zscale` when available. It should not silently fall back to raw HDR for final-quality SDR candidates.
- Compare raw vs SDR only as a diagnostic. If raw looks pale/gray/overexposed, do not proceed with raw.
- For long videos, make a low-res contact sheet first, then full-res grabs only for shortlisted timestamps.
- Prefer frames with open eyes, sharp face, confident expression, usable negative space, and no awkward mouth shapes.

Example:

```bash
ffmpeg -y -ss 48.5 -i "$SRC" -frames:v 1 \
  -vf "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709:t=bt709:m=bt709:r=tv,format=yuv420p" \
  work/review_frames/frame_048p5s.jpg
```

Adjust the exact filter based on the source. The important rule is to verify color visually before designing and to keep the chosen full-resolution frame's filename/provenance clear, e.g. `_avfoundation_sdr.jpg` or `_zscale_sdr.jpg`, not `_raw.jpg`.

For a long monologue, use the performance reference and produce a labeled candidate board. Prefer the script over manual one-off commands:

```bash
python3 <skills_root>/va7-cover-tools/scripts/extract_candidates.py \
  --src "$SRC" --count 36 --mode both --workers 6
```

If color is HDR/HLG, generate one raw sheet and one SDR-managed sheet for comparison before choosing the final frame pipeline. The approved final frame for rendering must be the SDR-managed frame.

### 4. Human Approval Gate: Frame And Copy

Before proposing copy from 灵感库, run:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/find_reference_script.py \
  --source-path "$SRC" \
  --asr-json work/asr/source_asr.json \
  --top 5 --include-script \
  --out work/reference_candidates.json
```

Use only records that passed the script's deterministic filter: `待做` checked, `发布排期` not empty, and `口播终稿` not empty. The model may use the returned candidates to propose 2-4 cover copy/title options, but it must not use `finished_content_*`, old cover previews, local ASR cache titles, or broad keyword `rg` hits as the source of truth. If no eligible reference candidate exists, label any ASR-derived copy as fallback and ask for approval.

Before writing options, classify the content using the live `选题类型`:

- For `专业性` or when type is unclear, default to a core knowledge keyword/concept as the main title and 3-4 parallel bullet points as the subtitle. The bullets should expose the video's main mechanisms, arguments, steps, or comparison dimensions.
- For `故事线` or a clearly narrative/opinion-led script, a conflict, judgment, or story hook may lead the main title; the subtitle may identify the audience, situation, or conclusion.
- Do not use the exceptional `买英伟达 / 不如 / 投自己` pattern as the default for professional knowledge content.

Apply the detailed checks in `references/cover-copy-patterns.md`, then compare only with same-type cases in `references/cover-case-library/index.md`.

Before making polished covers, present alternatives:

- a labeled sheet of frame candidates
- 2-4 copy/title alternatives when copy is not already approved
- brief notes on why each frame/copy works
- any color-pipeline comparison if HDR conversion is uncertain

Wait for user confirmation of both frame and copy. Do not directly produce and treat a final cover as accepted when the user has not approved the frame/copy.

### 5. Design Draft Covers

After approval, create draft covers for the required ratios.

Treat source fidelity and composition as separate concerns. Preserve the person's identity, expression, environment, and color, but actively recompose every ratio through crop, zoom, and translation. Never interpret “use this image as the base” or “preserve the original frame” as permission to retain the source framing.

Require an explicit non-null crop box for every ratio, including 16:9 sources rendered to 16:9. Tune the three crop boxes independently. Follow `references/composition-and-reference-qa.md`; do not use automatic center crop for a final cover.

Use `../va7-cover-tools/scripts/render_cover_set.py` with a JSON layout whenever possible. This makes revisions reproducible and keeps final exports in `<source folder>/cover/`.

Use the scripted `va7-main-title-clear` preset for yellow main title blocks unless the user explicitly asks for thicker/heavier type. This is the accepted 0612 Token消耗 title treatment: slightly smaller title, controlled fake-bold, and a light soft shadow. It prevents the yellow title from looking like it has a same-color outline or blurred edge.

Preset values currently applied by `render_cover_set.py`:

- `16x9`: `font_size=248`, `line_gap=18`, `weight=2`, `shadow={offset:[8,10], alpha:115, blur:1.4, weight:1}`
- `4x3`: `font_size=224`, `line_gap=18`, `weight=2`, `shadow={offset:[8,10], alpha:115, blur:1.4, weight:1}`
- `3x4`: `font_size=186`, `line_gap=16`, `weight=2`, `shadow={offset:[7,9], alpha:120, blur:1.4, weight:1}`

Example layout file. In real use, tune each spec separately after the user approves the frame/copy; do not rely on one shared text position for all ratios.

```json
{
  "specs": {
    "16x9": {
      "size": [3840, 2160],
      "crop": [0, 120, 3413, 2040],
      "text_blocks": [
        {"preset": "va7-main-title-clear", "lines": ["Skill", "反向进化"], "xy": [120, 120]},
        {"lines": ["捕获改动", "审核改动", "沉淀版本"], "xy": [130, 1390], "font_size": 178, "line_gap": 18, "fill": "#FFFFFF", "weight": 3, "shadow": {"offset": [10, 12], "alpha": 150, "blur": 2.2, "weight": 2}}
      ]
    },
    "4x3": {
      "size": [2880, 2160],
      "crop": [300, 60, 3100, 2160],
      "text_blocks": [
        {"preset": "va7-main-title-clear", "lines": ["Skill", "反向进化"], "xy": [95, 110]},
        {"lines": ["捕获改动", "审核改动", "沉淀版本"], "xy": [105, 1390], "font_size": 170, "line_gap": 18, "fill": "#FFFFFF", "weight": 3, "shadow": {"offset": [10, 12], "alpha": 150, "blur": 2.2, "weight": 2}}
      ]
    },
    "3x4": {
      "size": [1620, 2160],
      "crop": [980, 0, 2600, 2160],
      "text_blocks": [
        {"preset": "va7-main-title-clear", "lines": ["Skill", "反向进化"], "xy": [45, 54]},
        {"lines": ["捕获改动", "审核改动", "沉淀版本"], "xy": [56, 1330], "font_size": 166, "line_gap": 18, "fill": "#FFFFFF", "weight": 3, "shadow": {"offset": [10, 12], "alpha": 155, "blur": 2.2, "weight": 2}}
      ]
    }
  }
}
```

Render:

```bash
python3 <skills_root>/va7-cover-tools/scripts/render_cover_set.py \
  --preflight cover_preflight.json \
  --frame "$APPROVED_FRAME" \
  --source-video "$SRC" \
  --layout work/cover_layout.json \
  --prefix "创业信仰_封面"
```

For HDR/HLG source videos, this render command should fail if `$APPROVED_FRAME` is a raw HDR grab. Re-extract the selected timestamp through `extract_avfoundation_frame.swift` or another verified SDR-managed script path, then render.

Default VA7口播 cover rules:

- Preserve the selected frame's real person, expression, setting, and color; do not invent a fake background. Reframe it aggressively when needed.
- Put the face large, usually on the right.
- Put large text on the left or open negative space.
- Use two title levels by default: yellow/orange main title and white subtitle.
- Use no visible stroke/outline. Use soft shadow only when needed for readability.
- Use bold Chinese fonts such as Hiragino Sans GB / PingFang / STHeiti; do not rely only on huge size when actual weight is too thin.
- For yellow main titles, start from the `va7-main-title-clear` preset. Avoid `weight >= 4` plus shadow `weight >= 3` unless the user approves a heavier look after seeing a preview; that combination can make bright yellow glyphs look blurry or outlined.
- Keep text off the face, especially eyes, nose, mouth, and glasses.
- For vertical `3:4`, crop tighter than horizontal: hair top near the upper edge, face large, and avoid showing the ear when references show no ear.
- For vertical `3:4`, start title left/top padding around 5%/4% of the canvas and subtitle left padding around 6%. Move text inward without covering hair, glasses, eyes, nose, mouth, or face contours.
- Use the approved v4 title/subtitle geometry in `references/composition-and-reference-qa.md`: main title in the upper-left content zone, subtitle in the lower-left around 58%-72% canvas height, and subtitle left padding equal to or greater than the title's. Preserve two clearly separated information zones.

### 6. Human Approval Gate: Layout

Present draft cover(s) or a multi-ratio preview and ask for approval. Expect feedback on:

- chosen frame
- crop/face position
- ear/hair visibility
- text line breaks
- text size and weight
- color and shadow

Make targeted revisions. If the user approves 16:9 and 4:3 but only critiques 3:4, modify only 3:4.

### 7. Final Export

Export high-quality JPG/PNG files in the requested ratios. Use stable naming with version numbers during iteration and clearly indicate the final accepted files.

Recommended dimensions:

- `16:9`: `3840x2160`
- `4:3`: `2880x2160`
- `3:4`: `1620x2160`

Also export a combined preview sheet when several ratios are involved.

Final exports must be under `<source folder>/cover/`. If drafts were created in workspace `outputs/`, copy or re-render the accepted final set into `<source folder>/cover/` before final response.

### 8. QA

Build a historical-reference comparison board before running final QA. Put the current three-ratio preview first and at least two same-type historical previews below it:

```bash
python3 <skills_root>/va7-cover-tools/scripts/build_reference_qa_board.py \
  --current "$COVER_DIR/${PREFIX}_preview.jpg" \
  --reference <assets>/cover-case-library/local-previews/0704-skill2loop-preview.jpg \
  --reference <assets>/cover-case-library/local-previews/0623-loop-engineering-preview.jpg \
  --out "$COVER_DIR/${PREFIX}_reference_qa.jpg"
```

Open and inspect the comparison board. Write a visual-review JSON covering all checks specified in `references/composition-and-reference-qa.md`. Do not mark a check true without comparing the corresponding ratio against the historical rows.

Run strict QA before final delivery:

```bash
python3 <skills_root>/va7-cover-tools/scripts/qa_cover_set.py \
  --cover-dir "$(dirname "$SRC")/cover" \
  --prefix "$PREFIX" \
  --strict \
  --layout "$LAYOUT" \
  --source-frame "$APPROVED_FRAME" \
  --reference "$REF_1" --reference "$REF_2" \
  --qa-board "$COVER_DIR/${PREFIX}_reference_qa.jpg" \
  --visual-review "$VISUAL_REVIEW_JSON" \
  --out work/cover_qa.json
```

Inspect the final covers at full size and as thumbnails:

- face crop matches the approved reference style
- each ratio uses an explicit crop and visibly recomposes the source, including 16:9
- current preview appears in the same QA board as at least two same-type historical previews
- subject position, subject scale, head-top margin, text hierarchy, and text/subject separation are checked per ratio
- no unwanted ear in vertical crop when the user asked for none
- hair is not awkwardly cut unless intentionally flush with top edge
- text is large enough in the vertical cover
- text does not cover the face
- text line breaks match the approved copy
- no extra labels such as topic tags unless approved
- no visible outline/stroke
- shadow is readable but not hard/heavy
- color is not washed out from HDR mishandling
- final frame provenance is SDR-managed for HDR/HLG sources (`_avfoundation_sdr`, `_zscale_sdr`, or equivalent), not `_raw`
- all output ratios exist and have the correct dimensions

## Revision Rules

- Preserve approved parts. When the user says "other ratios are OK", do not change them.
- Answer concrete parameter questions directly, such as current font size, crop box, or shadow values.
- Prefer small controlled changes after the layout is close.
- Do not introduce new copy, tags, or decorative blocks after the user has approved the title structure.
- If a version was accepted except for one issue, branch from that version's crop and typography rather than rethinking the whole design.

## Common Commands

Check dimensions:

```bash
python3 - <<'PY'
from PIL import Image
from pathlib import Path
cover = Path(SRC).expanduser().resolve().parent / 'cover'
for p in cover.glob('*.jpg'):
    im = Image.open(p)
    print(p, im.size)
PY
```

Use `functions.view_image` or Markdown image tags to show local images back to the user in Codex desktop.

Check final cover folder:

```bash
find "$(dirname "$SRC")/cover" -maxdepth 2 -type f -print
```

## Parallel Workflow With Video Editing

When `va7-monologue-video-editor` is also active:

- start source inventory once and share the same `ffprobe`/color facts
- run ASR/reference search and cover candidate extraction concurrently
- use `find_reference_script.py` output for reference稿-based cover copy; use rough ASR only as a labeled fallback when the eligible reference search fails; still ask for copy approval
- do not wait for final subtitled video to extract frames unless the user wants subtitles visible on the cover, which is not the default
- avoid running multiple full-resolution video scans during final render; use saved candidate frames/contact sheets

## Guardrails

- Do not skip the frame/copy approval gate.
- Do not make final covers from an unreviewed screenshot unless the user explicitly selected it.
- Do not save final covers only in the Codex workspace; always place accepted final files under `<source folder>/cover/`.
- Do not add outlines/strokes unless explicitly requested.
- Do not make the shadow hard, black, and heavy; use soft shadows for legibility.
- Do not make vertical text too small. It should be thumbnail-readable.
- Do not cover the face with text.
- Do not ignore exact line breaks requested by the user.
- Do not reuse raw HDR grabs for final covers from iPhone HDR/HLG sources. Raw grabs are diagnostic only.

## 开头花字（放在封面流程「文案确认」之后）

花字是视频开头前 3 秒叠在画面上的字，不是封面。版式以 VA7 的样本图为准（横屏 1920×1080）：
- 左上：白字两行，情绪或问题句（样本：「FDE 太卷 / 被压价」）。
- 右下：黄字两行，关键词，右对齐（样本：「城市/赛道 / 主动选择」）。

输入：口播稿第一句；已确认的封面主副标题。

规则（由 ../va7-cover-tools/scripts/huazi.py check 强制）：
- 候选至少 2 套，每套 tl（左上）和 br（右下）各正好 2 行，附一句理由。
- 每行不超过 7 个字（样本最长 6 个）。
- 不得与封面标题任何一行完全相同。
- 含数字必须给 number_source。
- 含义对应开头第一句；脚本只给提示，人确认。

流程：
1. 写 huazi_candidates.json（见 huazi_candidates.sample.json）。
2. `python3 ../va7-cover-tools/scripts/huazi.py check --candidates huazi_candidates.json`，通过才继续；不通过退出码 2。
3. 人选定第几套。
4. 二选一：
   - 无人值守：`python3 ../va7-cover-tools/scripts/huazi.py render --choose N --out huazi.png`，得到 1920×1080 透明底 PNG，拖进剪映即可。没有通过的预检结果，或预检结果是旧格式，render 拒绝运行。
   - 有人在剪映里做：只交文字，不生成 PNG。

标准是样本：字号约占画面高度 13%、行距约 15.7%、白字纯白、黄字取样本色 (250,220,75)、字体用 Noto Sans SC Bold（2026-11-16 王诗梦看并排对比图后选定，以此为标准；Medium 偏细、Black 偏重，不用）。这些数是从样本图量出来的，不需要你们报数字，只需要看并排对比图说「行 / 不行」。

## 封面比例与出图纪律（王诗梦 2026-11-16 定）

- 封面固定出竖版 3:4，不用在出图前问比例；要横版时用户另说，横版是 4:3，不是 16:9。`qa_cover_set.py --ratios` 默认只查 3x4。
- 开头花字是叠在视频画面上用的，不是封面的一部分；花字预览只叠在原帧上，不叠封面。
- 直给图片也要按 3:4 基准手算 crop：人脸靠右、右边缘主动截断、眼鼻嘴可读、头顶比例 0-0.08，文字放左侧留白，不盖脸。
- 渲染后必须跑 `qa_cover_set.py --strict`（含对照板和逐比例目视复核），通过才发图；底图宽度小于目标 crop 的 1/2 时先告诉人「放大后会偏软」。

### 白字小标题与人物位置的硬规则（王诗梦 2026-11-16 定）

- 白字小标题：**每行至多 5 个字、不换行（一个要点一行）、至多 4 行**。`qa_cover_set.py` 已检查；要点写不进 5 字就改写，不拆行。
- 3:4 人物位置以 0713 基准为准，量化为：完整露出额头到下巴，头顶比例 0-0.08；眼镜左缘约在画面宽度 0.4 处，人脸靠右，右边缘最多截到耳朵；人脸左侧留出放大标题的位置，标题和小标题都不压头发和脸。
- 抽帧或底图里人物占比大、放不下标题时，不要硬裁成半张脸：先告诉人「这张底图放不下」，请对方换人物更小或分辨率更高的帧。

### 出图前必须先量底图（王诗梦 2026-11-16 定，起因：封面总要第二次才对）

1. 先看 0713 基准图，再看底图；在底图上量出人物坐标（源图像素）：`head_top_y`（头顶）、`hair_left_x`（标题高度处头发左缘）、`glasses_left_x`（眼镜左缘）、`mouth_left_x`（嘴左缘）、`ear_left_x`（耳朵左缘）、`chin_y`（下巴），写进 layout 的 `specs.3x4.subject`。
2. `render_cover_set.py` 出图前自动用这些坐标核对：头顶比例 0-0.08、眼镜左缘在 0.35-0.5、耳朵不能整个被裁、下巴在画内、大标题右缘不压头发、小标题右缘不压嘴，另外查字号和边距。没过就拒绝渲染，不是出完再看。
3. 构图和文案「好不好」必须由人看过说「行」，`cover_gate.py deliver --human-review '{by,message_id,quote}'`；agent 不得自己在 visual_review 里填 true 当通过。
4. 底图放不下所有条件（人物太大）时，先告诉人换帧，不硬凑。

- 白字小标题不加粗：`weight` 写 0，阴影 `weight` 也写 0（王诗梦 2026-11-16 看并排对比后定，叠加伪粗体笔画会糊成一团）。示例 layout 里小标题的 `weight: 3` 作废。黄色大标题仍沿用 `va7-main-title-clear`。

### 封面一次成功的标准流程（王诗梦 2026-11-16 确认，目标：之后做封面一次出对）

1. 看 0713 基准图 → 看底图 → 量人物坐标写进 `subject`（见上）。
2. 小标题按「每行 ≤5 字、≤4 行、不加粗」写好，大标题字号 ≥0.18×画布高/行数。
3. 运行 `../va7-cover-tools/scripts/suggest_crop.py --subject subject.json --text-blocks blocks.json --source-size WxH`，直接拿到满足全部构图条件的 crop；返回 `feasible:false` 就停，告诉人换帧，不硬凑。
4. 把 crop 写进 layout，`render_cover_set.py`（出图前自动再查一遍）→ `qa_cover_set.py --strict` → 对照板。
5. 发图，等人说「行」，才用 `cover_gate.py deliver --human-review` 记下人的原话和消息 id 取校验码。

### 白字小标题怎么写（原规则 + 2026-11-16 收紧）

原规则在 `references/cover-copy-patterns.md`，照它写，不要自己压缩改写正文句子：

1. 小标题是「内容目录」，不是口号：从口播里选出 3 条（第 4 条必须是独立且必要的核心点）最核心的机制、论点、步骤或比较维度。
2. 每条 2-5 字（原为 2-8 字，王诗梦收紧到 5 字），一行一条，不换行。
3. 平行：统一名词短语或统一动宾短语；独立：不重复改写同一点；核心：删掉任意一条都会损失内容结构；可扫读。
4. 流程：一句话写出「这条视频教会观众什么」→ 抽 5-7 个候选 → 合并重叠项 → 选 3-4 条 → 改成平行短语。可直接用大纲各层的 label（≤8 字，已是平行短语）作候选。
5. 主标题是核心概念或关键问题，不是口号；与小标题不重复。
6. `qa_cover_set.py` 检查条数 3-4、每条 2-5 字；平行、独立、核心由人审。

### 小标题第一次写不对的原因与已加的约束（2026-11-16）

原因：①规则其实在 `references/cover-copy-patterns.md`，但流程没有强制读，我没读就把正文句子压缩当小标题；②预检只检查「文案是否经人确认」，没有检查小标题的结构，所以重复、不平行的句子也能过。

约束：`cover_gate.py preflight` 现在必须带 `--copy-patterns-read-token VA7-COVER-COPY-READ-END-2026-11-16`（该文件末行读完标记）和 `--copy-json`（`{"title":[...],"bullets":[...]}`），脚本检查条数 3-4、每条 2-5 字、互不重复、不重复主标题；平行与核心留人审。

### 小标题放行条件：形式与内容都达标（王诗梦 2026-11-16 定）

- **形式**（脚本查）：3-4 条、每条 2-5 字、互不重复、不重复大标题、一行一条不加粗。
- **内容**（脚本查可追溯，人审判好坏）：`--copy-json` 里每条小标题必须在 `bullet_sources` 声明来自已确认大纲的哪一层（`{"bullet":"归因倒置","layer_id":"L1"}`），预检用 `--outline outline.json` 核对该层存在、各条来自不同的层、小标题与该层 label/judgment 字面相关；也就是小标题必须是大纲主张的压缩，不是另起炉灶，也不是正文句子的压缩。
- **怎么写**：默认直接取大纲每层的 `label`（≤8 字，已是平行的名词短语；超 5 字就取该层 `key_terms` 或判断里的核心词压成 2-5 字）。大纲只有 3 层时恰好 3 条；某层确实拆成两个独立主张且都是核心时才用第 4 条。
- 以上都过之后，仍须人说「行」（`◆小标题平行/核心`）才放行。

---
name: va7-monologue-video-editor
description: Edit VA7 one-take Chinese monologue/口播 videos from iPhone MOV or similar source footage. Use when the user asks to cut a desktop folder's MOV口播、一镜到底视频、创业/AI/IP口播视频, add ASR subtitles, choose Doubao/local ASR, trim only the silent/fake-start opening and extra ending seconds, match or confirm the va7-library口播终稿, preserve original resolution/frame rate/HDR/metadata where practical, use hardware-aware fast rendering on Mac/Linux, save the final edited video back into the original source folder, QA the result, and optionally send via Feishu CLI.
---

# VA7 Monologue Video Editor

## Scope

Use this for VA7's own one-take口播 videos. These are not interview clips: do not mine themes, rearrange structure, add B-roll, add title cards, add music, or make creative cuts unless the user explicitly asks.

Default output:

- same aspect ratio, resolution, frame rate, HDR/color tags, container family, and global shooting metadata as the source where practical
- on macOS for iPhone MOV workflows, preserve Finder/Spotlight-visible metadata such as GPS, `Encoding Software`, and `Timed Metadata` when practical; do not assume `ffmpeg -map_metadata 0` alone is enough
- final edited video saved in the same folder as the source MOV, not only in the Codex workspace
- head trim: remove setup breathing, sighs, fake laughs, and silence before the first intended spoken line
- tail trim: remove only extra silence or camera-stop seconds after the last intended line
- verbatim Chinese subtitles from ASR, corrected with the reference口播终稿 for names, English terms, and logic
- no花字, no BGM

## First-Turn Rules

Do a fast preflight before any long ASR or render job. The preflight must answer:

- source file: exact path, size, duration, codec, resolution, frame rate, HDR/color tags
- host profile: macOS Apple Silicon / macOS Intel / Linux CPU / Linux NVIDIA / other; available encoders and ASR tools
- reference status: exact口播稿 matched / several likely matches / no match
- ASR route: Doubao / local MLX Whisper / CUDA faster-whisper / whisper.cpp or other fallback
- user gates: whether a decision needs confirmation before expensive work

Ask the user before continuing when any of these are true:

- multiple plausible source videos exist and file size/time does not clearly identify the口播
- no high-confidence灵感库/口播稿 match exists; present the top 2-5 candidate titles or say no match was found
- both Doubao and local ASR are available and the user has not established a preferred backend for this project
- only a slow or low-confidence ASR backend is available
- a non-Mac/Linux host requires changing output codec/container from the source-like default

Do not silently run a long ASR or final render while the matching稿件 or ASR backend is still ambiguous. It is fine to run cheap preflight commands and short samples while waiting.

## Performance Defaults

Prefer the fastest correct path for the current host; do not assume Apple Silicon. Read `references/performance-routing.md` when the environment is new, slow, remote, Linux, or when encoding/ASR choices matter.

- Use `multi_tool_use.parallel` for independent inventory reads, `ffprobe`, `exiftool`, reference search, ASR environment checks, audio extraction, and cover-candidate extraction.
- For audio-only checks, always use `-vn` and map audio; do not accidentally decode 4K video for `silencedetect`, waveform, or ASR extraction.
- For frame checks, extract only the needed frames or a low-res proxy/contact sheet first; avoid scanning the full 4K stream unless necessary.
- For final subtitle burn-in, use one video encode only. On Apple Silicon prefer `hevc_videotoolbox`; on NVIDIA Linux prefer `hevc_nvenc`; on Intel Linux consider `hevc_qsv`/VAAPI; otherwise use `libx265` only as a slower fallback.
- During subtitle burn-in, audio may be copied for speed, but the final deliverable must pass loudness normalization. Use video stream copy plus audio-only re-encode for loudness so 4K HDR video is not re-rendered.

## Scripted Decision Gates

Do not make these decisions by ad hoc `rg`, local cache inspection, or model memory. Run the script first, then use model judgment only on the structured candidates:

- source video selection: `scripts/find_source_video.py`
- va7-library reference稿 selection: `scripts/find_reference_script.py`
- trim point proposal: `scripts/suggest_trim_points.py`
- ASR/reference correction review: `scripts/compare_asr_reference.py`
- audio loudness normalization: `scripts/normalize_audio_loudness.py`
- subtitle/archive persistence: `scripts/archive_subtitle_artifacts.py`
- iPhone MOV metadata preservation: `scripts/preserve_iphone_metadata.py`
- final render checks: `scripts/qa_final_video.py`

Historical workspace files, prior ASR JSON, finished-content exports, and old cover previews are cache hints only. They are never the source of truth for the reference稿件.

When the task explicitly involves preserving or transplanting iPhone MOV metadata, also use `$iphone-mov-metadata-preserver` as the canonical metadata-fix workflow instead of improvising one-off remux commands.

## Save Location Rule

The final deliverable must be written to the original source folder, beside the source `.MOV`.

Use the workspace only for intermediate files such as ASR JSON, subtitle PNGs, QA frames, and draft tests. Do not leave the only final video under `outputs/` or any Codex working directory.

Subtitle and ASR process files are not disposable. Before final delivery, run `scripts/archive_subtitle_artifacts.py`; do not hand-copy or hand-name subtitle files. The script always writes beside the source video under `<source folder>/subtitles/` and enforces the archive schema:

- `*_asr_source_relative_*.json`: raw ASR JSON with segment timestamps against the original source MOV
- `*_source_relative_rough_asr.srt` / `.tsv` / `.txt`: rough ASR transcript aligned to the original source MOV
- `*_edited_relative_corrected.srt` / `.ass` / `.tsv` / `.txt`: corrected transcript aligned to the final edited video, when subtitles were corrected and trim points are known
- `*_edited_relative_rough_asr_estimated.*`: only when final trim is inferred rather than confirmed; label it clearly as draft/estimated
- `*_subtitle_archive_manifest.json`: source path, final path, trim offsets, quality notes, and file list
- `README.md`: explain which files are source-relative vs edited-relative

Use `.tsv` as the machine-friendly format for later chapter/segment generation (`index`, `start`, `end`, `start_seconds`, `end_seconds`, `text`). Use SRT/ASS for editing tools.

Naming convention:

- source: `~/Desktop/0611 创业信仰/IMG_5986.MOV`
- final: `~/Desktop/0611 创业信仰/IMG_5986_口播剪辑_字幕.MOV`
- revised versions: `~/Desktop/0611 创业信仰/IMG_5986_口播剪辑_字幕_v2.MOV`
- clean remux if needed: `~/Desktop/0611 创业信仰/IMG_5986_口播剪辑_字幕_clean.MOV`

If a project folder contains a user-facing naming pattern, follow that pattern, but keep the file in the same source folder. If the user explicitly asks for an additional copy elsewhere, create it in addition to the original-folder final.

## Workflow

### 0. Environment And Capability Preflight

Run these before choosing ASR or render commands:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/preflight_media_pipeline.py \
  --src "$SRC" --pretty
uname -a
sysctl -n machdep.cpu.brand_string 2>/dev/null || true
ffmpeg -hide_banner -hwaccels
ffmpeg -hide_banner -encoders | rg 'videotoolbox|nvenc|qsv|vaapi|hevc|libx265' || true
which ffmpeg ffprobe exiftool python3 lark-cli mlx_whisper whisper-cli whisper.cpp whisper || true
```

Read `metadata_preservation` from the preflight output. If the source has iPhone `mebx` metadata tracks on macOS, the default delivery route is:

- render clean A/V first
- then run `scripts/preserve_iphone_metadata.py`

Do not skip this when Finder-visible metadata matters.

Classify the host:

- Apple Silicon Mac: use local MLX Whisper when configured; use `hevc_videotoolbox` for final 4K HEVC renders.
- NVIDIA Linux: use CUDA ASR if configured; use `hevc_nvenc` for final HEVC renders.
- CPU-only Linux/remote: favor Doubao ASR if credentials are configured; warn before slow CPU-only final encodes.
- Unknown host: run a 5-10 second render smoke test before the full render.

If the script reports `discovered_tool_paths` or `discovered_asr_workflow_files`, treat them as candidate prior workflows, not automatic truth. Report the candidate path and ask before using it when the backend choice affects cost, speed, or privacy.

### 1. Inventory

Locate the user-provided folder and identify the source `.MOV` or video file through the source-selection script:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/find_source_video.py \
  --folder "$SOURCE_FOLDER" --out work/source_candidates.json
```

If the user provides only a query such as a desktop folder name, use:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/find_source_video.py \
  --query "0612 Token消耗" --root ~/Desktop --out work/source_candidates.json
```

Proceed automatically only when `ambiguous` is false and `selected.path` is present. If ambiguous, show the candidates and ask the user to choose. After selecting the source, run `ffprobe` before editing and record:

- duration, resolution, frame rate, codec, pixel format
- color primaries/transfer/space, especially iPhone HDR/HLG
- audio codec/sample rate/channels
- global tags such as `com.apple.quicktime.make`, `model`, `software`, `creationdate`, `location.ISO6709`

Also record metadata-preservation signals from preflight:

- metadata track count
- whether Finder/Spotlight reads `Timed Metadata`
- whether Finder/Spotlight reads latitude/longitude
- whether Finder/Spotlight reads `EncodingApplications`

If multiple MOV files exist, inspect file sizes and modification times, then pick the likely口播 source. Ask only if ambiguous.

### 2. Find Reference Script

Use `scripts/find_reference_script.py`; do not hand-search Feishu exports, local caches, or finished-content records as the primary reference source.

The script must query the live va7-library `选题库` table and apply this deterministic filter before scoring candidates:

- `待做` checkbox is checked
- `发布排期` is not empty
- `口播终稿` is not empty

Run a hint-only search during first-turn preflight:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/find_reference_script.py \
  --source-path "$SRC" --hint "$TOPIC_HINT" --top 5 \
  --out work/reference_candidates.pre_asr.json
```

After rough ASR exists, rerun with ASR scoring and include the selected script text:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/find_reference_script.py \
  --source-path "$SRC" \
  --asr-json work/asr/source_asr.json \
  --top 5 --include-script \
  --out work/reference_candidates.json
```

The model's job is to inspect `work/reference_candidates.json` and decide which candidate actually matches the口播. The model must not skip the deterministic filter because a local cache, old ASR, `finished_content_*`, `production_schedule_*`, or keyword `rg` result looks plausible. If the script returns no candidates, say no eligible `待做 + 发布排期 + 口播终稿` row was found and ask for the matching稿件 or permission to proceed ASR-only.

Reference matching confidence:

- high: folder/title/source name or exact hook matches a single record; proceed
- medium: 2-5 likely titles match the same topic; ask the user which one before final subtitle correction
- low: no plausible title or multiple unrelated matches; ask the user for the matching稿件 or permission to proceed ASR-only

Use the reference script only for:

- correcting terms such as `英伟达`, `Anthropic`, `All in`, `bootstrap`, company/product/person names
- understanding intended sentence boundaries and argument structure
- spotting ASR hallucinations or missed words

Do not force subtitles to exactly equal the script. The final subtitles must match the retained audio.

### 3. ASR

Choose ASR through an explicit route, not by accident:

1. If the user specified Doubao/local/Whisper, use that.
2. If a project-local or previous accepted workflow exists for the same VA7 video pipeline, prefer it, but report it before launching a long job.
3. If both Doubao credentials/scripts and local MLX/CUDA ASR are available, ask which to use unless the user asked for "fastest" or "cheapest".
4. If the host is Apple Silicon and MLX Whisper is already installed/cached, use MLX for local fast ASR.
5. If the host is Linux with NVIDIA and faster-whisper/CUDA is installed, use CUDA ASR.
6. If local ASR is missing or slow and Doubao is configured, use Doubao.
7. If only CPU Whisper is available, warn that it may be slow and ask before running on long videos.

Extract ASR audio quickly:

```bash
ffmpeg -hide_banner -y -vn -i "$SRC" -map 0:a:0 -ac 1 -ar 16000 \
  -c:a pcm_s16le work/asr/source_16k.wav
```

Produce:

- ASR JSON with segment timestamps
- rough SRT
- a correction list for names/terms
- notes on likely opening chatter and ending extra seconds

### 4. Decide Trim Points

Generate trim candidates through the trim script, then inspect the first few seconds with both audio and frames. The start point should land on the first intentional word, not on a preparatory sigh, laugh, mouth click, or inhale.

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/suggest_trim_points.py \
  --src "$SRC" \
  --asr-json work/asr/source_asr.json \
  --out work/trim_points.json
```

Recommended checks:

```bash
ffmpeg -hide_banner -nostats -vn -i "$SRC" -map 0:a:0 \
  -af silencedetect=noise=-35dB:d=0.08 -t 8 -f null -
ffmpeg -hide_banner -y -ss "$CANDIDATE_START" -i "$SRC" \
  -t 4 -vn -map 0:a:0 -ac 1 -ar 16000 work/qa/opening.wav
ffmpeg -hide_banner -y -ss "$CANDIDATE_START" -i "$SRC" \
  -frames:v 1 work/qa/opening.jpg
```

For the end, start from `recommended.end_time` in `work/trim_points.json`, then stop after the final intended sentence and leave only natural completion, usually 0.3-1.0s, unless the user asked for a looser ending.

### 5. Build Subtitles

Before writing `corrections.json`, compare ASR against the selected reference candidate:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/compare_asr_reference.py \
  --asr-json work/asr/source_asr.json \
  --reference-json work/reference_candidates.json \
  --out work/asr/asr_reference_review.json
```

Use `work/asr/asr_reference_review.json` to write targeted `corrections.json` for obvious ASR term/name/number mistakes. Do not force subtitles to exactly equal the reference script; final subtitles must match retained audio.

Use `scripts/build_subtitles.py` to convert ASR JSON into corrected ASS/SRT after choosing `--start-offset` and `--end-time`.

Default subtitle style:

- Use `scripts/render_subtitle_png_filter.py --preset va7-e3-single-line-highlight` unless the user explicitly asks for a plainer style.
- This preset is the accepted E3 style from 0612 Token消耗: one subtitle line at a time, larger white text, compact dark rounded backing box, black edge for compression resistance, and yellow highlights for key terms.
- The script must split original multi-line ASS events into sequential single-line events. At any timestamp, the rendered subtitle image must contain at most one visible subtitle line.
- Default highlighted terms include `10 亿`, `10亿`, `Token`, `token`, `AI`, `Agent`, `agent`, `Vibe Coding`, and `SOP`.
- Do not manually emulate this style with ad hoc ASS settings. Use the script preset so the single-line timing, box size, and highlight behavior are deterministic.
- For a plainer legacy style, use `--preset classic`; do not use it by default when the user reports subtitles are hard to read.
- wrap long Chinese lines into two balanced lines, protecting English phrases

Example:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/build_subtitles.py \
  --asr-json work/asr/source_asr.json \
  --out-ass work/asr/corrected.ass \
  --out-srt work/asr/corrected.srt \
  --start-offset 2.12 \
  --end-time 172.37 \
  --corrections-json work/asr/corrections.json
```

`corrections.json` may contain:

```json
{
  "segment_corrections": {"17": "你买了多少英伟达"},
  "replacements": {"英文达": "英伟达", "Altropic": "Anthropic"},
  "protected_phrases": ["AI", "All in", "catch up", "bootstrap", "Anthropic"]
}
```

### 6. Render

For iPhone HDR MOV, avoid burning ASS directly if the renderer damages color or subtitle styling. Prefer the transparent-PNG overlay method:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/render_subtitle_png_filter.py \
  --ass work/asr/corrected.ass \
  --out-dir work/subtitle_png \
  --filter-out work/subtitle_overlay_filter.txt \
  --width 3840 --height 2160 \
  --preset va7-e3-single-line-highlight
```

Then render from the source with a single final encode. Use hardware HEVC for iPhone HDR sources unless there is a reason to change codec:

```bash
SOURCE_DIR="$(dirname "$SRC")"
SOURCE_STEM="$(basename "$SRC" .MOV)"
OUT="$SOURCE_DIR/${SOURCE_STEM}_口播剪辑_字幕.MOV"

ffmpeg -y -ss "$START_OFFSET" -i "$SRC" \
  -filter_complex_script work/subtitle_overlay_filter.txt \
  -map "[vout]" -map 0:a:0? \
  -c:v hevc_videotoolbox -profile:v main10 -pix_fmt yuv420p10le \
  -color_primaries bt2020 -color_trc arib-std-b67 -colorspace bt2020nc \
  -b:v "$SOURCE_LIKE_BITRATE" -tag:v hvc1 \
  -c:a copy -map_metadata 0 -movflags use_metadata_tags \
  -t "$DURATION" "$OUT"
```

Do not copy iPhone data streams into the subtitle render unless explicitly needed; mapping only `[vout]` and `0:a:0?` is usually cleaner and faster. Preserve global metadata with `-map_metadata 0`.

After rendering, run the metadata-preservation script. This is the default fix-up step for iPhone MOV outputs:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/preserve_iphone_metadata.py \
  --source-metadata-video "$SRC" \
  --target-video "$OUT" \
  --in-place \
  --backup-path "${OUT%.MOV}.backup_before_metadata_fix.MOV" \
  --json-out work/qa/metadata_preservation.json \
  --pretty
```

Behavior:

- On macOS, when the source has Apple `mebx` metadata tracks, the script uses AVFoundation passthrough remux to combine the rendered video's A/V tracks with the source metadata tracks, then overlays writable tags from the source with ExifTool.
- On non-macOS hosts or when the source lacks iPhone metadata tracks, the script falls back to ExifTool-only metadata copying.
- The script validates both ExifTool-visible tags and macOS Spotlight/Finder-visible fields such as latitude, longitude, `EncodingApplications`, and `Timed Metadata`.

Prefer this scripted route over ad hoc one-off `ffmpeg` remuxes when the user asks to "cover/迁移/保留" original iPhone metadata.

If copying iPhone data streams creates `overread end of atom 'stsd'` warnings, make a clean remux with only video/audio while preserving global tags:

```bash
FINAL="$SOURCE_DIR/${SOURCE_STEM}_口播剪辑_字幕_clean.MOV"
ffmpeg -y -i "$OUT" \
  -map 0:v:0 -map 0:a:0? -c copy -map_metadata 0 -movflags use_metadata_tags \
  "$FINAL"
```

Before delivery, normalize口播 loudness. Default target is `-16 LUFS` integrated loudness, `-2.5 dBTP` true peak, and `LRA 7`; the extra true-peak headroom avoids AAC inter-sample peaks after encoding. The pass band is `-18` to `-14 LUFS` with true peak at or below `-1.0 dBTP`. Use the script so the video stream is copied and only audio is re-encoded:

```bash
LOUD_FINAL="$SOURCE_DIR/${SOURCE_STEM}_口播剪辑_字幕_响度标准化.MOV"
python3 <skills_root>/va7-monologue-video-editor/scripts/normalize_audio_loudness.py \
  --input "$FINAL" \
  --output "$LOUD_FINAL" \
  --metadata-source-video "$SRC" \
  --preserve-finder-metadata \
  --overwrite
FINAL="$LOUD_FINAL"
```

The loudness report is written under `<source folder>/audio/` as `*_loudness_report.json`. Do not deliver a video whose report has `passed_after: false` unless the user explicitly accepts the lower/louder level.

When `--preserve-finder-metadata` is enabled, the loudness script will run the metadata-preservation workflow after audio normalization so the final deliverable does not lose Finder/Spotlight-visible iPhone metadata during the audio re-encode step.

See `references/ffmpeg-and-qa.md` for command variants and QA snippets.

### 7. QA Before Delivery

Always run deterministic QA before sending:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/qa_final_video.py \
  --final "$FINAL" \
  --source "$SRC" \
  --expected-start "$START_OFFSET" \
  --expected-end "$END_TIME" \
  --out work/qa/final_video_qa.json
```

Then inspect before sending:

- start: first audible content is the intended first line, with no fake laugh/sigh
- mid/end frames: subtitle size, single-line timing, compact backing box, keyword highlights, no clipping/overlap
- subtitles: every retained spoken unit has matching subtitle coverage
- ffprobe: resolution, frame rate, HDR tags, audio, duration
- loudness: integrated loudness in the `-18` to `-14 LUFS`口播 range, true peak no higher than `-1.0 dBTP`
- exiftool if available: make/model/software/creation date/GPS still present
- on macOS when the source had Finder-visible iPhone metadata: `mdimport`/Spotlight still reports latitude, longitude, `EncodingApplications`, and `Timed Metadata`
- decode check: at least one frame and first few seconds decode without failure
- subtitle archive: `<source folder>/subtitles/` contains timestamped ASR JSON plus SRT/TSV transcript files and a manifest/README

Use local preview images or video playback, then summarize what was checked.

### 8. Archive Timestamped Transcripts

Before final response, run the archive script. Do not manually create or rename the archive files:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/archive_subtitle_artifacts.py \
  --source-video "$SRC" \
  --final-video "$FINAL" \
  --asr-json work/asr/source_asr.json \
  --asr-label mlx_small \
  --edited-srt work/asr/corrected.srt \
  --edited-ass work/asr/corrected.ass \
  --edited-quality corrected \
  --edited-time-axis confirmed \
  --start-offset "$START_OFFSET" \
  --end-time-source "$END_TIME"
```

For ASR-only or draft edits with an inferred trim point, archive explicitly as rough/estimated:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/archive_subtitle_artifacts.py \
  --source-video "$SRC" \
  --final-video "$FINAL" \
  --asr-json work/asr/source_asr.json \
  --asr-label mlx_small \
  --edited-quality rough_asr \
  --edited-time-axis estimated \
  --estimate-start-offset-from-duration-delta \
  --note "rough ASR; trim inferred from source/final duration"
```

The script generates/copies all standard outputs in `<source folder>/subtitles/`: ASR JSON, source-relative rough SRT/TSV/TXT, edited-relative SRT/TSV/TXT/ASS when available, manifest, and README. The manifest's `chapter_generation.preferred_tsv` is the canonical input for later chapter/segment generation without reopening the Codex workspace.

### 9. Parallel Cover Handoff

If `va7-video-cover-maker` is also requested, start cheap cover preflight in parallel with ASR/render:

- extract low-res candidate contact sheets from the same source
- avoid waiting for final video render to pick frames
- use `work/reference_candidates.json` from `scripts/find_reference_script.py` to propose cover copy; if no eligible reference row exists, use rough ASR only as a clearly labeled fallback and ask for copy confirmation before final covers

Do not block the video edit on cover approval unless the user asked for one combined deliverable.

### 10. Feishu Delivery

For files larger than IM limits, upload with Feishu Drive and send the link:

```bash
cd "$SOURCE_DIR"
/opt/homebrew/bin/lark-cli drive +upload --as user --file "$FINAL" --name "$(basename "$FINAL")"
/opt/homebrew/bin/lark-cli im +messages-send --as bot --user-id "$VA7_OPEN_ID" --text "口播视频已剪好：<link>"
```

If the open_id is unknown, discover it from previous successful lark-cli messages or contacts instead of guessing.

## Guardrails

- Do not restructure a one-take口播 unless explicitly asked.
- Do not cut internal pauses aggressively; keep natural speaking rhythm.
- Do not use summary subtitles; subtitles must follow audio.
- Use `render_subtitle_png_filter.py --preset va7-e3-single-line-highlight` for readable default subtitles. If using any custom style, still preserve the one-visible-line rule unless the user explicitly asks for multi-line subtitles.
- Do not discard HDR/color metadata accidentally.
- Do not treat `ffmpeg -map_metadata 0` as a complete iPhone MOV metadata preservation strategy on macOS. When Finder-visible metadata matters, run `scripts/preserve_iphone_metadata.py`.
- Do not save the only final deliverable outside the source folder.
- Do not leave the only timestamped ASR/subtitle files in the Codex workspace; archive them under `<source folder>/subtitles/`.
- Do not deliver before doing visual and ffprobe QA.

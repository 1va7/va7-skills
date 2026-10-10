# Chapter Format

Use this reference when a platform requires manual video chapters.

## Required User-Facing Format

Return chapters as plain text, one block per chapter:

```text
【章节标题】
00:01-00:56
章节内容
```

No bullets, no markdown table, no extra labels.

## Constraints

- Chapter title: <= 14 characters. Chinese characters count as one character.
- Chapter content: <= 20 characters.
- Chapter count: <= video duration in minutes rounded up. A 2m30s video allows at most 3 chapters.
- Time range: `MM:SS-MM:SS` or `HH:MM:SS-HH:MM:SS`.
- Chapters must be sequential and non-overlapping.
- Start time should reflect the actual edited video. If the editor trimmed the first 2.12 seconds, convert ASR timestamps to the final-video timeline.

## Timestamp Sources

Use real timing evidence in this priority order:

1. Final corrected SRT from `va7-monologue-video-editor`, usually `work/asr/corrected.srt`.
2. Corrected ASR JSON with segment timestamps, usually `work/asr/source_asr.json` plus trim offset / `work/trim_points.json`.
3. Final edited video plus subtitle files in the source folder.
4. User-provided time ranges.

If no timestamp source is available, ask the user for the SRT, ASR JSON, edited video timing, or permission to run the subtitle/video workflow. Do not infer exact timestamps from the script alone.

## How To Draft

1. Read the口播终稿 to identify 3-6 logical sections.
2. Compute the maximum chapter count as `ceil(video_duration_seconds / 60)`.
3. Merge logical sections until the chapter count fits the maximum.
4. Align section boundaries to ASR/SRT segment starts and ends.
5. Keep chapter starts on the first sentence of the section, not mid-sentence.
6. Keep chapter ends at the last sentence before the next section.
7. Round timestamps to whole seconds after converting to final-video time.
8. Draft concise title/content pairs.
9. Show the plain-text chapter blocks to the user for approval before syncing.

## Examples

```text
【成本问题】
00:01-00:34
老板最关心token账单

【三类账单】
00:35-01:42
不同AI深度对应消耗

【判断标准】
01:43-02:31
看token是否换来产出
```

# FFmpeg and QA Notes

## Source Probe

```bash
ffprobe -hide_banner -v error \
  -show_entries format=duration,size:format_tags:stream=index,codec_type,codec_name,width,height,r_frame_rate,pix_fmt,color_space,color_transfer,color_primaries,bit_rate \
  -of json "$SRC"
```

```bash
exiftool -a -G1 -s -Make -Model -Software -CreateDate -CreationDate -GPSPosition -GPSCoordinates "$SRC"
```

For macOS Finder-visible iPhone metadata behavior, also inspect Spotlight/CoreMedia import output:

```bash
mdimport -d2 -n "$SRC"
```

## Opening and Ending Checks

Prefer the scripted trim gate first:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/suggest_trim_points.py \
  --src "$SRC" --asr-json work/asr/source_asr.json --out work/trim_points.json
```

Then inspect the recommended points manually:

```bash
ffmpeg -hide_banner -i "$SRC" -af silencedetect=noise=-35dB:d=0.08 -t 8 -f null -
ffmpeg -hide_banner -y -ss "$START" -i "$SRC" -t 4 -vn -ac 1 -ar 16000 work/qa/start.wav
ffmpeg -hide_banner -y -ss "$START" -i "$SRC" -frames:v 1 work/qa/start.jpg
ffmpeg -hide_banner -y -ss "$END_MINUS_2" -i "$SRC" -frames:v 1 work/qa/end.jpg
```

Choose a start that begins on the first intended word, even if that means cutting closer than the first ASR segment boundary.

## Final Render Template

Set `DURATION = END_TIME - START_OFFSET`.
Final videos must be saved beside the source MOV, not only under the Codex workspace.

```bash
SOURCE_DIR="$(dirname "$SRC")"
SOURCE_STEM="$(basename "$SRC" .MOV)"
OUT="$SOURCE_DIR/${SOURCE_STEM}_口播剪辑_字幕.MOV"

ffmpeg -hide_banner -y -ss "$START_OFFSET" -i "$SRC" \
  -filter_complex_script work/subtitle_overlay_filter.txt \
  -map "[vout]" -map 0:a:0? \
  -c:v hevc_videotoolbox -profile:v main10 -pix_fmt yuv420p10le \
  -b:v "$BITRATE" -tag:v hvc1 \
  -c:a copy -map_metadata 0 -movflags use_metadata_tags \
  -t "$DURATION" "$OUT"
```

Use source-like bitrate when preserving quality is more important than file size. For a 4K60 iPhone HDR clip, `40M`-`55M` is usually reasonable if the source is in that range.

## Clean Remux

Use this when copied iPhone metadata/data streams make tools warn about malformed atoms:

```bash
FINAL="$SOURCE_DIR/${SOURCE_STEM}_口播剪辑_字幕_clean.MOV"
ffmpeg -hide_banner -y -i "$OUT" \
  -map 0:v:0 -map 0:a:0? -c copy -map_metadata 0 -movflags use_metadata_tags \
  "$FINAL"
```

This does not re-encode video or audio. It keeps global QuickTime tags but omits extra data streams.

For iPhone MOV workflows on macOS, this clean remux is not the end of metadata preservation. If Finder-visible GPS / `Encoding Software` / `Timed Metadata` matter, follow with:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/preserve_iphone_metadata.py \
  --source-metadata-video "$SRC" \
  --target-video "$FINAL" \
  --in-place \
  --backup-path "${FINAL%.MOV}.backup_before_metadata_fix.MOV" \
  --json-out work/qa/metadata_preservation.json \
  --pretty
```

## QA Gate

Run the scripted checks:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/qa_final_video.py \
  --final "$FINAL" --source "$SRC" \
  --expected-start "$START_OFFSET" --expected-end "$END_TIME" \
  --out work/qa/final_video_qa.json
```

Then use the extracted frames and audio preview for visual/manual checks:

```bash
ffprobe -hide_banner -v error \
  -show_entries format=duration,size:format_tags:stream=index,codec_type,codec_name,width,height,r_frame_rate,pix_fmt,color_space,color_transfer,color_primaries \
  -of json "$FINAL"

ffmpeg -hide_banner -v error -y -ss 0.3 -i "$FINAL" -frames:v 1 work/qa/final_start.jpg
ffmpeg -hide_banner -v error -y -ss "$MID" -i "$FINAL" -frames:v 1 work/qa/final_mid.jpg
ffmpeg -hide_banner -v error -y -ss "$END_MINUS_2" -i "$FINAL" -frames:v 1 work/qa/final_end.jpg
ffmpeg -hide_banner -v error -i "$FINAL" -map 0:v:0 -frames:v 1 -f null -
```

Confirm:

- no fake laugh/sigh at the start
- subtitles are readable but not heavy: white text, 1-2px light-gray outline on 4K
- no black outline or dark box unless requested
- no subtitle clipping at bottom
- metadata and HDR tags are still present
- on macOS when the source is an iPhone MOV: Finder/Spotlight still reads latitude, longitude, `EncodingApplications`, and `Timed Metadata`

> 本文件的 HDR/SDR 内容只适用于封面 skill 的 video_frame（从视频抽帧）分支。用户直接给图（direct_image）时不做任何色彩判断和处理，原图就是最终底图。

# Frame Extraction Performance Notes

Use this reference for long VA7口播 videos, remote hosts, Linux servers, or any case where extracting cover frames from 4K HDR footage is slow or color-sensitive.

## Capability Probe

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/preflight_media_pipeline.py \
  --src "$SRC" --pretty
uname -a
ffmpeg -hide_banner -hwaccels
ffmpeg -hide_banner -filters | rg 'zscale|colorspace|tonemap|scale' || true
ffmpeg -hide_banner -encoders | rg 'videotoolbox|nvenc|qsv|vaapi|mjpeg|png' || true
fc-match 'Noto Sans CJK SC' 2>/dev/null || true
```

On macOS, prefer PingFang/Hiragino fonts for final typography. On Linux, use Noto Sans CJK SC or another installed CJK bold font; verify with `fc-match`.

## Fast Candidate Strategy

Use a two-pass frame workflow:

1. **Low-res scan**: create candidate/contact sheets cheaply.
2. **Shortlist**: inspect face/expression/negative space and choose timestamps.
3. **Full-res extraction**: extract only shortlisted frames with the verified color pipeline.
4. **Design**: crop and typeset from the selected full-res still.

Avoid extracting dozens of 3840x2160 frames up front.

Prefer the bundled script:

```bash
python3 <skills_root>/va7-cover-tools/scripts/extract_candidates.py \
  --src "$SRC" --count 24 --mode sdr --workers 4
```

It writes to `<source folder>/cover/candidates/`, so review artifacts stay with the original material.

## Long Video Sampling

For videos under 8 minutes, sample every 5-10 seconds:

```bash
ffmpeg -hide_banner -y -i "$SRC" \
  -vf "fps=1/8,scale=480:-1,tile=5x5" \
  -frames:v 1 "$(dirname "$SRC")/cover/candidates/contact_rough.jpg"
```

For longer videos, split the timeline and run timestamp grabs in parallel:

```bash
ffmpeg -hide_banner -y -ss 45 -i "$SRC" -frames:v 1 -vf "scale=960:-1" "$(dirname "$SRC")/cover/candidates/t045.jpg"
ffmpeg -hide_banner -y -ss 90 -i "$SRC" -frames:v 1 -vf "scale=960:-1" "$(dirname "$SRC")/cover/candidates/t090.jpg"
ffmpeg -hide_banner -y -ss 135 -i "$SRC" -frames:v 1 -vf "scale=960:-1" "$(dirname "$SRC")/cover/candidates/t135.jpg"
```

Use `-ss` before `-i` for speed. For exact final stills, re-extract the selected timestamp with `-ss` after `-i` only if frame precision matters more than speed.

Do not run a full-resolution scan over the whole file unless the contact sheet is unusable. For a long film, increase `--count` before increasing frame width.

## HDR/SDR Handling

iPhone HDR/HLG frames can look washed out when extracted raw. Treat raw HDR grabs as diagnostic images only, not final cover bases.

On macOS, prefer AVFoundation for selected full-resolution stills because it uses the same platform color-management path users see in QuickTime/Photos:

```bash
swift <skills_root>/va7-cover-tools/scripts/extract_avfoundation_frame.swift \
  "$SRC" "$TS" "$(dirname "$SRC")/cover/candidates/selected_${TS}_avfoundation_sdr.jpg" 3840
```

For candidate sheets, use the bundled script first:

```bash
python3 <skills_root>/va7-cover-tools/scripts/extract_candidates.py \
  --src "$SRC" --count 24 --mode sdr --workers 4
```

The script detects HLG/HDR metadata and should prefer AVFoundation on macOS, then `zscale` where available. It should not silently fall back to raw HDR for SDR candidates unless `--allow-raw-fallback` is explicitly used for diagnostics.

Compare at least one raw and one SDR-managed sample before designing:

```bash
ffmpeg -hide_banner -y -ss "$TS" -i "$SRC" -frames:v 1 "$(dirname "$SRC")/cover/candidates/raw.jpg"

ffmpeg -hide_banner -y -ss "$TS" -i "$SRC" -frames:v 1 \
  -vf "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709:t=bt709:m=bt709:r=tv,format=yuv420p" \
  "$(dirname "$SRC")/cover/candidates/sdr.jpg"
```

If `zscale` is missing and AVFoundation is not available, stop and report that no verified SDR extraction path is available. Do not finalize from a pale gray HDR grab, and do not treat `colorspace` alone as HLG tonemapping.

## Candidate Scoring

Score candidates before presenting:

- face sharpness and eye openness
- confident or thoughtful expression
- mouth shape not awkward
- no heavy glasses glare
- clean negative space for left-side title
- enough crop room for 3:4, 4:3, and 16:9
- color/skin tone acceptable after conversion

If OpenCV/MediaPipe or another face detector is available, use it to filter obvious misses, but do not make final aesthetic decisions without a contact sheet and human approval.

## Parallelization

Safe to parallelize:

- independent timestamp frame grabs
- raw vs SDR extraction for the same shortlisted timestamps
- contact sheet creation while ASR/reference search runs

Avoid parallelizing:

- multiple full-video 4K scans during final video render
- final cover exports that write the same filenames
- heavy GPU video jobs on the same small host

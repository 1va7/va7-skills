# Performance And Routing Notes

Use this reference when a VA7口播 edit starts on a fresh machine, remote server, or any host where ASR/render choices are not already known.

## Fast Preflight

Run these in parallel with source discovery:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/preflight_media_pipeline.py \
  --src "$SRC" --pretty
uname -a
sysctl -n machdep.cpu.brand_string 2>/dev/null || true
ffmpeg -hide_banner -hwaccels
ffmpeg -hide_banner -encoders | rg 'videotoolbox|nvenc|qsv|vaapi|hevc|libx265' || true
which ffmpeg ffprobe exiftool python3 lark-cli mlx_whisper whisper-cli whisper.cpp whisper || true
```

Run `ffprobe` once and save JSON under `work/source_probe.json`. Do not repeatedly probe the same large file unless needed.

The preflight script performs a bounded search for prior ASR tools/workflows under the current workspace and `~/Documents/Codex`. Treat discovered `asr-venv/bin/mlx_whisper`, `doubao_asr.py`, or similar files as candidates. Ask before using a historical workflow if the user has not selected it for the current video.

Do not search all of `~/.codex/sessions`, all of `$HOME`, or binary media folders for ASR/reference discovery. Search targeted workspace folders, the source folder, and Feishu/base records. Large session logs can contain base64/binary payloads and will waste time/context.

## ASR Backend Routing

Prefer the fastest backend that is both configured and accurate enough for Chinese/English mixed AI口播.

| Host/backend | Use when | Notes |
| --- | --- | --- |
| Doubao ASR | Credentials/scripts are configured, network is available, or CPU-only host would be slow | Often a good speed/accuracy choice; ask before using if the user has not selected cloud ASR for this project. |
| MLX Whisper | Apple Silicon Mac with cached MLX model | Good local path. Use `small` or better for mixed Chinese/English technical terms. |
| faster-whisper CUDA | Linux/NVIDIA with CUDA packages installed | Best local server path when available. |
| whisper.cpp / CPU Whisper | No cloud/GPU route exists | Warn before long videos; use only if accepted or video is short. |

If both Doubao and local ASR are viable and the user has not already chosen a default, ask a concise question before running the full job. If speed is explicitly requested, choose the empirically fastest configured backend and report it.

## Audio-Only Operations

Use `-vn` and `-map 0:a:0` for audio analysis and extraction:

```bash
ffmpeg -hide_banner -nostats -vn -i "$SRC" -map 0:a:0 \
  -af silencedetect=noise=-35dB:d=0.08 -t 8 -f null -

ffmpeg -hide_banner -y -vn -i "$SRC" -map 0:a:0 \
  -ac 1 -ar 16000 -c:a pcm_s16le work/asr/source_16k.wav
```

Avoid commands like `ffmpeg -i "$SRC" -af ...` for silence detection because they may decode 4K video unnecessarily.

## Final Encode Routing

Subtitle burn-in requires re-encoding the video. Do it once.

| Host | Preferred encoder | Example options |
| --- | --- | --- |
| Apple Silicon Mac | `hevc_videotoolbox` | `-c:v hevc_videotoolbox -profile:v main10 -pix_fmt yuv420p10le -tag:v hvc1` |
| NVIDIA Linux | `hevc_nvenc` | `-c:v hevc_nvenc -profile:v main10 -pix_fmt p010le -tag:v hvc1` |
| Intel Linux | `hevc_qsv` or VAAPI | Confirm filters/pixel format with a 5s smoke test first. |
| CPU only | `libx265` | Slow for 4K60; ask before full render. |

For iPhone HDR/HLG sources, carry color tags in the output when supported:

```bash
-color_primaries bt2020 -color_trc arib-std-b67 -colorspace bt2020nc
```

Use a 5-second smoke test whenever changing host/encoder/filter chain:

```bash
ffmpeg -hide_banner -y -ss "$START_OFFSET" -i "$SRC" \
  -filter_complex_script work/subtitle_overlay_filter.txt \
  -map "[vout]" -map 0:a:0? -t 5 \
  <encoder options> -c:a copy work/qa/render_smoke.mov
```

Probe and visually inspect the smoke test before launching the full render.

## Parallelization Pattern

After locating the source, run independent work concurrently:

- `ffprobe` + `exiftool`
- reference search in Feishu/base
- ASR tool/credential detection
- audio extraction for ASR
- cover candidate low-res extraction if the cover skill is active
- head/tail audio silence scans

Do not parallelize multiple full 4K encodes on the same host; they compete for the same encoder/GPU and slow each other down.

## Reference Script Gate

For VA7 monologues, reference稿件 is quality-critical because ASR often mangles English terms, model names, and numbers. Never use local cache, finished-content exports, or broad keyword search as the authoritative source.

Run the deterministic Feishu `选题库` gate first:

```bash
python3 <skills_root>/va7-monologue-video-editor/scripts/find_reference_script.py \
  --source-path "$SRC" \
  --asr-json work/asr/source_asr.json \
  --top 5 --include-script \
  --out work/reference_candidates.json
```

The script filters to records where `待做` is checked, `发布排期` is not empty, and `口播终稿` is not empty. If no exact match is found:

1. Present the script's top candidates and confidence.
2. Ask the user which candidate is correct, or ask for permission to proceed ASR-only if the script returns none.
3. Continue final subtitle correction only after user confirmation, unless the user explicitly approves ASR-only correction.

---
name: youtube-bilibili-localizer
description: Localize YouTube or local videos into Simplified Chinese subtitles or Mandarin dubbing and publish the result to Bilibili. Use when Codex needs to take a video link or local MP4, generate Chinese or bilingual subtitles, optionally synthesize Mandarin dubbing, translate the source title into Chinese with a 【中文字幕】 prefix, prepare Bilibili metadata, and optionally upload with biliup.
---

# YouTube Bilibili Localizer

## Overview

Use this skill when the user wants a full YouTube-to-Bilibili workflow:

- download a supported video URL or ingest a local video
- transcribe speech into timestamped segments with `faster-whisper`
- translate subtitles into Simplified Chinese
- keep bilingual subtitles by default: Chinese on top, source text below
- optionally synthesize Mandarin dubbing
- translate the source title into Chinese and prefix it with `【中文字幕】`
- prepare Bilibili metadata and optionally upload with `biliup`

Default behavior:

- subtitle layout: `bilingual`
- translation mode: `api`
- Bilibili copyright: `1` (`self-made/original`)

Offline translation is supported for `en -> zh`. The first offline run may download the Argos language package.

## Workflow

1. Confirm the input and mode.

Accept:

- a YouTube URL or another `yt-dlp`-supported URL
- a local video file
- a pre-existing transcript JSON with timestamps

Choose:

- `subtitles`: subtitles only
- `dub`: subtitles plus Mandarin dubbing

2. Read [references/runtime-and-publishing.md](references/runtime-and-publishing.md) when setting up the machine, checking credentials, or debugging upload/runtime problems.

3. Run the publisher entry point:

```bash
scripts/run_publish_localized_video.sh \
  --input "https://www.youtube.com/watch?v=..." \
  --workdir ./runs/demo \
  --mode subtitles \
  --translation-mode offline \
  --subtitle-layout bilingual \
  --dry-run
```

4. Review outputs in the work directory before uploading.

Check:

- `metadata.source.json`
- `translated_segments.json`
- `subtitles.zh.srt`
- `publish_metadata.json`
- `final.mp4` when dubbing or hard-sub export is enabled

5. Upload only after explicit user approval or a direct request to publish.

## Decision Rules

Prefer this order:

1. Use `--translated-title` when the user already approved a Chinese title.
2. Use `--transcript-json` when timestamps already exist.
3. Use `offline` translation only for English-source content.
4. Keep bilingual subtitles when using offline translation unless the user explicitly asks for Chinese-only.
5. Default Bilibili submission type to `1` when the uploader has creator permission.
6. Switch to `2` only for explicit repost submissions.

## Failure Handling

- If `yt-dlp` is blocked, retry with `--cookies /path/to/cookies.txt` or `--cookies-from-browser edge`.
- If `faster-whisper` is unavailable, require `--transcript-json`.
- If Volcengine translation credentials are missing in `api` or `auto` mode, the workflow can fall back to offline `en -> zh`.
- If offline translation is requested for a non-English or unknown source, stop and ask for `--source-language en` or a different mode.
- If TTS credentials are missing, rerun with `--mode subtitles` or `--skip-upload`.
- If `biliup` upload fails, keep `publish_metadata.json` and the generated command for retry instead of discarding the localized outputs.

## Resources

- [scripts/publish_localized_video.py](scripts/publish_localized_video.py): main entry point for localization, metadata generation, and Bilibili upload
- [scripts/localize_video.py](scripts/localize_video.py): download, ASR, subtitle translation, dubbing, and export pipeline
- [scripts/run_publish_localized_video.sh](scripts/run_publish_localized_video.sh): shell wrapper that prefers the local `.venv`
- [references/runtime-and-publishing.md](references/runtime-and-publishing.md): setup notes, environment variables, and troubleshooting

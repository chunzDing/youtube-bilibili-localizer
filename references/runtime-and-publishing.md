# Runtime And Publishing

## Required Tools

- `ffmpeg`
- `ffprobe`

## Optional but Recommended Tools

- `yt-dlp`: download online inputs and fetch source metadata
- `faster-whisper`: local speech-to-text with timestamps
- `biliup`: automated Bilibili uploads
- `argostranslate`: offline subtitle and title translation for `en -> zh`
- `nvidia-cublas-cu12`: required on Windows when running `faster-whisper` on CUDA

## Python Dependencies

Install:

```bash
pip install -r requirements.txt
```

This repository expects the Python environment to contain:

- `faster-whisper`
- `argostranslate`
- `volcengine-python-sdk`

## Environment Variables

Translation and title translation:

- `VOLCENGINE_ACCESS_KEY`
- `VOLCENGINE_SECRET_KEY`
- `VOLCENGINE_REGION` default: `cn-north-1`

Mandarin dubbing:

- `VOLCENGINE_TTS_API_KEY`
- `VOLCENGINE_TTS_RESOURCE_ID` default: `volc.service_type.10029`

Uploading:

- `BILIUP_BIN` optional path or command name, default `biliup`
- `BILIUP_COOKIE` optional cookie/session file for `biliup`

## Translation Modes

- `api`: use Volcengine translation
- `offline`: use Argos Translate for `en -> zh`
- `auto`: try API first, then fall back to offline

Offline mode constraints:

- first offline run may download the Argos `en -> zh` package
- after the package is installed, later offline runs can stay local
- offline mode currently supports only English-source content

## Subtitle Layout

- `bilingual`: Chinese on the first line, source text on the second line
- `zh`: Chinese only

Default layout is `bilingual`.

## Bilibili Defaults

- title prefix: `【中文字幕】`
- default mode: `dub`
- default tags: `中文字幕,翻译,搬运`
- default copyright: `1`
- add `--source` only for repost submissions (`copyright=2`)

## Recommended Commands

Subtitles only:

```bash
scripts/run_publish_localized_video.sh \
  --input "https://www.youtube.com/watch?v=..." \
  --workdir ./runs/demo \
  --mode subtitles \
  --translation-mode offline \
  --subtitle-layout bilingual \
  --dry-run
```

Dub plus upload:

```bash
scripts/run_publish_localized_video.sh \
  --input "https://www.youtube.com/watch?v=..." \
  --workdir ./runs/demo \
  --mode dub \
  --translation-mode auto \
  --tid 171
```

## Common Failure Modes

### Missing `yt-dlp`

Install `yt-dlp` or pass a local file instead of a URL.

### YouTube Bot Check

Retry with:

- `--cookies /path/to/cookies.txt`
- or `--cookies-from-browser edge`

### Missing `faster-whisper`

Install it or pass `--transcript-json`.

### Missing CUDA DLLs on Windows

Install `nvidia-cublas-cu12` in the active environment. The localizer adds the package DLL path to `PATH` automatically.

### Missing Volcengine Credentials

- subtitle/title translation in `api` or `auto` mode may fall back to offline `en -> zh`
- TTS requires `VOLCENGINE_TTS_API_KEY`

### Offline Translation Fails

Pass `--source-language en` for English content, or switch back to `api` / `auto`.

### `biliup` Upload Fails

Keep `publish_metadata.json` and rerun the generated command after fixing login or CLI options.

# YouTube Bilibili Localizer

中文说明 / English documentation

## 简介

这是一个可独立分发的 Codex skill 仓库，用来把 YouTube 或本地视频汉化后发布到 Bilibili。

它把原先分散的“视频本地化”和“Bilibili 投稿”能力收拢成一个 skill，支持：

- 下载 YouTube 视频或读取本地视频
- 使用 `faster-whisper` 生成时间轴字幕
- 生成中文字幕
- 默认生成中英双语字幕
- 可选普通话配音
- 把原标题翻译成中文，并自动加上 `【中文字幕】` 前缀
- 生成投稿元数据并可用 `biliup` 自动投稿到 Bilibili

## Overview

This repository packages a standalone Codex skill for localizing YouTube or local videos into Chinese and publishing them to Bilibili.

It combines the localization and publishing workflow into one skill and supports:

- downloading YouTube videos or ingesting local files
- generating timestamped transcripts with `faster-whisper`
- creating Chinese subtitles
- generating bilingual subtitles by default
- optional Mandarin dubbing
- translating the source title into Chinese with the `【中文字幕】` prefix
- preparing Bilibili metadata and optionally uploading with `biliup`

## Repository Layout

- `SKILL.md`: Codex skill entry
- `agents/openai.yaml`: skill UI metadata
- `scripts/localize_video.py`: download, ASR, translation, dubbing, export
- `scripts/publish_localized_video.py`: title translation, metadata generation, optional Bilibili upload
- `scripts/run_localize_video.sh`: localizer launcher
- `scripts/run_publish_localized_video.sh`: publisher launcher
- `references/runtime-and-publishing.md`: setup notes and troubleshooting
- `requirements.txt`: Python dependencies for the local pipeline

## 安装

### 作为 GitHub 仓库使用

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

额外准备：

- `ffmpeg`
- `ffprobe`
- `yt-dlp`
- `biliup`（如果需要自动投稿）

### 作为 Codex skill 使用

把这个仓库放到你的 skill 目录下，例如：

- Windows: `%USERPROFILE%\\.codex\\skills\\youtube-bilibili-localizer`
- macOS / Linux: `${CODEX_HOME:-$HOME/.codex}/skills/youtube-bilibili-localizer`

## Installation

### Use as a GitHub repository

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Also install:

- `ffmpeg`
- `ffprobe`
- `yt-dlp`
- `biliup` if you want automated uploads

### Use as a Codex skill

Place the repository under your Codex skills directory, for example:

- Windows: `%USERPROFILE%\\.codex\\skills\\youtube-bilibili-localizer`
- macOS / Linux: `${CODEX_HOME:-$HOME/.codex}/skills/youtube-bilibili-localizer`

## 环境变量

复制 `.env.example` 为 `.env.local` 或手动设置环境变量：

- `VOLCENGINE_ACCESS_KEY`
- `VOLCENGINE_SECRET_KEY`
- `VOLCENGINE_REGION`
- `VOLCENGINE_TTS_API_KEY`
- `VOLCENGINE_TTS_RESOURCE_ID`
- `BILIUP_BIN`
- `BILIUP_COOKIE`

离线翻译模式下，字幕和标题默认使用本地 Argos Translate；首次运行可能会联网下载 `en -> zh` 语言包。

## Environment Variables

Copy `.env.example` to `.env.local` or export the variables manually:

- `VOLCENGINE_ACCESS_KEY`
- `VOLCENGINE_SECRET_KEY`
- `VOLCENGINE_REGION`
- `VOLCENGINE_TTS_API_KEY`
- `VOLCENGINE_TTS_RESOURCE_ID`
- `BILIUP_BIN`
- `BILIUP_COOKIE`

In offline mode, subtitles and title translation use local Argos Translate. The first run may download the `en -> zh` language package.

## Usage

Subtitles only, offline translation, bilingual subtitles:

```bash
scripts/run_publish_localized_video.sh \
  --input "https://www.youtube.com/watch?v=VIDEO_ID" \
  --workdir ./runs/demo \
  --mode subtitles \
  --translation-mode offline \
  --subtitle-layout bilingual \
  --dry-run
```

Full localization plus upload:

```bash
scripts/run_publish_localized_video.sh \
  --input "https://www.youtube.com/watch?v=VIDEO_ID" \
  --workdir ./runs/demo \
  --mode dub \
  --translation-mode auto \
  --tags "中文字幕,翻译,搬运" \
  --tid 171
```

## 投稿规则 / Publishing Notes

- 默认标题格式：`【中文字幕】` + 汉化后的原标题
- 默认字幕布局：上中文，下原文
- 默认投稿类型：`自制 / original`
- 仅在明确转载场景下切换为 `转载 / repost`

## Attribution / 致谢

本项目基于以下仓库进行二次开发：

- [jiayuqi7813/video-Zebra-china](https://github.com/jiayuqi7813/video-Zebra-china)

当前仓库在原项目基础上进行了结构重组，并增加了：

- 单 skill 仓库结构
- 离线字幕与标题翻译模式
- 双语字幕默认布局
- Bilibili 投稿工作流
- Windows CUDA 运行兼容修复
- `自制 / original` 默认投稿类型

This project is based on and adapted from:

- [jiayuqi7813/video-Zebra-china](https://github.com/jiayuqi7813/video-Zebra-china)

This repository restructures the workflow into a single skill and adds:

- a standalone skill repository layout
- offline subtitle and title translation
- bilingual subtitles by default
- Bilibili publishing workflow
- Windows CUDA compatibility fixes
- `original/self-made` as the default submission type

## 授权提醒 / License Note

截至 2026-05-05，我检查上游仓库页面时，没有看到明确的 `LICENSE` 文件。

这意味着：

- 标注来源是必要的
- 但标注来源本身不等于获得代码再分发许可
- 如果本仓库包含来自上游的复制或改写代码，公开发布前应先确认上游许可证，或取得原作者明确授权

视频作者授权你发布视频，与上游代码是否允许公开再分发，是两件独立的事情。

As of 2026-05-05, the upstream GitHub page did not show a clear `LICENSE` file.

That means:

- attribution is necessary
- attribution alone does not grant redistribution rights
- if this repository contains copied or adapted upstream code, confirm the upstream license or obtain explicit permission before making the repository public

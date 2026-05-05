# YouTube to Bilibili Chinese Localizer Wrapper

中文说明 / English documentation

## 简介

这是一个面向 Windows 的本地工作流封装，用来把 YouTube 视频处理成适合发布到 Bilibili 的中文版本。

当前仓库主要围绕两个本地 Codex skill 工作：

- `youtube-chinese-localizer`
- `bilibili-chinese-publisher`

目前支持的流程包括：

- 下载 YouTube 视频
- 使用 `faster-whisper` 生成原文转写
- 使用离线翻译生成中文字幕
- 默认生成中英双语字幕（上中文，下英文）
- 烧录字幕并导出成片
- 自动投稿到 Bilibili

## Overview

This is a Windows-oriented local workflow wrapper for turning YouTube videos into Chinese-localized versions suitable for Bilibili publishing.

It currently works on top of two local Codex skills:

- `youtube-chinese-localizer`
- `bilibili-chinese-publisher`

The workflow currently supports:

- downloading YouTube videos
- generating source-language transcripts with `faster-whisper`
- creating Chinese subtitles with offline translation
- generating bilingual subtitles by default (Chinese on top, English below)
- burning subtitles into the final video
- automatically publishing to Bilibili

## 项目结构

- `run-video-localizer.ps1`: PowerShell 入口脚本，调用本地视频汉化 skill
- `translate_transcript_to_zh.py`: 独立的离线字幕翻译脚本
- `probe-volc-tts.ps1`: 火山 TTS 配置探测入口
- `probe_volc_tts.py`: 火山 TTS 探测脚本
- `runs/`: 每次任务的输出目录
- `.env.local`: 本地环境变量文件，不应提交到 GitHub

## Project Structure

- `run-video-localizer.ps1`: PowerShell entry script for the local video localization skill
- `translate_transcript_to_zh.py`: standalone offline subtitle translation script
- `probe-volc-tts.ps1`: PowerShell entry script for Volcengine TTS probing
- `probe_volc_tts.py`: Volcengine TTS probing script
- `runs/`: output directory for each run
- `.env.local`: local environment file and should not be committed

## 运行环境

当前项目默认假设以下环境已经准备好：

- Windows
- PowerShell
- FFmpeg
- Python 3.10+
- 本地安装的 Codex skills

默认 skill 路径：

- `C:\Users\dqc\.codex\skills\youtube-chinese-localizer`
- `C:\Users\dqc\.codex\skills\bilibili-chinese-publisher`

如果你的环境不同，可以通过环境变量覆盖：

- `YCL_SKILL_ROOT`
- `YCL_PYTHON_EXE`
- `YCL_FFMPEG_BIN`

## Requirements

This project currently assumes:

- Windows
- PowerShell
- FFmpeg
- Python 3.10+
- locally installed Codex skills

Default skill paths:

- `C:\Users\dqc\.codex\skills\youtube-chinese-localizer`
- `C:\Users\dqc\.codex\skills\bilibili-chinese-publisher`

If your machine is different, you can override the defaults with:

- `YCL_SKILL_ROOT`
- `YCL_PYTHON_EXE`
- `YCL_FFMPEG_BIN`

## 快速开始

### 1. 配置环境变量

复制 `.env.example` 为 `.env.local`，再填入你自己的配置。

常见变量包括：

- `VOLCENGINE_ACCESS_KEY`
- `VOLCENGINE_SECRET_KEY`
- `VOLCENGINE_REGION`
- `VOLCENGINE_TTS_API_KEY`
- `VOLCENGINE_TTS_RESOURCE_ID`

注意：如果你准备开源这个项目，不要把真实密钥提交到 GitHub。

### 2. 运行本地视频汉化

```powershell
.\run-video-localizer.ps1 `
  -InputPath "https://www.youtube.com/watch?v=VIDEO_ID" `
  -SourceLanguage "en" `
  -SkipTts `
  -TranslationMode "offline" `
  -SubtitleLayout "bilingual" `
  -WhisperDevice "cuda" `
  -WhisperComputeType "float16"
```

### 3. 查看输出

结果通常会写入 `runs/<video-id>/`，常见文件包括：

- `source.mp4`
- `audio.wav`
- `transcript.json`
- `translated_segments.json`
- `subtitles.zh.srt`
- `final.mp4`

## Quick Start

### 1. Configure environment variables

Copy `.env.example` to `.env.local`, then fill in your own values.

Common variables include:

- `VOLCENGINE_ACCESS_KEY`
- `VOLCENGINE_SECRET_KEY`
- `VOLCENGINE_REGION`
- `VOLCENGINE_TTS_API_KEY`
- `VOLCENGINE_TTS_RESOURCE_ID`

Important: do not commit real secrets to GitHub.

### 2. Run the local video localization flow

```powershell
.\run-video-localizer.ps1 `
  -InputPath "https://www.youtube.com/watch?v=VIDEO_ID" `
  -SourceLanguage "en" `
  -SkipTts `
  -TranslationMode "offline" `
  -SubtitleLayout "bilingual" `
  -WhisperDevice "cuda" `
  -WhisperComputeType "float16"
```

### 3. Check outputs

Outputs are usually written to `runs/<video-id>/`. Common files include:

- `source.mp4`
- `audio.wav`
- `transcript.json`
- `translated_segments.json`
- `subtitles.zh.srt`
- `final.mp4`

## 双语字幕说明

当前字幕默认使用双语布局：

- 第一行：中文字幕
- 第二行：原文字幕

这样即使离线翻译质量不够理想，观众也能结合原文理解内容。

## Bilingual Subtitle Behavior

Subtitles currently default to a bilingual layout:

- first line: Chinese translation
- second line: original subtitle text

This helps viewers understand the content even when offline translation quality is imperfect.

## Bilibili 投稿说明

当前项目支持自动投稿到 Bilibili，并默认按 `自制` 处理。

这个默认值面向“已经获得原作者明确授权”的使用场景。如果你的场景属于明确转载，请在投稿时手动切换对应类型。

## Bilibili Publishing Notes

This project supports automatic Bilibili publishing and now defaults to `original/self-made` submission mode.

This default is intended for workflows where the uploader has explicit permission from the original creator. If your case is a repost, switch the submission type manually.

## 开源前注意事项

- 不要提交 `.env.local`
- 不要提交真实 API Key、Cookie、浏览器会话文件
- 不要提交 `cookies.json`、`chrome_cookies_copy.db`、`--impersonate`
- 不要提交 `runs/` 里的下载产物和成片
- 当前脚本仍然依赖本地安装的 Codex skills

## Before Open-Sourcing

- do not commit `.env.local`
- do not commit real API keys, cookies, or browser session files
- do not commit `cookies.json`, `chrome_cookies_copy.db`, or `--impersonate`
- do not commit downloaded artifacts or rendered videos under `runs/`
- the current scripts still depend on locally installed Codex skills

## 致谢 / Attribution

本项目基于以下仓库进行二次开发：

- [jiayuqi7813/video-Zebra-china](https://github.com/jiayuqi7813/video-Zebra-china)

当前仓库在原项目基础上增加或调整了：

- 离线字幕翻译工作流
- 中英双语字幕布局
- Bilibili 投稿流程改造
- Windows CUDA 运行环境修复
- 投稿默认使用 `自制`

This project is based on and adapted from:

- [jiayuqi7813/video-Zebra-china](https://github.com/jiayuqi7813/video-Zebra-china)

This repository adds or changes:

- offline subtitle translation workflow
- bilingual subtitle layout
- Bilibili publishing workflow updates
- Windows CUDA runtime fixes
- `original/self-made` as the default submission mode

## 授权提醒 / License Note

请注意：截至我整理这个仓库时，上游仓库页面没有看到明确的 `LICENSE` 文件。

这意味着：

- 标注来源是应该做的
- 但“标注来源”本身不等于获得了代码再分发许可
- 如果你的仓库包含了从上游复制或改写而来的代码，公开发布前应先确认上游许可证，或取得原作者明确授权

视频作者授权你投稿视频，与上游代码仓库是否允许再分发，是两件独立的事情。

Please note: when this repository was prepared, the upstream GitHub page did not show a clear `LICENSE` file.

That means:

- attribution is still necessary
- but attribution alone does not grant redistribution rights
- if this repository contains copied or adapted upstream code, confirm the upstream license or obtain explicit permission before making the repository public

Permission from the video creator to repost or localize the video is separate from permission to redistribute upstream source code.

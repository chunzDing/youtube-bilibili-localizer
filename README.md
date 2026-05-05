# YouTube Bilibili Localizer

把 YouTube 或本地视频汉化为中文字幕或普通话配音，并发布到 Bilibili。

这个仓库同时支持两种使用方式：

- 作为独立 Python 项目运行
- 作为 Codex skill 放进 `~/.codex/skills/` 使用

默认推荐链路：

- API 翻译优先
- `high` 翻译质量模式
- 内置术语表
- 先跑 Bilibili 登录助手，再 `--dry-run`，最后正式投稿

## 功能概览

- 下载 YouTube 视频或读取本地视频
- 使用 `faster-whisper` 生成带时间轴的转录
- 对字幕做分段优化，减少碎片化翻译
- 默认生成中英双语字幕
- 支持 Volcengine API 翻译与标题翻译
- 支持内置术语表和自定义 glossary
- 可选普通话配音
- 自动生成 `【中文字幕】` 标题
- 可选通过 `biliup` 自动投稿到 Bilibili
- 提供交互式 Bilibili 登录助手，直接产出 `biliup` 可用 cookie

## 安装

### 依赖工具

必须安装：

- `ffmpeg`
- `ffprobe`

推荐安装：

- `yt-dlp`
- `biliup`

### Python 环境

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## API 配置

复制 `.env.example` 为 `.env.local`，或在系统环境中设置这些变量：

- `VOLCENGINE_ACCESS_KEY`
  用于字幕翻译和标题翻译。
- `VOLCENGINE_SECRET_KEY`
  与 `VOLCENGINE_ACCESS_KEY` 配套使用。
- `VOLCENGINE_REGION`
  默认 `cn-north-1`。
- `VOLCENGINE_TTS_API_KEY`
  仅普通话配音需要。
- `VOLCENGINE_TTS_RESOURCE_ID`
  默认 `volc.service_type.10029`。
- `BILIUP_BIN`
  可选，自定义 `biliup` 可执行文件路径或命令名，默认 `biliup`。
- `BILIUP_COOKIE`
  可选，手动指定 `biliup` cookie 文件路径。优先级低于 `--bili-cookie`，高于默认 `.auth/bilibili.cookies.json`。

安全提醒：

- 不要把 AK/SK 提交到仓库。
- 不要把 `.auth/` 目录或任何 `cookies.json` 提交到仓库。

## Bilibili 登录

### 推荐方式：登录助手

Windows:

```powershell
.\scripts\run_biliup_login_helper.ps1 --browser edge
```

macOS / Linux:

```bash
scripts/run_biliup_login_helper.sh --browser chrome
```

行为说明：

- 会打开一个全新的浏览器窗口
- 你在窗口里完成 Bilibili 登录
- 登录助手会自动轮询登录状态
- 默认输出到 `.auth/bilibili.cookies.json`

正式投稿时，如果你没有显式传 `--bili-cookie`，程序会自动尝试使用这个默认 cookie 文件。

## 推荐首次使用流程

1. 先配置 Volcengine 环境变量。
2. 跑一次 Bilibili 登录助手。
3. 用 `--dry-run` 生成字幕、视频和投稿元数据。
4. 确认标题、字幕和元数据没问题后再正式上传。

## 字幕模式

- `--subtitle-layout bilingual`
  中文在上，原文在下。默认值。
- `--subtitle-layout zh`
  只保留中文。

## 翻译质量模式

- `--translation-quality high`
  默认推荐模式。会做字幕分段优化、术语保护和翻译后清洗，更适合教程类视频。
- `--translation-quality standard`
  更接近原始分段，处理更简单，适合快速出结果。

## 术语表

默认会自动加载：

- `references/glossary.zh.json`

如果你想覆盖或补充默认术语表，可以传：

```powershell
--glossary-file ".\my-glossary.json"
```

默认 glossary 已覆盖这类常见术语：

- `vibe coding`
- `prompt`
- `SaaS`
- `Base44`
- `landing page`
- `workflow`
- `roadblock`
- `AI agent`

## 常用命令

### 只生成中文字幕，不上传

Windows PowerShell:

```powershell
.\scripts\run_publish_localized_video.ps1 `
  --input "https://www.youtube.com/watch?v=VIDEO_ID" `
  --workdir ".\runs\demo" `
  --mode subtitles `
  --translation-mode api `
  --translation-quality high `
  --subtitle-layout bilingual `
  --dry-run
```

macOS / Linux:

```bash
scripts/run_publish_localized_video.sh \
  --input "https://www.youtube.com/watch?v=VIDEO_ID" \
  --workdir ./runs/demo \
  --mode subtitles \
  --translation-mode api \
  --translation-quality high \
  --subtitle-layout bilingual \
  --dry-run
```

### 生成普通话配音并正式投稿

```powershell
.\scripts\run_publish_localized_video.ps1 `
  --input "https://www.youtube.com/watch?v=VIDEO_ID" `
  --workdir ".\runs\demo" `
  --mode dub `
  --translation-mode auto `
  --translation-quality high `
  --tid 171
```

### 复用已有 transcript，避免重复 ASR

```powershell
.\scripts\run_localize_video.ps1 `
  --input ".\runs\demo\source.mp4" `
  --workdir ".\runs\demo-api" `
  --transcript-json ".\runs\demo\transcript.json" `
  --skip-transcription `
  --source-language en `
  --translation-mode api `
  --translation-quality high `
  --skip-tts
```

## 输出文件

工作目录中常见输出：

- `metadata.source.json`
- `transcript.json`
- `translated_segments.json`
- `subtitles.zh.srt`
- `publish_metadata.json`
- `final.mp4`

新增元数据字段：

- `translation_quality_used`
- `glossary_file_used`
- `segment_refinement_used`
- `bili_cookie_path_used`

## 常见问题

### 1. API 翻译没有生效

检查：

- `VOLCENGINE_ACCESS_KEY` 和 `VOLCENGINE_SECRET_KEY` 是否正确
- 火山翻译服务是否真的开通
- `translated_segments.json` 里的 `translation_mode_used` 是否为 `api`

### 2. 字幕中文太生硬

优先尝试：

- `--translation-mode api`
- `--translation-quality high`
- 补充 `--glossary-file`

如果视频是教程类、产品评测类、工具介绍类，`high` 模式通常会比原始逐段翻译自然很多。

### 3. Bilibili 上传提示未登录

先重新跑登录助手：

```powershell
.\scripts\run_biliup_login_helper.ps1 --browser edge
```

然后确认：

- `.auth/bilibili.cookies.json` 存在
- `publish_metadata.json` 里的 `bili_cookie_path_used` 指向的是你预期的 cookie 文件

### 4. YouTube 下载被拦

可以重试：

- `--cookies-from-browser edge`
- `--cookies path/to/cookies.txt`
- `--yt-dlp-impersonate edge:windows-10`

### 5. Windows 上 whisper/CUDA 报错

当前项目会自动补充常见 CUDA DLL 路径，但前提是依赖已经正确安装。建议确认：

- `.venv` 已重建
- `pip install -r requirements.txt` 完成
- 当前 Python 就是 skill 的 `.venv`

## 仓库结构

- `SKILL.md`
  Codex skill 入口说明。
- `scripts/localize_video.py`
  下载、转录、翻译、配音、导出主流程。
- `scripts/publish_localized_video.py`
  标题翻译、投稿元数据生成、自动上传。
- `scripts/biliup_login_helper.py`
  交互式 Bilibili 登录助手。
- `scripts/translation_utils.py`
  术语、翻译清洗和文本规范化工具。
- `scripts/bilibili_auth.py`
  `biliup` cookie 构造、验证和默认路径逻辑。
- `references/runtime-and-publishing.md`
  运行和投稿排障说明。
- `references/glossary.zh.json`
  默认术语表。
- `tests/`
  标准库 `unittest` 测试。

## 致谢

本项目基于以下仓库继续整理与扩展：

- [jiayuqi7813/video-Zebra-china](https://github.com/jiayuqi7813/video-Zebra-china)

当前仓库在此基础上重点增加了：

- 独立 skill 仓库结构
- 标题与字幕 API 翻译
- 高质量字幕分段优化
- 默认术语表
- Bilibili 登录助手
- Bilibili 投稿工作流

## 许可提醒

截至 2026-05-05，我在上游页面没有看到明确的 `LICENSE` 文件。

这意味着：

- 标注来源是必要的
- 仅标注来源并不等于获得再分发授权
- 如果这个仓库包含上游代码的复制或改写，在公开发布前请先确认上游许可，或获得原作者明确授权

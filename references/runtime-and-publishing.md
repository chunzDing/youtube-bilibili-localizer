# Runtime and Publishing

## 必需工具

- `ffmpeg`
- `ffprobe`

## 推荐工具

- `yt-dlp`
- `biliup`
- `playwright`

## Python 依赖

安装：

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

主要依赖：

- `faster-whisper`
- `argostranslate`
- `volcengine-python-sdk`
- `playwright`

## 环境变量

### 翻译和标题翻译

- `VOLCENGINE_ACCESS_KEY`
- `VOLCENGINE_SECRET_KEY`
- `VOLCENGINE_REGION`
  默认 `cn-north-1`

### 普通话配音

- `VOLCENGINE_TTS_API_KEY`
- `VOLCENGINE_TTS_RESOURCE_ID`
  默认 `volc.service_type.10029`

### 投稿

- `BILIUP_BIN`
  可选，默认 `biliup`
- `BILIUP_COOKIE`
  可选，指定 cookie 文件路径
- `BILIBILI_DEFAULT_TID`
  可选，仅在显式 `--tid` 未提供且规则分区没有命中时作为投稿分区兜底值

优先级：

1. `--bili-cookie`
2. `BILIUP_COOKIE`
3. `.auth/bilibili.cookies.json`

投稿分区优先级：

1. `--tid`
2. 规则回退
3. `BILIBILI_DEFAULT_TID`
4. `36`（知识区）

当前脚本内置规则覆盖：

- `188` 科技
- `36` 知识
- `160` 生活
- `171` 电子竞技

这些值表示“期望的大类”。真正调用 `biliup upload` 时，脚本会自动映射到可投稿的叶子分区，例如：

- `188` -> `231`（计算机技术）
- `36` -> `122`（野生技能协会）
- `160` -> `21`（日常）

简介优先级：

1. `--desc`
2. 默认简介回退

版权默认值：

- 默认 `copyright=1`
- 只有显式传 `--copyright 2` 时才按转载处理
- 只有转载时才附 `--source`

可见性默认值：

- 默认 `--is-only-self 0`
- 即直接正常投稿
- 需要先存为草稿再手动检查时，显式传 `--is-only-self 1`

## 翻译模式

- `api`
  使用 Volcengine
- `offline`
  使用 Argos Translate，仅支持 `en -> zh`
- `auto`
  先走 API，失败后自动回退到离线

发生回退时：

- 控制台会明确提示
- `translated_segments.json` 会写入 `translation_fallback_used=true`
- `translation_fallback_reason` 会记录失败原因

## 翻译质量模式

- `high`
  默认值。会做字幕分段优化、术语保护和翻译后清洗。
- `standard`
  更轻量，接近原始分段。

## 登录助手

推荐先运行：

```powershell
.\scripts\run_biliup_login_helper.ps1 --browser edge
```

或：

```bash
scripts/run_biliup_login_helper.sh --browser chrome
```

登录助手会：

- 打开全新浏览器窗口
- 自动轮询登录状态
- 导出 `biliup` 可用 cookie
- 默认写入 `.auth/bilibili.cookies.json`
- 立即调用 Bilibili 接口验证登录态

## 推荐命令

### 只做字幕

```powershell
.\scripts\run_publish_localized_video.ps1 `
  --input "https://www.youtube.com/watch?v=..." `
  --workdir ".\runs\demo" `
  --mode subtitles `
  --translation-mode api `
  --translation-quality high `
  --subtitle-layout bilingual `
  --dry-run
```

### 配音并投稿

```powershell
.\scripts\run_publish_localized_video.ps1 `
  --input "https://www.youtube.com/watch?v=..." `
  --workdir ".\runs\demo" `
  --mode dub `
  --translation-mode auto `
  --translation-quality high
```

### Codex 模式：由助手传入简介和分区

```powershell
.\scripts\run_publish_localized_video.ps1 `
  --input "https://www.youtube.com/watch?v=..." `
  --workdir ".\runs\demo" `
  --mode subtitles `
  --translation-mode api `
  --translation-quality high `
  --translated-title "这里填助手生成的中文标题" `
  --desc "这里填助手生成的投稿简介" `
  --tid 188
```

### CLI 模式：显式指定投稿分区

```powershell
.\scripts\run_publish_localized_video.ps1 `
  --input "https://www.youtube.com/watch?v=..." `
  --workdir ".\runs\demo" `
  --mode subtitles `
  --translation-mode api `
  --translation-quality high `
  --tid 188
```

### 显式按转载投稿

```powershell
.\scripts\run_publish_localized_video.ps1 `
  --input "https://www.youtube.com/watch?v=..." `
  --workdir ".\runs\demo" `
  --mode subtitles `
  --translation-mode api `
  --translation-quality high `
  --copyright 2
```

## 常见失败场景

### 缺少 `yt-dlp`

安装 `yt-dlp`，或者改用本地视频输入。

### YouTube 触发风控

可以尝试：

- `--cookies-from-browser edge`
- `--cookies /path/to/cookies.txt`
- `--yt-dlp-impersonate edge:windows-10`

### 缺少 `faster-whisper`

安装依赖，或者传 `--transcript-json` 复用已有 transcript。

### Windows 上 CUDA DLL 缺失

当前 localizer 会自动把常见 CUDA 目录注入 `PATH`，但依赖必须已经装好。必要时重建 `.venv`。

### Volcengine 凭证缺失或服务未开通

- `api` / `auto` 模式可能回退到离线翻译
- TTS 需要额外的 `VOLCENGINE_TTS_API_KEY`

### 离线翻译效果差

这是预期限制。优先改用：

- `--translation-mode api`
- `--translation-quality high`

### `biliup` 投稿失败

优先看这几类问题：

- 未登录
- cookie 文件路径错误
- `biliup` 命令不存在
- `tid` / `copyright` / `desc` / `title` 不符合投稿要求

无论失败与否，现有产物和 `publish_metadata.json` 都会保留，方便你直接重试。

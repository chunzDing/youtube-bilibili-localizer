<# 
  Based on: https://github.com/jiayuqi7813/video-Zebra-china
  Local wrapper for YouTube-to-Bilibili localization.
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [string]$Workdir = "",

    [string]$TranscriptJson = "",

    [string]$CookiesFromBrowser = "",

    [switch]$SkipTranscription,

    [switch]$SkipTts,

    [string]$SourceLanguage = "",

    [ValidateSet("api", "offline", "auto")]
    [string]$TranslationMode = "offline",

    [ValidateSet("zh", "bilingual")]
    [string]$SubtitleLayout = "bilingual",

    [string]$WhisperModel = "small",

    [string]$WhisperDevice = "cpu",

    [string]$WhisperComputeType = "int8",

    [string]$Voice = "zh_female_qingxin",

    [double]$BackgroundVolume = 0.12,

    [switch]$SidecarSubtitles
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $projectRoot ".env.local"

if (Test-Path -LiteralPath $envFile) {
    Get-Content -LiteralPath $envFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }

        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) {
            return
        }

        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

$skillRoot = if ($env:YCL_SKILL_ROOT) { $env:YCL_SKILL_ROOT } else { "C:\Users\dqc\.codex\skills\youtube-chinese-localizer" }
$pythonExe = if ($env:YCL_PYTHON_EXE) { $env:YCL_PYTHON_EXE } else { Join-Path $skillRoot ".venv\Scripts\python.exe" }
$ffmpegBin = if ($env:YCL_FFMPEG_BIN) { $env:YCL_FFMPEG_BIN } else { "C:\Users\dqc\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-essentials_build\bin" }
$venvBin = Join-Path $skillRoot ".venv\Scripts"
$scriptPath = Join-Path $skillRoot "scripts\localize_video.py"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Missing Python runtime: $pythonExe"
}

if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Missing localizer script: $scriptPath"
}

$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$pathPrefixes = @($venvBin)
if ($ffmpegBin -and (Test-Path -LiteralPath $ffmpegBin)) {
    $pathPrefixes += $ffmpegBin
}
$env:PATH = (($pathPrefixes + @($env:PATH)) -join ";")

if (-not $Workdir) {
    $safeName = [IO.Path]::GetFileNameWithoutExtension($InputPath)
    if ($InputPath -match "v=([A-Za-z0-9_-]{6,})") {
        $safeName = $Matches[1]
    } elseif ($InputPath -match "youtu\.be/([A-Za-z0-9_-]{6,})") {
        $safeName = $Matches[1]
    } elseif (-not $safeName) {
        $safeName = "video-run"
    }

    $Workdir = Join-Path $projectRoot "runs\$safeName"
}

$args = @(
    $scriptPath
    "--input"
    $InputPath
    "--workdir"
    $Workdir
    "--whisper-device"
    $WhisperDevice
    "--whisper-compute-type"
    $WhisperComputeType
    "--whisper-model"
    $WhisperModel
    "--voice"
    $Voice
    "--background-volume"
    $BackgroundVolume.ToString([Globalization.CultureInfo]::InvariantCulture)
)

if ($TranscriptJson) {
    $args += @("--transcript-json", $TranscriptJson)
}

if ($CookiesFromBrowser) {
    $args += @("--cookies-from-browser", $CookiesFromBrowser)
}

if ($SkipTranscription) {
    $args += "--skip-transcription"
}

if ($SkipTts) {
    $args += "--skip-tts"
}

if ($SourceLanguage) {
    $args += @("--source-language", $SourceLanguage)
}

if ($SidecarSubtitles) {
    $args += "--sidecar-subtitles"
}

$args += @("--translation-mode", $TranslationMode)
$args += @("--subtitle-layout", $SubtitleLayout)

& $pythonExe @args

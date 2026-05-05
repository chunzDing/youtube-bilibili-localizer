<#
  Based on: https://github.com/jiayuqi7813/video-Zebra-china
  Local helper for probing Volcengine TTS credentials.
#>

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $projectRoot ".env.local"
$scriptPath = Join-Path $projectRoot "probe_volc_tts.py"

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

        [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
    }
}

$skillRoot = if ($env:YCL_SKILL_ROOT) { $env:YCL_SKILL_ROOT } else { "C:\Users\dqc\.codex\skills\youtube-chinese-localizer" }
$pythonExe = if ($env:YCL_PYTHON_EXE) { $env:YCL_PYTHON_EXE } else { Join-Path $skillRoot ".venv\Scripts\python.exe" }

& $pythonExe $scriptPath

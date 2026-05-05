$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillDir = Split-Path -Parent $scriptDir
$venvPython = Join-Path $skillDir ".venv\Scripts\python.exe"
$entryScript = Join-Path $scriptDir "publish_localized_video.py"

if (Test-Path -LiteralPath $venvPython) {
    & $venvPython $entryScript @args
    exit $LASTEXITCODE
}

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    & py -3 $entryScript @args
    exit $LASTEXITCODE
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & python $entryScript @args
    exit $LASTEXITCODE
}

throw "Missing Python runtime. Create $skillDir\.venv or install Python 3."

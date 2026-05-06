$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RootDir

Write-Host "[PaperPilot] Starting backend on http://127.0.0.1:8000"
python -m uvicorn api.main:app --reload --port 8000

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RootDir

Write-Host "[PaperPilot] Starting frontend on http://127.0.0.1:8501"
python -m streamlit run app.py --server.port 8501

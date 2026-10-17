<#
.SYNOPSIS
  Run the AI Home Visitor system (cameras + dashboard) or one of its maintenance commands.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run.ps1                 # start everything
  powershell -ExecutionPolicy Bypass -File scripts\run.ps1 check-config
  powershell -ExecutionPolicy Bypass -File scripts\run.ps1 check-cameras
#>
param([Parameter(Position = 0)][string]$Command = "serve")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Virtual environment missing. Run: py -3.12 -m venv .venv ; .\.venv\Scripts\pip install -r requirements.txt"
}
$env:PYTHONPATH = Join-Path $root "backend"
Set-Location $root
& $py -m ahv $Command
exit $LASTEXITCODE

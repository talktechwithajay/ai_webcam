<#
.SYNOPSIS
  One-time setup: Python venv + dependencies, face models, dashboard build, settings file.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "1/5 Python virtual environment"
if (-not (Test-Path ".venv\Scripts\python.exe")) { py -3.12 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

Write-Host "2/5 Face models (checksum-verified)"
& .\.venv\Scripts\python.exe tools\download_models.py

Write-Host "3/5 Dashboard"
if (Get-Command npm -ErrorAction SilentlyContinue) {
    Push-Location frontend
    npm install --no-audit --no-fund
    npm run build
    Pop-Location
} else {
    Write-Warning "Node.js/npm not found: the dashboard cannot be built. Install Node LTS and re-run."
}

Write-Host "4/5 Settings file"
if (-not (Test-Path "config\settings.local.yaml")) {
    Copy-Item "config\settings.example.yaml" "config\settings.local.yaml"
    Write-Host "  Created config\settings.local.yaml - open it and fill in your details (it is git-ignored)."
} else {
    Write-Host "  config\settings.local.yaml already exists."
}

Write-Host "5/5 Tests"
$env:PYTHONPATH = Join-Path $root "backend"
& .\.venv\Scripts\python.exe -m pytest -q

Write-Host ""
Write-Host "Next: edit config\settings.local.yaml, then run:"
Write-Host "  scripts\run.ps1 check-config"
Write-Host "  scripts\run.ps1 check-cameras"
Write-Host "  scripts\run.ps1            (start; dashboard at http://localhost:8080)"

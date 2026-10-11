<#
.SYNOPSIS  Installs missing prerequisites with winget. Run from an elevated PowerShell for VirtualBox.
.USAGE     powershell -ExecutionPolicy Bypass -File scripts\install-prerequisites.ps1 [-IncludeVirtualBox] [-IncludeVSCode]
.NOTES     Prompts nothing; review the package list below first. Package IDs verified with `winget search`.
#>
param([switch]$IncludeVirtualBox, [switch]$IncludeVSCode)

function Install($id) {
    Write-Host ">> winget install $id"
    winget install --id $id --exact --accept-package-agreements --accept-source-agreements
}

$have312 = $false
try { $have312 = [bool](& py -3.12 --version 2>$null) } catch {}
if (-not $have312) { Install 'Python.Python.3.12' } else { Write-Host 'Python 3.12 already present' }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Install 'Git.Git' }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Install 'OpenJS.NodeJS.LTS' }
if ($IncludeVSCode -and -not (Get-Command code -ErrorAction SilentlyContinue)) { Install 'Microsoft.VisualStudioCode' }
if ($IncludeVirtualBox) { Install 'Oracle.VirtualBox' }

Write-Host "`nDone. Open a NEW terminal so PATH changes apply, then re-run scripts\check-environment.ps1"

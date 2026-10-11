<#
.SYNOPSIS  Read-only inspection of the Windows host for the visitor-recognition project.
.USAGE     powershell -ExecutionPolicy Bypass -File scripts\check-environment.ps1
#>
$ErrorActionPreference = 'Continue'
function Row($name, $ok, $detail) {
    $mark = if ($ok) { '[ OK ]' } else { '[FAIL]' }
    Write-Host ("{0} {1,-28} {2}" -f $mark, $name, $detail)
}

# Python 3.12 (preferred; 3.13 may lack wheels for some CV packages)
$py312 = $null
try { $py312 = (& py -3.12 --version 2>$null) } catch {}
Row 'Python 3.12' ([bool]$py312) ($(if ($py312) { $py312 } else { 'not installed (py -3.12 missing)' }))

$git = (Get-Command git -ErrorAction SilentlyContinue)
Row 'Git' ([bool]$git) ($(if ($git) { (git --version) } else { 'missing' }))

$node = (Get-Command node -ErrorAction SilentlyContinue)
Row 'Node.js' ([bool]$node) ($(if ($node) { (node --version) } else { 'missing' }))

$vb = "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
Row 'VirtualBox' (Test-Path $vb) ($(if (Test-Path $vb) { & $vb --version } else { 'not installed' }))

$code = Get-Command code -ErrorAction SilentlyContinue
Row 'VS Code' ([bool]$code) ($(if ($code) { $code.Source } else { 'not on PATH' }))

# Hyper-V / VBS: VirtualBox runs (slower) alongside Hyper-V via WHP, but HAOS performance suffers.
$hv = (Get-CimInstance Win32_ComputerSystem).HypervisorPresent
Row 'Hypervisor active (info)' $true ("HypervisorPresent=$hv  (True means Hyper-V/VBS is running; see docs/01-windows-setup.md)")

$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
Row 'RAM >= 8 GB' ($ram -ge 8) "$ram GB"

Write-Host "`nCameras (PnP class Camera/Image, present):"
Get-PnpDevice -PresentOnly -Class Camera, Image -ErrorAction SilentlyContinue |
    Select-Object Status, Class, FriendlyName | Format-Table -AutoSize

Write-Host "Sleep timeouts (seconds, 0 = never) - AC / DC:"
$q = powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE
($q | Select-String 'Current (AC|DC)') | ForEach-Object { $_.Line.Trim() }

<#
.SYNOPSIS
  Start the visitor system automatically when you sign in to Windows (and optionally the Home Assistant VM).
.PARAMETER Remove
  Remove the scheduled tasks again.
.PARAMETER VMName
  VirtualBox VM name to start headless before the app (default "Home Assistant"); pass "" to skip.
.NOTES
  Runs as the current user, no admin rights needed. Logs go to data\logs\.
#>
param([switch]$Remove, [string]$VMName = "Home Assistant")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$appTask = "AI Home Visitor"
$vmTask = "AI Home Visitor - Home Assistant VM"

if ($Remove) {
    foreach ($t in @($appTask, $vmTask)) { Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue }
    Write-Host "Removed scheduled tasks."
    return
}

$logDir = Join-Path $root "data\logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)

if ($VMName) {
    $vbox = "${env:ProgramFiles}\Oracle\VirtualBox\VBoxManage.exe"
    if (Test-Path $vbox) {
        $a = New-ScheduledTaskAction -Execute $vbox -Argument "startvm `"$VMName`" --type headless"
        Register-ScheduledTask -TaskName $vmTask -Action $a -Trigger $trigger -Settings $settings -Force | Out-Null
        Write-Host "Registered: $vmTask"
    } else {
        Write-Warning "VBoxManage not found; skipping the VM task."
    }
}

$cmd = "powershell.exe"
$arg = "-NoProfile -ExecutionPolicy Bypass -Command `"& '$root\scripts\run.ps1' *>> '$logDir\ahv.log'`""
$action = New-ScheduledTaskAction -Execute $cmd -Argument $arg -WorkingDirectory $root
# Delay a little so the VM and network are up first.
$delayed = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$delayed.Delay = "PT60S"
Register-ScheduledTask -TaskName $appTask -Action $action -Trigger $delayed -Settings $settings -Force | Out-Null
Write-Host "Registered: $appTask  (starts 60 s after you sign in; log: $logDir\ahv.log)"
Write-Host "Remove with: scripts\install-startup.ps1 -Remove"

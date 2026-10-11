<#
.SYNOPSIS  Stops the laptop sleeping while plugged in (AC). Monitor may still turn off.
.USAGE     powershell -ExecutionPolicy Bypass -File scripts\prevent-sleep.ps1            # apply
           powershell -ExecutionPolicy Bypass -File scripts\prevent-sleep.ps1 -Restore 30  # restore 30 min AC sleep
#>
param([int]$Restore = 0)

if ($Restore -gt 0) {
    powercfg /change standby-timeout-ac $Restore
    Write-Host "AC sleep timeout restored to $Restore min"
    return
}
powercfg /change standby-timeout-ac 0      # never sleep on AC
powercfg /change hibernate-timeout-ac 0    # never hibernate on AC
# Closing the lid does nothing on AC (index 0 = do nothing).
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setactive SCHEME_CURRENT
Write-Host 'Sleep/hibernate disabled on AC; lid close = do nothing on AC. Keep the laptop plugged in.'

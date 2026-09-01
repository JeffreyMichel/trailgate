# One-time setup: registers the "Trailgate Permit Check" scheduled task.
# Run in an ELEVATED PowerShell:  powershell -ExecutionPolicy Bypass -File .\scheduler\Register-Task.ps1
# Re-run any time to update the task definition.

#Requires -Version 5.1
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'

$TaskName = 'Trailgate Permit Check'
$Script   = Join-Path $PSScriptRoot 'trigger-permit-check.ps1'
$RunAt    = '7:00:00AM'   # local time (this box is Pacific)

if (-not (Test-Path $Script)) { throw "missing $Script" }

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $Script)

$trigger = New-ScheduledTaskTrigger -Daily -At $RunAt

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

# S4U: runs whether or not you're logged on, no stored password. Outbound HTTPS
# to GitHub works fine; it just can't reach password-protected network shares.
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType S4U -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description 'Dispatches the trailgate permit-check.yml GitHub Actions workflow at 7:00 local time.' `
    -Force

Write-Host "Registered '$TaskName' - fires daily at $RunAt."
Write-Host "Test now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Then check: Get-Content '$PSScriptRoot\logs\trigger-*.log' -Tail 5"

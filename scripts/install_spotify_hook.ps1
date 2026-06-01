# LyPy — start at Windows USER LOGON (Scheduled Task), NOT a Spotify hook.
#
# This script does NOT launch LyPy when Spotify.exe starts. For Spotify-like UX:
#   - In LyPy: Start at Windows login + Launch hidden to tray
#   - Optional: Raise when Spotify.exe starts / Show when Spotify is active (WMTC)
# See README.md "Spotify startup" for the full truth table.
#
# Cold-launch on Spotify process start requires separate Task Scheduler/WMI setup
# and is not provided by this repo.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\install_spotify_hook.ps1 -LyPyExe "C:\Apps\LyPy.exe"

param(
    [Parameter(Mandatory = $false)]
    [string] $LyPyExe = ""
)

if (-not $LyPyExe) {
    $here = Split-Path -Parent $MyInvocation.MyCommand.Path
    $guess = Join-Path (Split-Path -Parent $here) "dist\LyPy.exe"
    if (Test-Path -LiteralPath $guess) { $LyPyExe = $guess }
}

if (-not (Test-Path -LiteralPath $LyPyExe)) {
    Write-Host "Pass -LyPyExe path to LyPy.exe. Example:"
    Write-Host '  powershell -ExecutionPolicy Bypass -File .\install_spotify_hook.ps1 -LyPyExe "D:\build\LyPy.exe"'
    exit 1
}

$TaskName = "LyPyUserLogon"
$Action = New-ScheduledTaskAction -Execute $LyPyExe
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
} catch {}

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Description "Starts LyPy at user logon" | Out-Null

Write-Host "Registered scheduled task '$TaskName' for: $LyPyExe"
Write-Host "Remove with: Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"

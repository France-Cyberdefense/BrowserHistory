<#
.SYNOPSIS
    Deploy Browser History Monitor (global install)
    Creates deployment trigger file browser_history.log
#>

# =========================
# CONFIGURATION
# =========================
$SourceUrl   = "https://raw.githubusercontent.com/France-CyberDefense/BrowserHistory/refs/heads/main/browser-history-monitor.py"
$InstallDir = "C:\BrowserMonitor"
$ScriptName = "browser-history-monitor.py"
$TaskName   = "BrowserHistoryMonitor"

$DestPath   = Join-Path $InstallDir $ScriptName
$LogPath    = Join-Path $InstallDir "browser_history.log"

# =========================
# ADMIN CHECK
# =========================
$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)

if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "This script must be run as Administrator"
    exit 1
}

# =========================
# PYTHON CHECK (SYSTEM)
# =========================
$PythonExe = "C:\Program Files\Python312\pythonw.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Error "System-wide Python 3.12 not found ($PythonExe)"
    exit 1
}

# =========================
# INSTALL DIRECTORY
# =========================
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
}

# =========================
# DEPLOYMENT TRIGGER FILE
# =========================
# This file is used as a SOC-native deployment indicator
if (-not (Test-Path $LogPath)) {
    New-Item -ItemType File -Force -Path $LogPath | Out-Null
}

# =========================
# DOWNLOAD PYTHON SCRIPT
# =========================
Invoke-WebRequest -Uri $SourceUrl -OutFile $DestPath -UseBasicParsing

# =========================
# SCHEDULED TASK (USER CONTEXT)
# =========================
$action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$DestPath`"" `
    -WorkingDirectory $InstallDir

$trigger = New-ScheduledTaskTrigger -AtLogon

$taskPrincipal = New-ScheduledTaskPrincipal `
    -GroupId "BUILTIN\Users" `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -Hidden `
    -ExecutionTimeLimit 0

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $taskPrincipal `
    -Settings $settings | Out-Null

# =========================
# STARTUP FAILSAFE
# =========================
$StartupDir = "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp"
$ShortcutPath = Join-Path $StartupDir "BrowserHistoryMonitor.lnk"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $PythonExe
$Shortcut.Arguments  = "`"$DestPath`""
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Save()

Write-Host "[OK] Deployment complete – trigger file present at $LogPath"

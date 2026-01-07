<#
.SYNOPSIS
  Deploy Browser History Monitor (Global install, user-scoped logs)
#>

# =========================
# CONFIG
# =========================
$SourceUrl   = "https://raw.githubusercontent.com/France-CyberDefense/BrowserHistory/refs/heads/main/browser-history-monitor.py"
$InstallDir = "C:\BrowserMonitor"
$ScriptName = "browser-history-monitor.py"
$TaskName   = "BrowserHistoryMonitor"

$DestPath = Join-Path $InstallDir $ScriptName

# =========================
# ADMIN CHECK
# =========================
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Run as Administrator"
    exit 1
}

# =========================
# PYTHON CHECK
# =========================
$Python = "C:\Program Files\Python312\pythonw.exe"
if (-not (Test-Path $Python)) {
    Write-Error "System Python 3.12 not found"
    exit 1
}

# =========================
# INSTALL DIR
# =========================
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# ACL: READ & EXECUTE ONLY
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)

$admins = New-Object System.Security.AccessControl.FileSystemAccessRule(
    "BUILTIN\Administrators", "FullControl",
    "ContainerInherit,ObjectInherit", "None", "Allow"
)

$users = New-Object System.Security.AccessControl.FileSystemAccessRule(
    "BUILTIN\Users", "ReadAndExecute",
    "ContainerInherit,ObjectInherit", "None", "Allow"
)

$acl.AddAccessRule($admins)
$acl.AddAccessRule($users)
Set-Acl $InstallDir $acl

# =========================
# DOWNLOAD SCRIPT
# =========================
Invoke-WebRequest -Uri $SourceUrl -OutFile $DestPath -UseBasicParsing

# =========================
# SCHEDULED TASK
# =========================
$action  = New-ScheduledTaskAction -Execute $Python -Argument "`"$DestPath`"" -WorkingDirectory $InstallDir
$trigger = New-ScheduledTaskTrigger -AtLogon
$principal = New-ScheduledTaskPrincipal -GroupId "BUILTIN\Users" -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -Hidden -ExecutionTimeLimit 0

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings

# =========================
# STARTUP FAILSAFE
# =========================
$Startup = "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp"
$lnk = Join-Path $Startup "BrowserHistoryMonitor.lnk"

$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = $Python
$s.Arguments  = "`"$DestPath`""
$s.WorkingDirectory = $InstallDir
$s.Save()

Write-Host "[OK] Deployment complete"

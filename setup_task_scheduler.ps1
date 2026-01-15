# Windows Task Scheduler Setup Script
# Used to create a scheduled task to protect the monitoring program

$ErrorActionPreference = "Stop"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = "python"
$MainScript = Join-Path $ScriptDir "main.py"
$TaskName = "YunzaiLLBotMonitor"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host " YunzaiLLBot Monitor - Task Scheduler Setup" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Check if main.py exists
if (-not (Test-Path $MainScript)) {
    Write-Host "Error: main.py not found" -ForegroundColor Red
    Write-Host "Path: $MainScript" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Found main.py: $MainScript" -ForegroundColor Green
Write-Host ""

# Check if task already exists
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "Warning: Task '$TaskName' already exists" -ForegroundColor Yellow
    $response = Read-Host "Delete and recreate? (Y/N)"
    if ($response -eq "Y" -or $response -eq "y") {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[OK] Old task deleted" -ForegroundColor Green
    } else {
        Write-Host "Operation cancelled" -ForegroundColor Yellow
        exit 0
    }
}

Write-Host "Creating scheduled task..." -ForegroundColor Cyan

# Create task action
$action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument "`"$MainScript`"" `
    -WorkingDirectory $ScriptDir

# Create trigger - startup and repeat every 1 minute
# 使用无限重复的触发器
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1)

# Create retry settings - retry every 10 seconds, unlimited times
# 注意：实际的重启次数由任务本身的keep_alive_main函数控制
$repetition = New-ScheduledTaskSettingsSet `
    -RestartInterval (New-TimeSpan -Seconds 10) `
    -RestartCount 999

# Set task to run as current user account (to show window)
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Highest

# Create task settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit "0"  # 0表示无限制

# Register task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Monitor llbot and Yunzai processes, auto-restart on failure" `
    -Force | Out-Null

Write-Host "[OK] Task created successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Task Info:" -ForegroundColor Cyan
Write-Host "  Task Name: $TaskName" -ForegroundColor White
Write-Host "  Account: $currentUser" -ForegroundColor White
Write-Host "  Trigger: Every 1 minute (30s delay on first run)" -ForegroundColor White
Write-Host "  Retry: Every 10 sec, unlimited (controlled by script)" -ForegroundColor White
Write-Host "  Script: $MainScript" -ForegroundColor White
Write-Host ""

# Verify task creation
$task = Get-ScheduledTask -TaskName $TaskName
if ($task) {
    Write-Host "[OK] Task registered successfully" -ForegroundColor Green
    Write-Host ""
    Write-Host "Common Commands:" -ForegroundColor Cyan
    Write-Host "  Check status: Get-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
    Write-Host "  Start task:   Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
    Write-Host "  Stop task:    Stop-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
    Write-Host "  Delete task:  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Tip: You can view and manage this task in Task Scheduler (taskschd.msc)" -ForegroundColor Yellow
} else {
    Write-Host "[X] Task creation failed" -ForegroundColor Red
    exit 1
}
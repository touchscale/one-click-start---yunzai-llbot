$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = "python"
$MainScript = Join-Path $ScriptDir "main.py"
$TaskName = "YunzaiLLBotMonitor"

# 自动检测 Python 完整路径（计划任务在系统 session 中可能找不到 PATH 中的 python）
$PythonResolved = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonResolved) {
    $PythonResolved = (Get-Command python3 -ErrorAction SilentlyContinue).Source
}
if ($PythonResolved) {
    $PythonPath = $PythonResolved
    Write-Host "[OK] 检测到 Python 路径: $PythonPath" -ForegroundColor Green
} else {
    Write-Host "[!] 未找到 Python，将使用 'python' 命令（如果任务运行失败，请手动指定完整路径）" -ForegroundColor Yellow
}

Write-Host "================================================" -ForegroundColor Cyan
Write-Host " YunzaiLLBot Monitor - Task Scheduler Setup" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

function SetupAutoLogin {
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Yellow
    Write-Host " Auto-Login Configuration" -ForegroundColor Yellow
    Write-Host "================================================" -ForegroundColor Yellow
    Write-Host ""

    $autoLoginScript = Join-Path $ScriptDir "auto_login.py"
    if (-not (Test-Path $autoLoginScript)) {
        Write-Host "[X] auto_login.py not found" -ForegroundColor Red
        return $false
    }

    $configPath = Join-Path $ScriptDir "config.yaml"
    if (-not (Test-Path $configPath)) {
        Write-Host "[X] config.yaml not found" -ForegroundColor Red
        return $false
    }

    Write-Host "Reading auto-login configuration from config.yaml..." -ForegroundColor Cyan

    try {
        Push-Location $ScriptDir
        $output = & $PythonPath -c "from config import load_config; from auto_login import apply_config_from_dict, print_status; config = load_config(); result = apply_config_from_dict(config); print_status(); print(f'Result: {result}')"
        Pop-Location

        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Auto-login configuration applied successfully" -ForegroundColor Green
            return $true
        } else {
            Write-Host "[X] Failed to apply auto-login configuration" -ForegroundColor Red
            Write-Host $output
            return $false
        }
    }
    catch {
        Write-Host "[X] Error running auto-login configuration: $_" -ForegroundColor Red
        Write-Host "Note: This script requires administrator privileges." -ForegroundColor Yellow
        return $false
    }
}

if (-not (Test-Path $MainScript)) {
    Write-Host "Error: main.py not found" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Found main.py: $MainScript" -ForegroundColor Green
Write-Host ""

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "Warning: Task already exists" -ForegroundColor Yellow
    $response = Read-Host "Delete and recreate? (Y/N)"
    if ($response -eq "Y" -or $response -eq "y") {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[OK] Old task deleted" -ForegroundColor Green
    } else {
        Write-Host "Operation cancelled" -ForegroundColor Yellow
        exit 0
    }
}

Write-Host "Creating scheduled task..." -ForegroundColor Cyan

$autoLoginResult = SetupAutoLogin
if (-not $autoLoginResult) {
    Write-Host "Auto-login not enabled. You will need to log in manually." -ForegroundColor Gray
    Write-Host ""
}

# Set task to run as current user account (to show window)
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

# Create task action
$action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument "`"$MainScript`"" `
    -WorkingDirectory $ScriptDir

# Create trigger - run every minute (periodic monitoring)
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Highest

# Create task settings with retry and prevent parallel execution
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit "0" `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -RestartCount 999 `
    -MultipleInstances IgnoreNew

Write-Host "Registering task..." -ForegroundColor Cyan

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "Monitor llbot and Yunzai processes, auto-restart on failure" `
        -Force | Out-Null

    Write-Host "[OK] Scheduled task created successfully!" -ForegroundColor Green
}
catch {
    Write-Host "[X] Failed to create task: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Task Information:" -ForegroundColor Cyan
Write-Host "  Task Name: $TaskName" -ForegroundColor White
Write-Host "  Run As: $currentUser" -ForegroundColor White
Write-Host "  Trigger: Every 1 minute" -ForegroundColor White
Write-Host "  Run Mode: Interactive with visible Python window" -ForegroundColor White
Write-Host "  Script Path: $MainScript" -ForegroundColor White
Write-Host "  Behavior: Checks every minute, auto-restarts on failure" -ForegroundColor White
Write-Host ""
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "  - Monitor will check every minute" -ForegroundColor White
Write-Host "  - Python window will be visible" -ForegroundColor White
Write-Host "  - Auto-restarts if process exits (up to 999 times)" -ForegroundColor White
Write-Host ""

# Verify task creation
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
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
    Write-Host "[X] Task verification failed" -ForegroundColor Red
    exit 1
}

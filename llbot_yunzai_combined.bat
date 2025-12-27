@echo off
:: Run CMD as administrator
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    powershell -Command "Start-Process '%0' -Verb RunAs"
    exit /b
)
chcp 65001 >nul
title llbot and Yunzai Process Monitor

:: Set variables for llbot
setlocal enabledelayedexpansion
set "LLBOT_PATH=D:\idm\qqnt\LLBot-Desktop-win-x64\llbot.exe"
set "LLBOT_DIR=D:\idm\qqnt\LLBot-Desktop-win-x64"
set "LLBOT_PROCESS_NAME=llbot.exe"
set "LLBOT_WAIT_SECONDS=5"

:: Set variables for Yunzai
set "GIT_BASH_PATH=D:\Git\git-bash.exe"
set "BASH_DIR=D:\idm\Yunzai"
set "NODE_COMMAND=node app"
set "YUNZAI_WAIT_SECONDS=5"
set "YUNZAI_PROCESS_NAME=git-bash.exe"

:: Set variables for Redis
set "REDIS_DIR=D:\idm\Redis-7.2.5-Windows-x64-msys2\Redis-7.2.5-Windows-x64-msys2"
set "REDIS_PROCESS_NAME=redis-server.exe"

:: Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Running as administrator - process termination should work properly
) else (
    echo WARNING: Not running as administrator - some processes may not terminate properly
    echo Please run this script as administrator for full functionality
    timeout /t 5 /nobreak >nul
)

echo Starting llbot and Yunzai process monitoring...
echo Press Ctrl+C to exit monitoring

:MAIN_LOOP

:: Check and manage llbot process
REM Check if llbot is accessible
powershell -command "try { $response = Invoke-WebRequest -Uri 'http://localhost:3080' -UseBasicParsing -TimeoutSec 10; if ($response.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 (
    echo [ %date% %time% ] http://localhost:3080 is accessible...
    REM Check if llbot.exe is still running as a backup check
    tasklist /FI "IMAGENAME eq !LLBOT_PROCESS_NAME!" 2>NUL | find /I /N "!LLBOT_PROCESS_NAME!">NUL
    if "%ERRORLEVEL%"=="0" (
        echo [ %date% %time% ] !LLBOT_PROCESS_NAME! process is running...
    ) else (
        REM llbot.exe is not running even though website should be accessible, clean up related processes and restart it
        echo [ %date% %time% ] !LLBOT_PROCESS_NAME! process is not running but website should be accessible, cleaning up related processes and restarting...
        
        REM Terminate flet.exe processes (try multiple methods for better reliability)
        echo [ %date% %time% ] Attempting to terminate flet.exe processes...
        for /f "tokens=2" %%i in ('tasklist /fi "imagename eq flet.exe" /fo csv ^| find /i "flet.exe"') do (
            echo [ %date% %time% ] Terminating flet.exe PID %%i...
            taskkill /pid %%i /f /t >nul 2>&1
            if !ERRORLEVEL! EQU 0 (
                echo [ %date% %time% ] Successfully terminated flet.exe PID %%i
            ) else (
                echo [ %date% %time% ] Failed to terminate flet.exe PID %%i
            )
        )
        REM Fallback: kill by image name if PID method didn't work
        taskkill /f /im flet.exe /t >nul 2>&1
        if !ERRORLEVEL! LEQ 1 (
            echo [ %date% %time% ] flet.exe processes terminated or not found
        ) else (
            echo [ %date% %time% ] Warning: Could not terminate some flet.exe processes
        )
        
        REM Terminate QQ.exe processes (comprehensive method for stubborn processes)
        echo [ %date% %time% ] Attempting to terminate QQ.exe processes...
        
        REM Method 1: Use PowerShell to find and terminate all QQ-related processes
        for /f "usebackq" %%i in (`powershell -command "Get-Process -Name 'QQ','QQProtect','QQPCRTP' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"`) do (
            echo [ %date% %time% ] Terminating QQ-related process PID %%i using PowerShell...
            powershell -command "Stop-Process -Id %%i -Force -ErrorAction SilentlyContinue" >nul 2>&1
            if !ERRORLEVEL! EQU 0 (
                echo [ %date% %time% ] Successfully terminated process %%i using PowerShell
            ) else (
                echo [ %date% %time% ] Failed to terminate process %%i using PowerShell
            )
        )
        
        REM Method 2: Use wmic to terminate any remaining QQ processes
        for /f "skip=1" %%i in ('wmic process where "name like '%%QQ%%'" get ProcessId ^| findstr /r "[0-9]"') do (
            if not "%%i"=="" (
                echo [ %date% %time% ] Terminating QQ-related process PID: %%i using wmic...
                wmic process where ProcessId=%%i call terminate >nul 2>&1
                if !ERRORLEVEL! EQU 0 (
                    echo [ %date% %time% ] Successfully terminated process %%i using wmic
                ) else (
                    echo [ %date% %time% ] Failed to terminate process %%i using wmic
                )
            )
        )
        
        REM Method 3: Use taskkill with image name for any remaining processes
        echo [ %date% %time% ] Terminating QQ-related processes by image name...
        taskkill /f /im QQ.exe /t >nul 2>&1
        if !ERRORLEVEL! LEQ 1 (
            echo [ %date% %time% ] QQ.exe processes terminated or not found
        ) else (
            echo [ %date% %time% ] Warning: Could not terminate QQ.exe processes
        )
        
        taskkill /f /im QQProtect.exe /t >nul 2>&1
        if !ERRORLEVEL! LEQ 1 (
            echo [ %date% %time% ] QQProtect.exe processes terminated or not found
        ) else (
            echo [ %date% %time% ] Warning: Could not terminate QQProtect.exe processes
        )
        
        taskkill /f /im QQPCRTP.exe /t >nul 2>&1
        if !ERRORLEVEL! LEQ 1 (
            echo [ %date% %time% ] QQPCRTP.exe processes terminated or not found
        ) else (
            echo [ %date% %time% ] Warning: Could not terminate QQPCRTP.exe processes
        )
        
        REM Additional wait to ensure processes are fully terminated
        echo [ %date% %time% ] Waiting for processes to fully terminate...
        timeout /t 3 /nobreak >nul
        
        REM Check again if any QQ-related processes are still running
        tasklist /FI "IMAGENAME eq QQ.exe" 2>NUL | find /I /N "QQ.exe">NUL
        if "%ERRORLEVEL%"=="0" (
            echo [ %date% %time% ] Warning: QQ.exe still running, using final emergency termination...
            REM Final method: Use PowerShell with more aggressive parameters
            powershell -command "Get-WmiObject -Class Win32_Process -Filter \"Name='QQ.exe'\" | ForEach-Object { $_.Terminate(); }" >nul 2>&1
            timeout /t 1 /nobreak >nul
        ) else (
            echo [ %date% %time% ] QQ.exe processes confirmed terminated
        )
        
        REM Additional check for related QQ processes that might prevent restart
        tasklist /FI "IMAGENAME eq QQProtect.exe" 2>NUL | find /I /N "QQProtect.exe">NUL
        if "%ERRORLEVEL%"=="0" (
            echo [ %date% %time% ] QQProtect.exe still running, terminating...
            powershell -command "Get-Process -Name 'QQProtect' -ErrorAction SilentlyContinue | Stop-Process -Force" >nul 2>&1
        )
        
        tasklist /FI "IMAGENAME eq QQPCRTP.exe" 2>NUL | find /I /N "QQPCRTP.exe">NUL
        if "%ERRORLEVEL%"=="0" (
            echo [ %date% %time% ] QQPCRTP.exe still running, terminating...
            powershell -command "Get-Process -Name 'QQPCRTP' -ErrorAction SilentlyContinue | Stop-Process -Force" >nul 2>&1
        )
        
        REM Final verification: Check if any QQ-related processes are still running
        echo [ %date% %time% ] Verifying all QQ-related processes are terminated...
        tasklist /FI "IMAGENAME eq QQ.exe" 2>NUL | find /I /N "QQ.exe">NUL
        if "%ERRORLEVEL%"=="0" (
            echo [ %date% %time% ] ERROR: QQ.exe still running - restart may fail
        ) else (
            echo [ %date% %time% ] QQ.exe confirmed terminated
        )
        
        tasklist /FI "IMAGENAME eq QQProtect.exe" 2>NUL | find /I /N "QQProtect.exe">NUL
        if "%ERRORLEVEL%"=="0" (
            echo [ %date% %time% ] ERROR: QQProtect.exe still running - restart may fail
        ) else (
            echo [ %date% %time% ] QQProtect.exe confirmed terminated
        )
        
        tasklist /FI "IMAGENAME eq QQPCRTP.exe" 2>NUL | find /I /N "QQPCRTP.exe">NUL
        if "%ERRORLEVEL%"=="0" (
            echo [ %date% %time% ] ERROR: QQPCRTP.exe still running - restart may fail
        ) else (
            echo [ %date% %time% ] QQPCRTP.exe confirmed terminated
        )
        
        echo [ %date% %time% ] Starting !LLBOT_PROCESS_NAME!...
        
        REM Start llbot.exe in its directory to ensure config files are accessible
        if exist "!LLBOT_PATH!" (
            echo [ %date% %time% ] Found !LLBOT_PROCESS_NAME!, starting in directory: !LLBOT_DIR!
            cd /d "!LLBOT_DIR!"
            start "" "!LLBOT_PATH!"
        ) else (
            echo [ %date% %time% ] !LLBOT_PROCESS_NAME! not found, please verify the path: !LLBOT_PATH!
        )
    )
) else (
    echo [ %date% %time% ] http://localhost:3080 is not accessible, terminating related processes and restarting llbot...
    
    REM Terminate flet.exe processes (try multiple methods for better reliability)
    echo [ %date% %time% ] Attempting to terminate flet.exe processes...
    for /f "tokens=2" %%i in ('tasklist /fi "imagename eq flet.exe" /fo csv ^| find /i "flet.exe"') do (
        echo [ %date% %time% ] Terminating flet.exe PID %%i...
        taskkill /pid %%i /f /t >nul 2>&1
        if !ERRORLEVEL! EQU 0 (
            echo [ %date% %time% ] Successfully terminated flet.exe PID %%i
        ) else (
            echo [ %date% %time% ] Failed to terminate flet.exe PID %%i
        )
    )
    REM Fallback: kill by image name if PID method didn't work
    taskkill /f /im flet.exe /t >nul 2>&1
    if !ERRORLEVEL! LEQ 1 (
        echo [ %date% %time% ] flet.exe processes terminated or not found
    ) else (
        echo [ %date% %time% ] Warning: Could not terminate some flet.exe processes
    )
    
    REM Terminate QQ.exe processes (comprehensive method for stubborn processes)
    echo [ %date% %time% ] Attempting to terminate QQ.exe processes...
    
    REM Method 1: Use PowerShell to find and terminate all QQ-related processes
    for /f "usebackq" %%i in (`powershell -command "Get-Process -Name 'QQ','QQProtect','QQPCRTP' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"`) do (
        echo [ %date% %time% ] Terminating QQ-related process PID %%i using PowerShell...
        powershell -command "Stop-Process -Id %%i -Force -ErrorAction SilentlyContinue" >nul 2>&1
        if !ERRORLEVEL! EQU 0 (
            echo [ %date% %time% ] Successfully terminated process %%i using PowerShell
        ) else (
            echo [ %date% %time% ] Failed to terminate process %%i using PowerShell
        )
    )
    
    REM Method 2: Use wmic to terminate any remaining QQ processes
    for /f "skip=1" %%i in ('wmic process where "name like '%%QQ%%'" get ProcessId ^| findstr /r "[0-9]"') do (
        if not "%%i"=="" (
            echo [ %date% %time% ] Terminating QQ-related process PID: %%i using wmic...
            wmic process where ProcessId=%%i call terminate >nul 2>&1
            if !ERRORLEVEL! EQU 0 (
                echo [ %date% %time% ] Successfully terminated process %%i using wmic
            ) else (
                echo [ %date% %time% ] Failed to terminate process %%i using wmic
            )
        )
    )
    
    REM Method 3: Use taskkill with image name for any remaining processes
    echo [ %date% %time% ] Terminating QQ-related processes by image name...
    taskkill /f /im QQ.exe /t >nul 2>&1
    if !ERRORLEVEL! LEQ 1 (
        echo [ %date% %time% ] QQ.exe processes terminated or not found
    ) else (
        echo [ %date% %time% ] Warning: Could not terminate QQ.exe processes
    )
    
    taskkill /f /im QQProtect.exe /t >nul 2>&1
    if !ERRORLEVEL! LEQ 1 (
        echo [ %date% %time% ] QQProtect.exe processes terminated or not found
    ) else (
        echo [ %date% %time% ] Warning: Could not terminate QQProtect.exe processes
    )
    
    taskkill /f /im QQPCRTP.exe /t >nul 2>&1
    if !ERRORLEVEL! LEQ 1 (
        echo [ %date% %time% ] QQPCRTP.exe processes terminated or not found
    ) else (
        echo [ %date% %time% ] Warning: Could not terminate QQPCRTP.exe processes
    )
    
    REM Additional wait to ensure processes are fully terminated
    echo [ %date% %time% ] Waiting for processes to fully terminate...
    timeout /t 3 /nobreak >nul
    
    REM Check again if any QQ-related processes are still running
    tasklist /FI "IMAGENAME eq QQ.exe" 2>NUL | find /I /N "QQ.exe">NUL
    if "%ERRORLEVEL%"=="0" (
        echo [ %date% %time% ] Warning: QQ.exe still running, using final emergency termination...
        REM Final method: Use PowerShell with more aggressive parameters
        powershell -command "Get-WmiObject -Class Win32_Process -Filter \"Name='QQ.exe'\" | ForEach-Object { $_.Terminate(); }" >nul 2>&1
        timeout /t 1 /nobreak >nul
    ) else (
        echo [ %date% %time% ] QQ.exe processes confirmed terminated
    )
    
    REM Additional check for related QQ processes that might prevent restart
    tasklist /FI "IMAGENAME eq QQProtect.exe" 2>NUL | find /I /N "QQProtect.exe">NUL
    if "%ERRORLEVEL%"=="0" (
        echo [ %date% %time% ] QQProtect.exe still running, terminating...
        powershell -command "Get-Process -Name 'QQProtect' -ErrorAction SilentlyContinue | Stop-Process -Force" >nul 2>&1
    )
    
    tasklist /FI "IMAGENAME eq QQPCRTP.exe" 2>NUL | find /I /N "QQPCRTP.exe">NUL
    if "%ERRORLEVEL%"=="0" (
        echo [ %date% %time% ] QQPCRTP.exe still running, terminating...
        powershell -command "Get-Process -Name 'QQPCRTP' -ErrorAction SilentlyContinue | Stop-Process -Force" >nul 2>&1
    )
    
    REM Final verification: Check if any QQ-related processes are still running
    echo [ %date% %time% ] Verifying all QQ-related processes are terminated...
    tasklist /FI "IMAGENAME eq QQ.exe" 2>NUL | find /I /N "QQ.exe">NUL
    if "%ERRORLEVEL%"=="0" (
        echo [ %date% %time% ] ERROR: QQ.exe still running - restart may fail
    ) else (
        echo [ %date% %time% ] QQ.exe confirmed terminated
    )
    
    tasklist /FI "IMAGENAME eq QQProtect.exe" 2>NUL | find /I /N "QQProtect.exe">NUL
    if "%ERRORLEVEL%"=="0" (
        echo [ %date% %time% ] ERROR: QQProtect.exe still running - restart may fail
    ) else (
        echo [ %date% %time% ] QQProtect.exe confirmed terminated
    )
    
    tasklist /FI "IMAGENAME eq QQPCRTP.exe" 2>NUL | find /I /N "QQPCRTP.exe">NUL
    if "%ERRORLEVEL%"=="0" (
        echo [ %date% %time% ] ERROR: QQPCRTP.exe still running - restart may fail
    ) else (
        echo [ %date% %time% ] QQPCRTP.exe confirmed terminated
    )
    
    echo [ %date% %time% ] Starting !LLBOT_PROCESS_NAME!...
    
    REM Start llbot.exe in its directory to ensure config files are accessible
    if exist "!LLBOT_PATH!" (
        echo [ %date% %time% ] Found !LLBOT_PROCESS_NAME!, starting in directory: !LLBOT_DIR!
        cd /d "!LLBOT_DIR!"
        start "" "!LLBOT_PATH!"
    ) else (
        echo [ %date% %time% ] !LLBOT_PROCESS_NAME! not found, please verify the path: !LLBOT_PATH!
    )
    
    :WAIT_AND_CHECK
    echo [ %date% %time% ] Waiting for !LLBOT_PROCESS_NAME! to start...
    timeout /t !LLBOT_WAIT_SECONDS! /nobreak >nul
    
    REM Check again if process started successfully
    tasklist /FI "IMAGENAME eq !LLBOT_PROCESS_NAME!" 2>NUL | find /I /N "!LLBOT_PROCESS_NAME!">NUL
    if "%ERRORLEVEL%"=="0" (
        echo [ %date% %time% ] !LLBOT_PROCESS_NAME! restart successful
    ) else (
        echo [ %date% %time% ] !LLBOT_PROCESS_NAME! restart failed
    )
)

:: Check and manage Yunzai process
REM Check if Redis is running
tasklist /FI "IMAGENAME eq !REDIS_PROCESS_NAME!" 2>NUL | find /I /N "!REDIS_PROCESS_NAME!">NUL
if "%ERRORLEVEL%"=="1" (
    echo [ %date% %time% ] !REDIS_PROCESS_NAME! is not running, starting Redis server...
    cd /d "!REDIS_DIR!"
    powershell -Command "Start-Process '!REDIS_PROCESS_NAME!' -Verb RunAs"
    timeout /t 3 /nobreak >nul
) else (
    echo [ %date% %time% ] !REDIS_PROCESS_NAME! is already running...
)

REM Check if Yunzai is running
tasklist /fi "imagename eq !YUNZAI_PROCESS_NAME!" | find /i "!YUNZAI_PROCESS_NAME!" >nul
if %errorlevel% equ 1 (
    echo [ %date% %time% ] Starting Yunzai process...
    start "" "%GIT_BASH_PATH%" -c "cd '%BASH_DIR%' && %NODE_COMMAND%"
    echo [ %date% %time% ] Yunzai process started
) else (
    echo [ %date% %time% ] Yunzai process is already running...
)

REM Wait for specified time then check again
timeout /t !LLBOT_WAIT_SECONDS! /nobreak >nul
goto MAIN_LOOP
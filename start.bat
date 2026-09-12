@echo off
chcp 65001 >nul
title iOS RealRun

set "script_dir=%~dp0"
cd /d "%script_dir%"
set "python=%script_dir%venv\Scripts\python.exe"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Requesting admin privileges...
    powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%script_dir%' -ArgumentList '%*'"
    exit /b
)

echo ========================================
echo    iOS RealRun
echo ========================================
echo.

:: Parse arguments
set minutes=30
set nomount=0

:parse
if "%~1"=="" goto :endparse
if /i "%~1"=="-m" set minutes=%~2& shift & shift & goto :parse
if /i "%~1"=="--minutes" set minutes=%~2& shift & shift & goto :parse
if /i "%~1"=="-n" set nomount=1& shift & goto :parse
if /i "%~1"=="--nomount" set nomount=1& shift & goto :parse
shift & goto :parse
:endparse

:: Step 1: Check device
echo [1/3] Checking device connection...
"%python%" -c "import asyncio; from pymobiledevice3.lockdown import create_using_usbmux; asyncio.run(create_using_usbmux())"
if %errorlevel% neq 0 (
    echo [ERROR] No iOS device detected.
    echo Make sure:
    echo   - USB connected and device unlocked
    echo   - "Trust This Computer" was tapped
    echo   - iTunes is installed
    pause
    exit /b
)
echo   Device connected OK
echo.

:: Step 2: Mount developer disk image
if "%nomount%"=="0" (
    echo [2/3] Mounting Developer Disk Image...
    "%python%" -m pymobiledevice3 mounter auto-mount 2>&1 | findstr "mounted successfully" >nul
    if %errorlevel% equ 0 (
        echo   Mount OK
    ) else (
        echo   Mount report unclear, trying anyway...
    )
) else (
    echo [2/3] Skipping mount
)
echo.

:: Step 3: Launch
echo [3/3] Starting virtual location...
echo.
if %minutes% gtr 0 (
    echo   Duration: %minutes% minutes
    echo   Will auto-stop and restore real location
    echo   Press Ctrl+C to stop early
    echo.
    "%python%" main.py -m %minutes%
) else (
    echo   Running indefinitely, press Ctrl+C to stop
    echo.
    "%python%" main.py
)

echo.
echo Virtual location stopped, real location restored.
echo.
pause

<#
.SYNOPSIS
    iOS RealRun 一键启动脚本
.DESCRIPTION
    自动提权管理员 -> 挂载开发者镜像 -> 启动 iOS RealRun -> 到时自动停止
.PARAMETER Minutes
    运行时长（分钟），默认 30。设为 0 则无限运行（需手动 Ctrl+C）
.PARAMETER NoMount
    跳过挂载开发者镜像（已挂载过可跳过）
.EXAMPLE
    .\start.ps1                  # 默认 30 分钟
    .\start.ps1 -Minutes 45      # 45 分钟
    .\start.ps1 -Minutes 0       # 无限运行
    .\start.ps1 -Minutes 20 -NoMount  # 20 分钟，跳过挂载
#>

param(
    [int]$Minutes = 30,
    [switch]$NoMount
)

# ===== 自动提权 =====
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    $host.ui.RawUI.WindowTitle = "iOS RealRun - 请求管理员权限"
    $argList = "-ExecutionPolicy Bypass -File `"$PSCommandPath`" -Minutes $Minutes"
    if ($NoMount) { $argList += " -NoMount" }
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argList
    exit
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir
$python = "$PSScriptRoot\venv\Scripts\python.exe"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   iOS RealRun - 自动模拟跑步" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ===== 1. 检查设备 =====
Write-Host "[1/3] 检查设备连接..." -ForegroundColor Green
$checkResult = & $python -c "import asyncio; from pymobiledevice3.lockdown import create_using_usbmux; asyncio.run(create_using_usbmux())" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [错误] 未检测到 iOS 设备，请确认:" -ForegroundColor Red
    Write-Host "    - USB 已连接且设备已解锁" -ForegroundColor Red
    Write-Host "    - 已点击"信任此电脑"" -ForegroundColor Red
    Write-Host "    - 已安装 iTunes（提供驱动）" -ForegroundColor Red
    Write-Host ""
    Read-Host "准备好后按 Enter 重试"
    & $PSCommandPath -Minutes $Minutes
    exit
}
Write-Host "  设备连接正常" -ForegroundColor White

# ===== 2. 挂载开发者镜像 =====
if (-not $NoMount) {
    Write-Host ""
    Write-Host "[2/3] 挂载开发者镜像..." -ForegroundColor Green
    $mountResult = & $python -m pymobiledevice3 mounter auto-mount 2>&1
    if ($LASTEXITCODE -eq 0 -and ($mountResult -match "mounted successfully")) {
        Write-Host "  挂载成功" -ForegroundColor White
    } else {
        Write-Host "  挂载失败，可直接运行试一下" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "[2/3] 跳过挂载" -ForegroundColor Yellow
}

# ===== 3. 启动模拟 =====
Write-Host ""
Write-Host "[3/3] 启动虚拟定位..." -ForegroundColor Green
Write-Host ""

if ($Minutes -gt 0) {
    Write-Host "  运行时长: ${Minutes} 分钟" -ForegroundColor White
    Write-Host "  到时会自动停止并恢复真实定位" -ForegroundColor White
    Write-Host "  按 Ctrl+C 可提前结束" -ForegroundColor White
    & $python main.py -m $Minutes
} else {
    Write-Host "  无限运行中，按 Ctrl+C 停止" -ForegroundColor White
    & $python main.py
}

Write-Host ""
Write-Host "<<<< iOS RealRun 已停止，定位已恢复 >>>>" -ForegroundColor Cyan
Write-Host ""
Read-Host "按 Enter 退出"

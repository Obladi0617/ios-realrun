$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Missing venv\Scripts\python.exe. Prepare the project environment first."
}

& $python -m pip install --upgrade pyinstaller
& $python -m PyInstaller --noconfirm --clean iOSRealRun.spec

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
$isccPath = if ($iscc) { $iscc.Source } else { $null }
if (-not $isccPath) {
    $candidates = @(
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $isccPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if ($isccPath) {
    & $isccPath installer.iss
    Write-Host "Installer created in dist\installer" -ForegroundColor Green
}
else {
    Write-Host "dist\iOSRealRun created. Inno Setup was not found, so installer generation was skipped." -ForegroundColor Yellow
}
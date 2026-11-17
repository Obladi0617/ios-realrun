param([string]$PythonPath = "", [switch]$Clean)

$ErrorActionPreference = "Stop"
$previousNoUserSite = $env:PYTHONNOUSERSITE
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
$env:PYTHONNOUSERSITE = "1"
try {
    Set-Location $PSScriptRoot
    $frontendTemp = Join-Path $PSScriptRoot "build\frontend-temp"
    New-Item -ItemType Directory -Path $frontendTemp -Force | Out-Null
    $env:TEMP = $frontendTemp
    $env:TMP = $frontendTemp
    Push-Location (Join-Path $PSScriptRoot "frontend")
    try {
        if (-not (Test-Path -LiteralPath "node_modules")) {
            & npm.cmd ci --no-fund --no-audit
            if ($LASTEXITCODE -ne 0) { throw "Frontend dependencies could not be installed." }
        }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    }
    finally { Pop-Location }
    $python = if ($PythonPath) { $PythonPath } else { Join-Path $PSScriptRoot "venv\Scripts\python.exe" }

    if (-not (Test-Path $python)) {
        throw "Python was not found: $python. Prepare the project environment first."
    }

    $appVersion = & $python -c "from app_info import APP_VERSION; print(APP_VERSION)"
    if ($LASTEXITCODE -ne 0 -or $appVersion -notmatch '^\d+\.\d+\.\d+$') {
        throw "Cannot read the application version."
    }
    $distDir = Join-Path $PSScriptRoot "dist\v$appVersion"
    $workDir = Join-Path $PSScriptRoot "build\v$appVersion"
    $bundleDir = Join-Path $distDir "iOSRealRun"
    $installerDir = Join-Path $distDir "installer"

    $cleanArguments = if ($Clean) { @("--clean") } else { @() }
    & $python -m PyInstaller @cleanArguments --noconfirm --distpath $distDir --workpath $workDir iOSRealRun.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed (exit $LASTEXITCODE)." }

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
        & $isccPath "/DMyBuildDir=$bundleDir" "/DMyInstallerDir=$installerDir" installer.iss
        if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }
        $installerPath = Join-Path $installerDir "iOS-RealRun-Setup.exe"
        $hash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  iOS-RealRun-Setup.exe" | Set-Content -LiteralPath (Join-Path $installerDir "SHA256SUMS.txt") -Encoding ascii
        Write-Host "Installer created: $installerPath" -ForegroundColor Green
    }
    else {
        Write-Host "Bundle created: $bundleDir. Install Inno Setup 6 to build the installer." -ForegroundColor Yellow
    }

}
finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
    if ($null -eq $previousNoUserSite) {
        Remove-Item Env:PYTHONNOUSERSITE -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONNOUSERSITE = $previousNoUserSite
    }
}

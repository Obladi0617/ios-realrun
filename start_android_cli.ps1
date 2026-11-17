param(
    [string]$SdkDirectory = "",
    [string]$AndroidHome = "",
    [string]$AvdName = "RealRun_Android15",
    [ValidateSet("auto", "host", "swiftshader")]
    [string]$Gpu = "auto"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $SdkDirectory) {
    $candidates = @($env:ANDROID_HOME, $env:ANDROID_SDK_ROOT,
        "$env:LOCALAPPDATA\Android\Sdk", "D:\Android\Sdk")
    $SdkDirectory = $candidates | Where-Object {
        $_ -and (Test-Path -LiteralPath (Join-Path $_ "emulator\emulator.exe"))
    } | Select-Object -First 1
}
if (-not $SdkDirectory) { throw "Android SDK was not found. Supply -SdkDirectory." }
$SdkDirectory = (Resolve-Path -LiteralPath $SdkDirectory).Path
if (-not $AndroidHome) {
    $AndroidHome = Join-Path (Split-Path -Parent $SdkDirectory) "RealRunTest"
}
if ($AndroidHome -match '[^\x00-\x7F]') {
    throw "Use an ASCII path for -AndroidHome, for example D:\Android\RealRunTest."
}

$stateDirectory = Join-Path $AndroidHome "state"
$avdDirectory = Join-Path $AndroidHome "avd"
$discoveryDirectory = Join-Path $AndroidHome "discovery"
$temporaryDirectory = Join-Path $stateDirectory "android-temp"
New-Item -ItemType Directory -Path $stateDirectory, $avdDirectory, $discoveryDirectory, $temporaryDirectory -Force | Out-Null
$env:ANDROID_HOME = $SdkDirectory
$env:ANDROID_USER_HOME = $AndroidHome
$env:ANDROID_EMULATOR_HOME = $AndroidHome
$env:ANDROID_AVD_HOME = $avdDirectory
$env:ANDROID_EMULATOR_DISCOVERY_DIR = $discoveryDirectory
$env:IOSREALRUN_DATA_DIR = $stateDirectory
$env:PYTHONIOENCODING = "utf-8"

$emulator = Join-Path $SdkDirectory "emulator\emulator.exe"
if (-not (Test-Path -LiteralPath $emulator)) { throw "Install the SDK emulator component first." }
$available = & $emulator -list-avds
if ($LASTEXITCODE -ne 0) { throw "Cannot list Android virtual devices." }
if ($available -notcontains $AvdName) {
    $image = Join-Path $SdkDirectory "system-images\android-35\google_apis\x86_64"
    $manager = Join-Path $SdkDirectory "cmdline-tools\latest\bin\avdmanager.bat"
    if (-not (Test-Path -LiteralPath $image) -or -not (Test-Path -LiteralPath $manager)) {
        throw "Install cmdline-tools and system-images;android-35;google_apis;x86_64 first."
    }
    "no" | & $manager create avd --name $AvdName --package "system-images;android-35;google_apis;x86_64" --device "pixel_5"
    if ($LASTEXITCODE -ne 0) { throw "Cannot create the Android virtual device." }
}

$versionText = Get-Content -LiteralPath (Join-Path $PSScriptRoot "app_info.py") -Raw
$versionMatch = [regex]::Match($versionText, 'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"')
if (-not $versionMatch.Success) { throw "Cannot read the project version." }
$version = $versionMatch.Groups[1].Value
$worker = Join-Path $PSScriptRoot "dist\v$version\iOSRealRun\iOSRealRun-worker.exe"
$arguments = @("--backend", "android", "--sdk", $SdkDirectory, "--start-emulator", "--avd", $AvdName, "--headless", "--gpu", $Gpu)
Write-Host "Starting $AvdName without a window. No route will be started."
Write-Host "Runtime directory: $AndroidHome"
if (Test-Path -LiteralPath $worker) {
    # Build folders can inherit a low integrity label from a former sandbox.
    # New runtime files inherit this user's normal runtime-directory permissions.
    $runtimeApplication = Join-Path $AndroidHome "cli-v$version"
    $stampFile = Join-Path $runtimeApplication ".source-stamp.txt"
    $bundleDirectory = Split-Path -Parent $worker
    $sourceStamp = (Get-Item -LiteralPath $bundleDirectory).LastWriteTimeUtc.Ticks.ToString() + ":" + (Get-FileHash -LiteralPath $worker -Algorithm SHA256).Hash
    $oldStamp = if (Test-Path -LiteralPath $stampFile) { (Get-Content -LiteralPath $stampFile -Raw).Trim() } else { "" }
    if ($sourceStamp -ne $oldStamp -or -not (Test-Path -LiteralPath (Join-Path $runtimeApplication "_internal"))) {
        New-Item -ItemType Directory -Path $runtimeApplication -Force | Out-Null
        $runtimeInternal = Join-Path $runtimeApplication "_internal"
        if (Test-Path -LiteralPath $runtimeInternal) {
            $resolvedInternal = (Resolve-Path -LiteralPath $runtimeInternal).Path
            $resolvedRuntime = (Resolve-Path -LiteralPath $runtimeApplication).Path
            if (-not $resolvedInternal.StartsWith($resolvedRuntime + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
                throw "The runtime dependency directory is outside the application directory."
            }
            Remove-Item -LiteralPath $resolvedInternal -Recurse -Force
        }
        Copy-Item -LiteralPath (Join-Path $bundleDirectory "_internal") -Destination $runtimeApplication -Recurse -Force
        Copy-Item -LiteralPath $worker -Destination (Join-Path $runtimeApplication "iOSRealRun-worker.exe") -Force
        Set-Content -LiteralPath $stampFile -Value $sourceStamp -Encoding ascii
    }
    $worker = Join-Path $runtimeApplication "iOSRealRun-worker.exe"
    & $worker @arguments
}
else {
    $python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) { throw "Build the application or prepare the project venv first." }
    & $python (Join-Path $PSScriptRoot "worker.py") @arguments
}
$workerExit = $LASTEXITCODE
Write-Host "Worker exit: $workerExit"
Write-Host "Emulator log: $(Join-Path $stateDirectory 'emulator-start.log')"
exit $workerExit

param(
    [Parameter(Mandatory = $true)][string]$Sdk,
    [Parameter(Mandatory = $true)][string]$Output
)

$ErrorActionPreference = "Stop"
$tools = Join-Path $Sdk "build-tools\34.0.0"
$androidJar = Join-Path $Sdk "platforms\android-34\android.jar"
$classes = Join-Path $Output "classes"
$dex = Join-Path $Output "dex"
New-Item -ItemType Directory -Path $Output, $classes, $dex -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "AndroidManifest.xml"), (Join-Path $PSScriptRoot "GpsProbe.java") -Destination $Output -Force

function Invoke-Checked {
    param([string]$Tool, [string[]]$ToolArguments)
    & $Tool @ToolArguments
    if ($LASTEXITCODE -ne 0) { throw "Tool failed: $Tool ($LASTEXITCODE)" }
}

Invoke-Checked "javac.exe" @("-encoding", "UTF-8", "-source", "8", "-target", "8", "-classpath", $androidJar, "-d", $classes, (Join-Path $Output "GpsProbe.java"))
$classFiles = @(Get-ChildItem -LiteralPath $classes -Recurse -File -Filter "*.class" | ForEach-Object FullName)
Invoke-Checked (Join-Path $tools "d8.bat") (@("--lib", $androidJar, "--output", $dex) + $classFiles)
$baseApk = Join-Path $Output "base.apk"
$alignedApk = Join-Path $Output "aligned.apk"
$signedApk = Join-Path $Output "RealRun-GPS-Probe.apk"
Invoke-Checked (Join-Path $tools "aapt2.exe") @("link", "--manifest", (Join-Path $Output "AndroidManifest.xml"), "-I", $androidJar, "-o", $baseApk)
Invoke-Checked "jar.exe" @("uf", $baseApk, "-C", $dex, "classes.dex")
Invoke-Checked (Join-Path $tools "zipalign.exe") @("-f", "4", $baseApk, $alignedApk)
$key = Join-Path $Output "local-test.keystore"
if (-not (Test-Path -LiteralPath $key)) {
    Invoke-Checked "keytool.exe" @("-genkeypair", "-noprompt", "-alias", "local-test", "-keyalg", "RSA", "-keysize", "2048", "-validity", "3650", "-keystore", $key, "-storepass", "android", "-keypass", "android", "-dname", "CN=RealRun Local Test")
}
Invoke-Checked (Join-Path $tools "apksigner.bat") @("sign", "--ks", $key, "--ks-pass", "pass:android", "--key-pass", "pass:android", "--out", $signedApk, $alignedApk)
Write-Host "Local GPS probe APK: $signedApk"

#!/usr/bin/env pwsh
# scripts/sign-debug-apk.ps1
# 用一个本地 keystore 对 release APK 签名(便于真机调试)
# 生产发布请用 Play Store 自己的签名 key
param([string]$ApkPath)

$ErrorActionPreference = 'Stop'
$KeyDir  = Join-Path $PSScriptRoot '..\src-tauri\keystore'
$KeyFile = Join-Path $KeyDir 'debug.keystore'
$Alias   = 'upload'
$Pwd     = 'tradedojo1234'
$DName   = 'CN=cttai, OU=tradedojo, O=cttai, L=Beijing, S=Beijing, C=CN'

if (-not (Test-Path $KeyFile)) {
    Write-Host '[keytool] Generating keystore ...'
    New-Item -ItemType Directory -Force -Path $KeyDir | Out-Null
    & keytool -genkeypair `
        -keystore $KeyFile `
        -storepass $Pwd -keypass $Pwd `
        -alias $Alias -keyalg RSA -keysize 2048 -validity 10000 `
        -dname $DName
    if ($LASTEXITCODE -ne 0) { Write-Host '[ERR] keytool failed'; exit 1 }
}

# Locate apksigner
$apksignerPath = $null
if (Get-Command apksigner -ErrorAction SilentlyContinue) { $apksignerPath = 'apksigner' }
else {
    $candidates = @(
        "$env:ANDROID_HOME\build-tools\35.0.0\apksigner.bat"
        "$env:ANDROID_HOME\build-tools\34.0.0\apksigner.bat"
        "$env:ANDROID_HOME\build-tools\33.0.2\apksigner.bat"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { $apksignerPath = $c; break } }
}
if (-not $apksignerPath) { Write-Host '[ERR] apksigner not found in PATH or build-tools'; exit 1 }

Write-Host "[apksigner] Signing $ApkPath ..."
& $apksignerPath sign `
    --ks $KeyFile --ks-pass "pass:$Pwd" --key-pass "pass:$Pwd" `
    --ks-key-alias $Alias `
    --out $ApkPath `
    $ApkPath
& $apksignerPath verify $ApkPath
Write-Host "[OK] Signed. Keystore: $KeyFile  Alias: $Alias  Pass: $Pwd"
Write-Host '     (Replace with real Play Store key before publishing)'

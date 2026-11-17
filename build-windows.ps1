param(
    [switch]$Sign,
    [string]$CertificateThumbprint = $env:PSRTTY_SIGN_CERT_THUMBPRINT,
    [string]$SignToolPath = $env:PSRTTY_SIGNTOOL,
    [string]$TimestampUrl = $env:PSRTTY_TIMESTAMP_URL,
    [switch]$MachineCertificateStore
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Invoke-Python {
    & python @args
    if ($LASTEXITCODE -ne 0) { throw "Python command failed (exit $LASTEXITCODE): $args" }
}

Write-Host "=== PSRTTY 1.34 Windows build ===" -ForegroundColor Cyan
Invoke-Python --version
Invoke-Python -c "from psrtty import __version__; assert __version__ == '1.34', '1.34 の実装が完了していません'"
if ($Sign -and -not $CertificateThumbprint) {
    throw '署名する証明書の拇印を -CertificateThumbprint または PSRTTY_SIGN_CERT_THUMBPRINT で指定してください。'
}
Invoke-Python -m pip install -r requirements.txt
& .\build-iq-bridge.ps1
if ($LASTEXITCODE -ne 0) { throw 'ExtIO bridge build failed' }
# Fetch the pinned upstream release if it is not already staged. SHA-256 is
# checked by vendor_hamlib.py; a failed download stops the build.
if (-not (Test-Path 'lib\hamlib\libhamlib-4.dll')) {
    Invoke-Python vendor_hamlib.py
}
Invoke-Python validate_languages.py --generate
Invoke-Python -m unittest discover -v
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
Invoke-Python -m PyInstaller --noconfirm psrtty.spec
# Execute the actual EXE before packaging; missing runtime dependencies stop here.
Invoke-Python tools\check_frozen_skimmer.py dist\psrtty.exe
# Sign before package_release creates hashes. Never modify the EXE in the ZIP.
if ($Sign -or $CertificateThumbprint) {
    $signArgs = @('-m', 'build_support.windows_signing', '--certificate-thumbprint', $CertificateThumbprint)
    if ($SignToolPath) { $signArgs += @('--signtool', $SignToolPath) }
    if ($TimestampUrl) { $signArgs += @('--timestamp-url', $TimestampUrl) }
    if ($MachineCertificateStore) { $signArgs += '--machine-store' }
    $signArgs += @('dist\psrtty.exe', 'lib\iq\psrtty-extio32.exe', 'lib\iq\psrtty-extio64.exe')
    Invoke-Python @signArgs
} else {
    Write-Warning '未署名の開発用ビルドです。1.34の公開用ZIPは -Sign を指定し、署名・検証後に作成してください。'
}
# Stage outside release. Never remove existing unpacked releases/user data.
Invoke-Python package_release.py --build dist\psrtty.exe release
Write-Host "Build complete:" -ForegroundColor Green
Write-Host "ZIP: $(Join-Path $PSScriptRoot 'release\PSRTTY_1.34.zip')"

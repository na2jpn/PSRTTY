$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Invoke-Python {
    & python @args
    if ($LASTEXITCODE -ne 0) { throw "Python command failed (exit $LASTEXITCODE): $args" }
}

Write-Host "=== PSRTTY 1.28 Windows build ===" -ForegroundColor Cyan
Invoke-Python --version
Invoke-Python -c "from psrtty import __version__; assert __version__ == '1.28', '1.28 の実装が完了していません'"
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
# Stage outside release. Never remove existing unpacked releases/user data.
Invoke-Python package_release.py --build dist\psrtty.exe release
Write-Host "Build complete:" -ForegroundColor Green
Write-Host "ZIP: $(Join-Path $PSScriptRoot 'release\PSRTTY_1.28.zip')"

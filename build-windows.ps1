$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Invoke-Python {
    & python @args
    if ($LASTEXITCODE -ne 0) { throw "Python command failed (exit $LASTEXITCODE): $args" }
}

Write-Host "=== PSRTTY 0.84 Windows build ===" -ForegroundColor Cyan
Invoke-Python --version
Invoke-Python -m pip install -r requirements.txt
Invoke-Python -m unittest discover -v
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
Invoke-Python -m PyInstaller --noconfirm psrtty.spec
# Stage outside release. Never remove existing unpacked releases/user data.
Invoke-Python package_release.py --build dist\psrtty.exe release
Write-Host "Build complete:" -ForegroundColor Green
Write-Host "ZIP: $(Join-Path $PSScriptRoot 'release\PSRTTY_0.84.zip')"

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
if (-not (Test-Path $compiler)) { throw '.NET Framework 4 C# compiler was not found.' }
New-Item -ItemType Directory -Force 'lib\iq' | Out-Null
foreach ($arch in @('x86','x64')) {
    $bits = if ($arch -eq 'x86') { '32' } else { '64' }
    & $compiler /nologo /optimize+ /target:exe "/platform:$arch" /reference:System.Windows.Forms.dll "/out:lib\iq\psrtty-extio$bits.exe" tools\ExtIOBridge.cs
    if ($LASTEXITCODE -ne 0) { throw "ExtIO bridge build failed: $arch" }
    & ".\lib\iq\psrtty-extio$bits.exe" --self-test
    if ($LASTEXITCODE -ne 0) { throw "ExtIO sample-format test failed: $arch" }
}

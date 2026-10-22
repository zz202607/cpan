# Build Cpan.exe, the portable ZIP and the per-user installer.
# Prerequisites: Python 3.13 + pip install -r requirements-build.txt
#                Inno Setup 6 (winget install JRSoftware.InnoSetup)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$version = "2.0.0"
Write-Host "==> Running safety test suite" -ForegroundColor Cyan
py -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }

Write-Host "==> Generating icon and installer artwork" -ForegroundColor Cyan
py tools\make_icon.py

Write-Host "==> Freezing Cpan.exe (PyInstaller, onedir)" -ForegroundColor Cyan
py -m PyInstaller --noconfirm --clean --windowed --onedir --noupx --name Cpan `
  --icon assets\cpan.ico --add-data "assets;assets" `
  --version-file installer\version_info.txt cpan_gui.py
Copy-Item "README.md" "dist\Cpan\README.md" -Force

Write-Host "==> Compiling installer (Inno Setup)" -ForegroundColor Cyan
$isccCandidates = @(
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
  throw "Inno Setup 6 not found. Install it with: winget install JRSoftware.InnoSetup"
}
& $iscc installer\cpan.iss
if ($LASTEXITCODE -ne 0) { throw "ISCC failed with exit code $LASTEXITCODE" }

Write-Host "==> Creating portable ZIP" -ForegroundColor Cyan
$zip = "dist\Cpan-Portable-$version.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "dist\Cpan" -DestinationPath $zip -CompressionLevel Optimal

Write-Host "==> Done" -ForegroundColor Green
Get-Item "dist\installer\Cpan-Setup-$version.exe", $zip |
  Select-Object FullName, @{n="SizeMB";e={[math]::Round($_.Length/1MB,1)}}
Get-FileHash "dist\installer\Cpan-Setup-$version.exe", $zip -Algorithm SHA256 |
  Select-Object Path, Hash

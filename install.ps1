# One-line install:  irm https://raw.githubusercontent.com/jhud172/atticus-codex-windows/main/install.ps1 | iex
# Checks the PC, downloads Atticus to %USERPROFILE%\.atticus-codex, builds it, and opens it.
$ErrorActionPreference = 'Stop'
$src = Join-Path $env:USERPROFILE '.atticus-codex'
function Need($cmd, $id, $what) {
  if (Get-Command $cmd -ErrorAction SilentlyContinue) { return }
  Write-Host "Installing $what…"
  winget install --id $id -e --silent --accept-package-agreements --accept-source-agreements | Out-Null
  $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "Could not install $what. Install it, then run this again." }
}
Need git Git.Git 'Git for Windows'
if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) { Need py Python.Python.3.12 'Python 3.12' }
if (Test-Path "$src\.git") { git -C $src pull -q --ff-only } else { git clone -q https://github.com/jhud172/atticus-codex-windows.git $src }
& powershell -NoProfile -ExecutionPolicy Bypass -File "$src\build.ps1"

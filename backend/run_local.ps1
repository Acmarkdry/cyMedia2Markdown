param(
  [ValidateSet("cpu", "gpu")]
  [string]$Role = "gpu"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvName = if ($Role -eq "gpu") { ".venv-gpu" } else { ".venv-cpu" }
$Python = Join-Path $ProjectRoot "$VenvName\Scripts\python.exe"

if (-not (Test-Path $Python)) {
  & (Join-Path $ProjectRoot "tools\setup_runtime.ps1") -Role $Role
}

& $Python (Join-Path $PSScriptRoot "app.py")
exit $LASTEXITCODE

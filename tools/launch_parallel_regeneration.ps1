param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Args
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Py = if ($env:M2M_PYTHON) {
  $env:M2M_PYTHON
} elseif (Test-Path (Join-Path $Root '.venv-cpu\Scripts\python.exe')) {
  Join-Path $Root '.venv-cpu\Scripts\python.exe'
} elseif (Test-Path (Join-Path $Root '.venv-gpu\Scripts\python.exe')) {
  Join-Path $Root '.venv-gpu\Scripts\python.exe'
} else {
  'py'
}

if ($Py -eq 'py') {
  & $Py -3.12 (Join-Path $Root 'tools\launch_parallel_regeneration.py') @Args
} else {
  & $Py (Join-Path $Root 'tools\launch_parallel_regeneration.py') @Args
}
exit $LASTEXITCODE

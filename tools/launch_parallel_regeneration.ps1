param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Args
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Py = Join-Path $Root 'backend\.venv\Scripts\python.exe'

& $Py (Join-Path $Root 'tools\launch_parallel_regeneration.py') @Args
exit $LASTEXITCODE

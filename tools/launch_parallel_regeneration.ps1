param(
  [string[]]$Slugs = @('BV1L94y197kh', 'BV1Ce4y1X7k5', 'BV1X5411V7jh', 'BV1zD4y1X77M'),
  [int]$ChunkMinutes = 12,
  [int]$LlmTimeout = 3600,
  [switch]$Shutdown
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Py = Join-Path $Root 'backend\.venv\Scripts\python.exe'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$LauncherLog = Join-Path $Root "output\parallel_launcher_$Stamp.log"

"started=$(Get-Date -Format o) slugs=$($Slugs -join ',')" | Out-File -FilePath $LauncherLog -Encoding utf8

$children = @()
foreach ($slug in $Slugs) {
  $log = Join-Path $Root "output\parallel_$slug`_$Stamp.log"
  $childScript = @"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
`$ErrorActionPreference = 'Continue'
Set-Location '$Root'
`$py = '$Py'
"started=`$(Get-Date -Format o) slug=$slug" | Out-File -FilePath '$log' -Encoding utf8
& `$py '$Root\tools\regenerate_video_notes_direct.py' --slug '$slug' --llm-timeout $LlmTimeout --chunk-minutes $ChunkMinutes *>> '$log'
`$exit = `$LASTEXITCODE
"finished=`$(Get-Date -Format o) slug=$slug exit_code=`$exit" | Out-File -FilePath '$log' -Append -Encoding utf8
exit `$exit
"@
  $process = Start-Process -FilePath powershell.exe `
    -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $childScript) `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -PassThru
  $children += $process
  "launched slug=$slug pid=$($process.Id) log=$log" | Out-File -FilePath $LauncherLog -Append -Encoding utf8
}

foreach ($child in $children) {
  try {
    Wait-Process -Id $child.Id
  } catch {
    "wait_failed pid=$($child.Id) error=$($_.Exception.Message)" | Out-File -FilePath $LauncherLog -Append -Encoding utf8
  }
  "child_done pid=$($child.Id) time=$(Get-Date -Format o)" | Out-File -FilePath $LauncherLog -Append -Encoding utf8
}

"all_children_done=$(Get-Date -Format o)" | Out-File -FilePath $LauncherLog -Append -Encoding utf8

$summary = foreach ($slug in $Slugs) {
  $qualityPath = Join-Path $Root "output\$slug\backend_video_notes_quality.json"
  $notesPath = Join-Path $Root "output\$slug\notes.md"
  $quality = $null
  if (Test-Path $qualityPath) {
    try {
      $quality = Get-Content -Encoding UTF8 $qualityPath | ConvertFrom-Json
    } catch {
      $quality = $null
    }
  }
  [pscustomobject]@{
    slug = $slug
    done = Test-Path $qualityPath
    notes_kb = if (Test-Path $notesPath) { [math]::Round((Get-Item $notesPath).Length / 1KB, 1) } else { 0 }
    passed = if ($quality) { $quality.quality.passed } else { $null }
    chars = if ($quality) { $quality.quality.chars } else { $null }
    images = if ($quality) { $quality.quality.image_markers } else { $null }
    chunked = if ($quality) { $quality.chunked } else { $null }
    chunks = if ($quality) { $quality.chunk_count } else { $null }
    retried = if ($quality) { $quality.retried } else { $null }
  }
}

$summary | ConvertTo-Json -Depth 6 | Out-File -FilePath (Join-Path $Root "output\parallel_summary_$Stamp.json") -Encoding utf8
$summary | Format-Table -AutoSize | Out-File -FilePath $LauncherLog -Append -Encoding utf8

if ($Shutdown) {
  shutdown.exe /s /t 180 /c "parallel video note regeneration finished; shutdown in 3 minutes; log: $LauncherLog"
}

param(
    [string]$QueueRoot = "",
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $ProjectRoot ".venv-cpu\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Missing CPU runtime: $Python. Run tools\setup_runtime.ps1 -Role cpu first."
}

if (-not $QueueRoot) {
    $QueueRoot = if ($env:M2M_QUEUE_ROOT) { $env:M2M_QUEUE_ROOT } else { Join-Path (Split-Path -Parent $ProjectRoot) "_queue" }
}

function Invoke-Check($Title, [scriptblock]$Block) {
    Write-Host "==> $Title"
    & $Block
}

Invoke-Check "Python version" {
    & $Python --version
}

Invoke-Check "Python compile" {
    & $Python -m py_compile `
        (Join-Path $ProjectRoot "backend\app.py") `
        (Join-Path $ProjectRoot "backend\routers\queue.py") `
        (Join-Path $ProjectRoot "tools\m2m_doctor.py") `
        (Join-Path $ProjectRoot "tools\distributed_video_notes.py") `
        (Join-Path $ProjectRoot "tools\batch_video_notes.py") `
        (Join-Path $ProjectRoot "tools\launch_parallel_regeneration.py") `
        (Join-Path $ProjectRoot "tools\regenerate_video_notes_direct.py") `
        (Join-Path $ProjectRoot "tools\rebuild_note_assets.py") `
        (Join-Path $ProjectRoot "tools\rename_output_dirs.py") `
        (Join-Path $ProjectRoot "tools\validate_video_outputs.py")
}

Invoke-Check "Backend import" {
    & $Python -c "import sys; sys.path.insert(0, r'$ProjectRoot\backend'); import app; print(app.app.title)"
}

Invoke-Check "Unit tests" {
    & $Python -m unittest discover -s (Join-Path $ProjectRoot "tests") -p "test_*.py"
}

Invoke-Check "Doctor cpu" {
    & $Python (Join-Path $ProjectRoot "tools\m2m_doctor.py") --role cpu --project-root $ProjectRoot --queue-root $QueueRoot
}

Invoke-Check "Doctor frontend" {
    & $Python (Join-Path $ProjectRoot "tools\m2m_doctor.py") --role frontend --project-root $ProjectRoot
}

Invoke-Check "Distributed worker help" {
    & cmd /c "`"$ProjectRoot\tools\distributed_video_notes.cmd`" worker --help"
}

Invoke-Check "Batch helper help" {
    & cmd /c "`"$ProjectRoot\tools\batch_video_notes.cmd`" --help"
}

Invoke-Check "Parallel helper help" {
    & cmd /c "`"$ProjectRoot\tools\parallel_regenerate.cmd`" --help"
}

if (Test-Path $QueueRoot) {
    Invoke-Check "Queue status" {
        & cmd /c "`"$ProjectRoot\tools\distributed_status.cmd`" --queue-root `"$QueueRoot`""
    }
} else {
    Write-Host "==> Queue status"
    Write-Host "SKIP: queue root does not exist: $QueueRoot"
}

if (-not $SkipFrontendBuild) {
    Invoke-Check "Frontend build" {
        Push-Location (Join-Path $ProjectRoot "frontend")
        try {
            npm run build
        } finally {
            Pop-Location
        }
    }
}

Write-Host "All quality checks completed."

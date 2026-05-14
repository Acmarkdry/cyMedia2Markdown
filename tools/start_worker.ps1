param(
    [ValidateSet("cpu", "gpu")]
    [string]$Role = "cpu",
    [string]$QueueRoot = "",
    [string]$ProjectRoot = "",
    [string]$ApiBase = "http://127.0.0.1:8080/api/v1",
    [int]$Jobs = 2,
    [int]$ChunkMinutes = 12,
    [int]$LlmTimeout = 3600,
    [Nullable[int]]$MaxTokens = $null,
    [string]$Remarks = "",
    [int]$MergeGroupSize = 3,
    [ValidateSet("opencode", "assemble")]
    [string]$MergeStrategy = "assemble",
    [int]$PollInterval = 30,
    [int]$MediaTimeout = 1800,
    [int]$LeaseSeconds = 1800,
    [int]$HeartbeatInterval = 60,
    [int]$IdleSleep = 30,
    [int]$MaxAttempts = 3,
    [int]$MaxJobs = 0,
    [Nullable[double]]$CacheAfterEpoch = $null,
    [switch]$Once,
    [switch]$DryRun,
    [switch]$IgnoreMaxAttempts,
    [switch]$ForceAsr,
    [switch]$ForceChunks,
    [switch]$NoQualityRetry,
    [switch]$ClearScreenshots
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = if ($ProjectRoot) { (Resolve-Path $ProjectRoot).Path } else { (Resolve-Path (Join-Path $ScriptRoot "..")).Path }
$QueueRoot = if ($QueueRoot) { $QueueRoot } elseif ($env:M2M_QUEUE_ROOT) { $env:M2M_QUEUE_ROOT } else { Join-Path (Split-Path -Parent $ProjectRoot) "_queue" }

function Test-IsUncPath([string]$PathToCheck) {
    return $PathToCheck.StartsWith("\\")
}

function Test-PathInside([string]$Child, [string]$Parent) {
    $childFull = [System.IO.Path]::GetFullPath($Child)
    $parentFull = [System.IO.Path]::GetFullPath($Parent)
    if (-not $parentFull.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $parentFull = $parentFull + [System.IO.Path]::DirectorySeparatorChar
    }
    return $childFull.StartsWith($parentFull, [System.StringComparison]::OrdinalIgnoreCase)
}

if ($Role -eq "gpu" -and (Test-IsUncPath $ProjectRoot)) {
    throw "GPU worker ProjectRoot must be a local clone, not an SMB path: $ProjectRoot"
}

if (-not (Test-Path $QueueRoot)) {
    New-Item -ItemType Directory -Path $QueueRoot -Force | Out-Null
}
$QueueRoot = (Resolve-Path $QueueRoot).Path

if ($ProjectRoot -eq $QueueRoot -or (Test-PathInside $ProjectRoot $QueueRoot)) {
    throw "ProjectRoot must not live inside QueueRoot. Keep the project clone and _queue directory separate."
}

$VenvName = if ($Role -eq "gpu") { ".venv-gpu" } else { ".venv-cpu" }
$Python = Join-Path $ProjectRoot "$VenvName\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Missing $Role runtime: $Python. Run tools\setup_runtime.ps1 -Role $Role first."
}

if ($Role -eq "cpu") {
    $LocalOpenCode = Join-Path $env:USERPROFILE ".local\bin\opencode.exe"
    if (Test-Path $LocalOpenCode) {
        $env:OPENCODE_CLI_PATH = $LocalOpenCode
    }
}

$DoctorArgs = @(
    (Join-Path $ProjectRoot "tools\m2m_doctor.py"),
    "--role", $Role,
    "--project-root", $ProjectRoot,
    "--queue-root", $QueueRoot
)
if ($Role -eq "gpu") {
    $DoctorArgs += @("--api-base", $ApiBase)
}
& $Python @DoctorArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$WorkerArgs = @(
    (Join-Path $ProjectRoot "tools\distributed_video_notes.py"),
    "worker",
    "--role", $Role,
    "--queue-root", $QueueRoot,
    "--project-root", $ProjectRoot,
    "--python", $Python,
    "--lease-seconds", $LeaseSeconds,
    "--heartbeat-interval", $HeartbeatInterval,
    "--idle-sleep", $IdleSleep,
    "--max-attempts", $MaxAttempts
)
if ($MaxJobs -gt 0) { $WorkerArgs += @("--max-jobs", $MaxJobs) }
if ($Once) { $WorkerArgs += "--once" }
if ($DryRun) { $WorkerArgs += "--dry-run" }
if ($IgnoreMaxAttempts) { $WorkerArgs += "--ignore-max-attempts" }

if ($Role -eq "gpu") {
    $WorkerArgs += @(
        "--api-base", $ApiBase,
        "--poll-interval", $PollInterval,
        "--media-timeout", $MediaTimeout
    )
    if ($ForceAsr) { $WorkerArgs += "--force-asr" }
} else {
    $WorkerArgs += @(
        "--jobs", $Jobs,
        "--chunk-minutes", $ChunkMinutes,
        "--llm-timeout", $LlmTimeout,
        "--merge-group-size", $MergeGroupSize,
        "--merge-strategy", $MergeStrategy
    )
    if ($MaxTokens -ne $null) { $WorkerArgs += @("--max-tokens", $MaxTokens) }
    if ($Remarks) { $WorkerArgs += @("--remarks", $Remarks) }
    if ($NoQualityRetry) { $WorkerArgs += "--no-quality-retry" }
    if (-not $ClearScreenshots) { $WorkerArgs += "--no-clear-screenshots" }
    if ($ForceChunks) { $WorkerArgs += "--force-chunks" }
    if ($CacheAfterEpoch -ne $null) { $WorkerArgs += @("--cache-after-epoch", $CacheAfterEpoch) }
}

& $Python @WorkerArgs
exit $LASTEXITCODE

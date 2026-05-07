param(
    [ValidateSet("cpu", "gpu", "frontend", "all")]
    [string]$Role = "cpu",
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RequiredPython = "3.12"

function Invoke-Step($Title, [scriptblock]$Block) {
    Write-Host "==> $Title"
    & $Block
}

function Assert-UnderProjectRoot([string]$PathToCheck) {
    $fullPath = [System.IO.Path]::GetFullPath($PathToCheck)
    $rootPath = [System.IO.Path]::GetFullPath($ProjectRoot)
    if (-not $rootPath.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $rootPath = $rootPath + [System.IO.Path]::DirectorySeparatorChar
    }
    if (-not $fullPath.StartsWith($rootPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify path outside project root: $fullPath"
    }
}

function New-ProjectVenv([string]$Name, [string]$Requirements) {
    $venv = Join-Path $ProjectRoot $Name
    py "-$RequiredPython" --version | Out-Host
    if ($Recreate -and (Test-Path $venv)) {
        Assert-UnderProjectRoot $venv
        Remove-Item -LiteralPath $venv -Recurse -Force
    }
    if (-not (Test-Path $venv)) {
        Invoke-Step "Create $Name with py -$RequiredPython" {
            py "-$RequiredPython" -m venv $venv
        }
    }
    $pythonExe = Join-Path $venv "Scripts\python.exe"
    Invoke-Step "Upgrade packaging tools in $Name" {
        & $pythonExe -m pip install --upgrade pip setuptools wheel
    }
    Invoke-Step "Install $Requirements into $Name" {
        & $pythonExe -m pip install -r (Join-Path $ProjectRoot $Requirements)
    }
    Invoke-Step "Verify $Name" {
        & $pythonExe --version
        & $pythonExe -m pip --version
    }
}

if ($Role -eq "cpu" -or $Role -eq "all") {
    New-ProjectVenv ".venv-cpu" "backend\requirements-cpu.txt"
}

if ($Role -eq "gpu" -or $Role -eq "all") {
    New-ProjectVenv ".venv-gpu" "backend\requirements-gpu.txt"
}

if ($Role -eq "frontend" -or $Role -eq "all") {
    Invoke-Step "Install frontend dependencies" {
        Push-Location (Join-Path $ProjectRoot "frontend")
        try {
            npm install
        } finally {
            Pop-Location
        }
    }
}

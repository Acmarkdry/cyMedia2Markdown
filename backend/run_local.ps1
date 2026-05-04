$ErrorActionPreference = "Stop"

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
  Write-Error "Codex CLI not found. Install Codex CLI and run 'codex login' first."
}

if (-not (Test-Path ".venv")) {
  py -3 -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py

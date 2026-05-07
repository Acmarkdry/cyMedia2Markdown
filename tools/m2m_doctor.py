# -*- coding: utf-8 -*-
"""Runtime contract checks for AI-Media2Doc distributed workers."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_BASE = "http://127.0.0.1:8080/api/v1"
REQUIRED_PYTHON_PREFIX = "Python 3.12."


def run_ok(command: list[str], timeout: int = 12) -> tuple[bool, str]:
    executable = shutil.which(command[0]) if len(command) == 1 or not Path(command[0]).exists() else command[0]
    if not executable:
        return False, f"{command[0]} not found"
    try:
        completed = subprocess.run([executable, *command[1:]], capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = (completed.stdout or completed.stderr or "").strip()
    return completed.returncode == 0, output


def is_unc(path: Path | str) -> bool:
    return str(path).startswith("\\\\")


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def python_candidates(project_root: Path, role: str) -> list[Path]:
    names = {
        "cpu": [".venv-cpu"],
        "gpu": [".venv-gpu"],
        "all": [".venv-cpu", ".venv-gpu"],
    }[role]
    return [
        *(project_root / name / "Scripts" / "python.exe" for name in names),
    ]


def first_working_python(project_root: Path, role: str) -> tuple[Path | None, list[dict]]:
    rows = []
    for candidate in python_candidates(project_root, role):
        exists = candidate.exists()
        executable_ok, output = run_ok([str(candidate), "--version"]) if exists else (False, "missing")
        version_ok = executable_ok and output.startswith(REQUIRED_PYTHON_PREFIX)
        rows.append({"path": str(candidate), "exists": exists, "ok": version_ok, "version": output})
        if version_ok:
            return candidate, rows
    return None, rows


def health_url(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/api/v1"):
        return f"{base[:-len('/api/v1')]}/health"
    return f"{base}/health"


def check_health(api_base: str) -> tuple[bool, str]:
    url = health_url(api_base)
    try:
        with urlopen(url, timeout=8) as response:
            return 200 <= response.status < 300, f"{url} HTTP {response.status}"
    except (OSError, URLError) as exc:
        return False, f"{url} unreachable: {exc}"


def queue_layout(queue_root: Path) -> dict:
    return {
        name: (queue_root / name).exists()
        for name in ["jobs", "artifacts", "logs", "work", "work/manifests"]
    }


def build_report(args: argparse.Namespace) -> dict:
    project_root = Path(args.project_root).resolve()
    queue_root = Path(args.queue_root).resolve() if args.queue_root else None
    role = args.role
    errors: list[str] = []
    warnings: list[str] = []

    if not project_root.exists():
        errors.append(f"project_root does not exist: {project_root}")
    for name in ["backend", "frontend", "tools"]:
        if not (project_root / name).exists():
            errors.append(f"project_root missing {name}/: {project_root}")

    if queue_root:
        layout = queue_layout(queue_root)
        if not queue_root.exists():
            errors.append(f"queue_root does not exist: {queue_root}")
        if project_root == queue_root or is_relative_to(project_root, queue_root):
            errors.append(
                "project_root must not be inside queue_root. Use a dedicated queue directory such as "
                "D:\\m2m_queue\\_queue, and keep the project clone outside that queue root."
            )
        if any(layout.values()) and not all(layout.values()):
            warnings.append(f"queue_root layout is partial: {layout}")
    else:
        layout = {}

    if role in {"gpu", "all"} and is_unc(project_root):
        errors.append("GPU prepare project_root must be a local project path, not an SMB/UNC path.")

    python, python_rows = first_working_python(project_root, "cpu" if role == "frontend" else role)
    if role in {"cpu", "gpu", "all"} and not python:
        errors.append("No runnable Python 3.12.x environment found.")

    codex = os.environ.get("CODEX_CLI_PATH") or shutil.which("codex.cmd") or shutil.which("codex.exe") or shutil.which("codex")
    codex_ok, codex_version = (run_ok([codex, "--version"]) if codex else (False, "missing"))
    if role in {"cpu", "all"} and not codex_ok:
        errors.append("Codex CLI is missing or not executable. Set CODEX_CLI_PATH or fix PATH.")

    node_ok, node_version = run_ok(["node", "--version"])
    npm_ok, npm_version = run_ok(["npm", "--version"])
    if role in {"frontend", "all"}:
        if not node_ok:
            errors.append("node is missing or not executable.")
        if not npm_ok:
            errors.append("npm is missing or not executable.")

    backend_ok = None
    backend_message = ""
    if role in {"gpu", "all"}:
        backend_ok, backend_message = check_health(args.api_base)
        if not backend_ok:
            errors.append(f"GPU backend health check failed: {backend_message}")

    return {
        "ok": not errors,
        "role": role,
        "project_root": str(project_root),
        "queue_root": str(queue_root) if queue_root else "",
        "errors": errors,
        "warnings": warnings,
        "python": {"selected": str(python) if python else "", "candidates": python_rows},
        "codex": {"path": codex or "", "ok": codex_ok, "version": codex_version},
        "node": {"ok": node_ok, "version": node_version},
        "npm": {"ok": npm_ok, "version": npm_version},
        "backend": {"checked": backend_ok is not None, "ok": backend_ok, "message": backend_message},
        "queue_layout": layout,
    }


def print_human(report: dict) -> None:
    print(f"AI-Media2Doc doctor: {'OK' if report['ok'] else 'FAILED'}")
    print(f"role: {report['role']}")
    print(f"project_root: {report['project_root']}")
    if report["queue_root"]:
        print(f"queue_root: {report['queue_root']}")
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")
    for error in report["errors"]:
        print(f"ERROR: {error}")
    print(f"python: {report['python']['selected'] or 'not found'}")
    print(f"codex: {report['codex']['path'] or 'not found'} ({report['codex']['version']})")
    print(f"node: {report['node']['version']}")
    print(f"npm: {report['npm']['version']}")
    if report["backend"]["checked"]:
        print(f"backend: {report['backend']['message']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AI-Media2Doc runtime contract.")
    parser.add_argument("--role", choices=["cpu", "gpu", "frontend", "all"], default="cpu")
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--queue-root", type=Path)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_report(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

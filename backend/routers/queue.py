# -*- coding: UTF-8 -*-
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

import env
from config.log import get_logger
from core.response import APIResponse, success_response

router = APIRouter(prefix="/queue", tags=["queue"])
logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_PYTHON = "3.12.x"
DEFAULT_QUEUE_ROOT = (PROJECT_ROOT.parent / "_queue").resolve()
STATE_ORDER = {
    "queued": 0,
    "prepare_running": 1,
    "prepare_failed": 1,
    "prepared": 2,
    "codex_running": 3,
    "codex_failed": 3,
    "done": 4,
}
RUNNING_STATES = {"prepare_running", "codex_running"}
FAILED_STATES = {"prepare_failed", "codex_failed"}


def iso_time(value: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value or time.time()))


def resolve_queue_root() -> Path:
    configured = (env.M2M_QUEUE_ROOT or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_QUEUE_ROOT


def safe_load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read queue job: %s", path)
        return None
    return data if isinstance(data, dict) else None


def iter_job_paths(queue_root: Path) -> list[Path]:
    jobs_dir = queue_root / "jobs"
    if not jobs_dir.exists():
        return []
    return sorted(path for path in jobs_dir.glob("*.json") if path.is_file())


def extract_sort_index(job: dict[str, Any]) -> int:
    candidates = [
        str(job.get("source_id") or ""),
        str(job.get("job_id") or ""),
        str(job.get("slug") or ""),
    ]
    for value in candidates:
        match = re.search(r"(?:^|[_\s-])p(\d+)(?:\D|$)", value, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 999999


def parse_events(queue_root: Path, job_id: str, limit: int = 8) -> list[dict[str, Any]]:
    path = queue_root / "logs" / f"{job_id}.jsonl"
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        logger.exception("Failed to read queue event log: %s", path)
        return []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def stage_status(job: dict[str, Any], stage: str) -> str:
    state = str(job.get("state") or "")
    if stage == "prepare":
        if state in {"prepared", "codex_running", "codex_failed", "done"}:
            return "success"
        if state == "prepare_running":
            return "running"
        if state == "prepare_failed":
            return "failed"
        return "waiting"
    if stage == "codex":
        if state == "done":
            return "success"
        if state == "codex_running":
            return "running"
        if state == "codex_failed":
            return "failed"
        if state in {"prepared", "prepare_running", "prepare_failed"}:
            return "waiting"
        return "blocked" if state == "queued" else "waiting"
    return "waiting"


def build_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    history = job.get("history") if isinstance(job.get("history"), list) else []
    prepare_claim = next(
        (item for item in reversed(history) if item.get("stage") == "prepare" and item.get("event") == "claimed"),
        None,
    )
    codex_claim = next(
        (item for item in reversed(history) if item.get("stage") == "codex" and item.get("event") == "claimed"),
        None,
    )
    return [
        {
            "key": "queued",
            "label": "入队",
            "status": "success",
            "time": job.get("created_at_iso"),
        },
        {
            "key": "prepare",
            "label": "准备媒体/ASR",
            "status": stage_status(job, "prepare"),
            "time": job.get("prepare_completed_at_iso") or (prepare_claim or {}).get("time"),
            "owner": (prepare_claim or {}).get("owner"),
        },
        {
            "key": "codex",
            "label": "生成笔记",
            "status": stage_status(job, "codex"),
            "time": job.get("codex_completed_at_iso") or (codex_claim or {}).get("time"),
            "owner": (codex_claim or {}).get("owner"),
        },
        {
            "key": "done",
            "label": "完成",
            "status": "success" if job.get("state") == "done" else "waiting",
            "time": job.get("codex_completed_at_iso") if job.get("state") == "done" else None,
        },
    ]


def normalize_job(queue_root: Path, job: dict[str, Any]) -> dict[str, Any]:
    state = str(job.get("state") or "unknown")
    attempts = job.get("attempts") if isinstance(job.get("attempts"), dict) else {}
    lease_until = job.get("lease_until")
    lease_expired = bool(state in RUNNING_STATES and lease_until and float(lease_until) < time.time())
    last_error = job.get("last_error") if isinstance(job.get("last_error"), dict) else None
    recent_events = parse_events(queue_root, str(job.get("job_id") or ""))
    paths = job.get("paths") if isinstance(job.get("paths"), dict) else {}
    video = job.get("video") if isinstance(job.get("video"), dict) else {}
    sort_index = extract_sort_index(job)

    return {
        "job_id": job.get("job_id"),
        "state": state,
        "state_order": STATE_ORDER.get(state, 99),
        "source_id": job.get("source_id"),
        "slug": job.get("slug"),
        "title": job.get("title") or video.get("title") or job.get("slug") or job.get("job_id"),
        "url": video.get("url"),
        "sort_index": sort_index,
        "owner": job.get("owner"),
        "lease_until": lease_until,
        "lease_until_iso": job.get("lease_until_iso"),
        "lease_expired": lease_expired,
        "last_heartbeat": job.get("last_heartbeat"),
        "last_heartbeat_iso": job.get("last_heartbeat_iso"),
        "updated_at": job.get("updated_at"),
        "updated_at_iso": job.get("updated_at_iso"),
        "created_at": job.get("created_at"),
        "created_at_iso": job.get("created_at_iso"),
        "prepare_completed_at_iso": job.get("prepare_completed_at_iso"),
        "codex_completed_at_iso": job.get("codex_completed_at_iso"),
        "prepare_attempts": int(attempts.get("prepare") or 0),
        "codex_attempts": int(attempts.get("codex") or 0),
        "last_error": last_error,
        "paths": paths,
        "steps": build_steps(job),
        "recent_events": recent_events,
    }


def state_summary(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    definitions = [
        ("queued", "待准备"),
        ("prepare_running", "准备中"),
        ("prepared", "待生成"),
        ("codex_running", "生成中"),
        ("done", "已完成"),
        ("prepare_failed", "准备失败"),
        ("codex_failed", "生成失败"),
    ]
    return [
        {
            "state": state,
            "label": label,
            "count": sum(1 for job in jobs if job["state"] == state),
        }
        for state, label in definitions
    ]


def runtime_contract(queue_root: Path) -> dict[str, Any]:
    share_root = queue_root.parent
    project_name = PROJECT_ROOT.name
    backend_root = PROJECT_ROOT / "backend"
    queue_layout = {
        "jobs": str(queue_root / "jobs"),
        "artifacts": str(queue_root / "artifacts"),
        "logs": str(queue_root / "logs"),
        "work": str(queue_root / "work"),
    }
    backend_storage = {
        "uploads": str(backend_root / env.LOCAL_UPLOAD_DIR),
        "media": str(backend_root / env.LOCAL_MEDIA_DIR),
        "screenshots": str(backend_root / env.LOCAL_SCREENSHOT_DIR),
        "logs": str(backend_root / env.LOG_DIR),
    }
    storage_contract = {
        "share_root": str(share_root),
        "project_root": str(PROJECT_ROOT),
        "queue_root": str(queue_root),
        "final_output_root": str(PROJECT_ROOT / "output"),
        "backend_storage": backend_storage,
        "queue_layout": queue_layout,
        "artifact_output_pattern": str(queue_root / "artifacts" / "<job_id>" / "output" / "<video_slug>"),
        "artifact_media_pattern": str(queue_root / "artifacts" / "<job_id>" / "media" / "<video_file>"),
    }
    return {
        "required_python": REQUIRED_PYTHON,
        "project_root": str(PROJECT_ROOT),
        "queue_root": str(queue_root),
        "share_root": str(share_root),
        "queue_layout": queue_layout,
        "storage_contract": storage_contract,
        "local_media_dir": backend_storage["media"],
        "cpu_venv": str(PROJECT_ROOT / ".venv-cpu"),
        "gpu_venv": str(PROJECT_ROOT / ".venv-gpu"),
        "current_python": sys.version.split()[0],
        "commands": {
            "setup_cpu": r"tools\setup_runtime.ps1 -Role cpu",
            "setup_gpu": r"tools\setup_runtime.ps1 -Role gpu",
            "setup_frontend": r"tools\setup_runtime.ps1 -Role frontend",
            "doctor_cpu": rf"tools\m2m_doctor.py --role cpu --project-root {PROJECT_ROOT} --queue-root {queue_root}",
            "doctor_gpu": rf"tools\m2m_doctor.py --role gpu --project-root D:\Local\{project_name} --queue-root \\MINIPC\m2m_queue\_queue",
            "start_cpu": rf"tools\start_worker.ps1 -Role cpu -QueueRoot {queue_root}",
            "start_gpu": rf"tools\start_worker.ps1 -Role gpu -QueueRoot \\MINIPC\m2m_queue\_queue -ProjectRoot D:\Local\{project_name}",
        },
    }


@router.get("/status", response_model=APIResponse)
async def queue_status(include_events: bool = Query(True)) -> APIResponse:
    queue_root = resolve_queue_root()
    jobs = []
    for path in iter_job_paths(queue_root):
        job = safe_load_json(path)
        if not job:
            continue
        normalized = normalize_job(queue_root, job)
        if not include_events:
            normalized["recent_events"] = []
        jobs.append(normalized)

    jobs.sort(key=lambda item: (item["sort_index"], str(item.get("job_id") or "")))
    counts: dict[str, int] = {}
    for job in jobs:
        counts[job["state"]] = counts.get(job["state"], 0) + 1

    running_jobs = [job for job in jobs if job["state"] in RUNNING_STATES]
    failed_jobs = [job for job in jobs if job["state"] in FAILED_STATES]
    todo_jobs = [job for job in jobs if job["state"] in {"queued", "prepared"}]
    current_jobs = running_jobs or todo_jobs[:1]
    total = len(jobs)
    done = counts.get("done", 0)

    data = {
        "queue_root": str(queue_root),
        "refreshed_at": iso_time(),
        "contract": runtime_contract(queue_root),
        "counts": counts,
        "summary": {
            "total": total,
            "done": done,
            "running": len(running_jobs),
            "failed": len(failed_jobs),
            "todo": len(todo_jobs),
            "prepared": counts.get("prepared", 0),
            "queued": counts.get("queued", 0),
            "progress_percent": round((done / total) * 100) if total else 0,
        },
        "states": state_summary(jobs),
        "current_jobs": current_jobs,
        "running_jobs": running_jobs,
        "todo_jobs": todo_jobs,
        "failed_jobs": failed_jobs,
        "jobs": jobs,
    }
    return success_response(data=data, message="Queue status loaded")

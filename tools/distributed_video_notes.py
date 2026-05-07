# -*- coding: utf-8 -*-
"""Durable file-queue workers for distributed video-note generation.

The distributed mode keeps the existing processing pipeline intact:

* prepare workers run ``batch_video_notes.py --skip-codex`` on GPU machines.
* codex workers run ``regenerate_video_notes_direct.py`` on CPU/Codex machines.

Coordination happens through a shared directory that can live on an SMB share.
Each job is one JSON file. Workers claim jobs with short directory locks and
keep long-running subprocess ownership through renewable leases.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import urlopen

from video_manifest import ascii_slug, load_manifest, safe_output_name


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_BASE = "http://127.0.0.1:8080/api/v1"
SCHEMA_VERSION = 1
RUNNING_STATES = {"prepare_running", "codex_running"}
REQUIRED_PYTHON_PREFIX = "Python 3.12."


def now() -> float:
    return time.time()


def iso_time(value: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value or now()))


def worker_id(role: str) -> str:
    return f"{role}:{socket.gethostname()}:{os.getpid()}"


def run_command(command: Path | str, args: list[str] | None = None, timeout: int = 15) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            [str(command), *(args or ["--version"])],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    output = (completed.stdout or completed.stderr or "").strip()
    return completed.returncode == 0, output


def executable_works(command: Path | str, args: list[str] | None = None, timeout: int = 15) -> bool:
    ok, _ = run_command(command, args, timeout)
    return ok


def python_version_ok(python_exe: Path) -> tuple[bool, str]:
    ok, output = run_command(python_exe, ["--version"])
    return ok and output.startswith(REQUIRED_PYTHON_PREFIX), output


def default_python(project_root: Path, role: str = "worker") -> Path:
    role_envs = {
        "prepare": [".venv-gpu"],
        "codex": [".venv-cpu"],
        "worker": [".venv-cpu", ".venv-gpu"],
    }
    names = role_envs.get(role, role_envs["worker"])
    candidates = [
        *(project_root / name / "Scripts" / "python.exe" for name in names),
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate.exists() and python_version_ok(candidate)[0]:
            return candidate
    return Path(sys.executable)


def resolve_project_root(value: str | Path | None) -> Path:
    return Path(value).resolve() if value else ROOT


def is_unc_path(path: Path | str) -> bool:
    return str(path).startswith("\\\\")


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def codex_command() -> str | None:
    explicit = os.environ.get("CODEX_CLI_PATH")
    if explicit:
        return explicit
    return shutil.which("codex.cmd") or shutil.which("codex.exe") or shutil.which("codex")


def health_url_from_api_base(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/api/v1"):
        return f"{base[:-len('/api/v1')]}/health"
    return f"{base}/health"


def check_backend_health(api_base: str, timeout: int = 8) -> tuple[bool, str]:
    url = health_url_from_api_base(api_base)
    try:
        with urlopen(url, timeout=timeout) as response:
            if 200 <= response.status < 300:
                return True, url
            return False, f"{url} returned HTTP {response.status}"
    except (OSError, URLError) as exc:
        return False, f"{url} is not reachable: {exc}"


def preflight_worker(args: argparse.Namespace, role: str) -> Path:
    project_root = resolve_project_root(args.project_root)
    queue_root = Path(args.queue_root).resolve()
    problems: list[str] = []
    warnings: list[str] = []

    if not project_root.exists():
        problems.append(f"project root does not exist: {project_root}")
    for required in ["tools", "backend"]:
        if not (project_root / required).exists():
            problems.append(f"project root is missing {required}/: {project_root}")

    if role == "prepare" and is_unc_path(project_root):
        problems.append(
            "GPU worker --project-root must be a local path on the GPU machine. "
            "Keep --queue-root on SMB, but run project-root from the GPU host clone."
        )
    if project_root == queue_root or is_relative_to(project_root, queue_root):
        problems.append(
            "project-root must not be inside queue-root. Use a dedicated queue root such as "
            "D:\\m2m_queue\\_queue, and pass the local project clone as --project-root."
        )

    python_exe = Path(args.python) if args.python else default_python(project_root, role)
    if not python_exe.exists():
        problems.append(f"python executable does not exist: {python_exe}")
    else:
        ok, version = python_version_ok(python_exe)
        if not ok:
            problems.append(
                f"python executable must be Python 3.12.x: {python_exe} reported {version or 'unavailable'}"
            )
    args.python = python_exe

    if role == "prepare":
        ok, message = check_backend_health(args.api_base)
        if not ok:
            problems.append(f"backend health check failed: {message}")
    if role == "codex":
        command = codex_command()
        if not command:
            problems.append("Codex CLI is not on PATH and CODEX_CLI_PATH is not set.")
        elif not executable_works(command, ["--version"]):
            problems.append(f"Codex CLI cannot run: {command}")

    payload = {
        "event": "preflight",
        "role": role,
        "project_root": str(project_root),
        "queue_root": str(queue_root),
        "python": str(python_exe),
        "warnings": warnings,
    }
    print(json.dumps(payload, ensure_ascii=False))
    if problems:
        raise SystemExit("Preflight failed:\n- " + "\n- ".join(problems))
    return python_exe


def ensure_layout(queue_root: Path) -> None:
    for name in ["jobs", "artifacts", "logs", "work", "work/manifests"]:
        (queue_root / name).mkdir(parents=True, exist_ok=True)


def atomic_write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def job_path(queue_root: Path, job_id: str) -> Path:
    return queue_root / "jobs" / f"{job_id}.json"


def iter_job_paths(queue_root: Path) -> list[Path]:
    jobs_dir = queue_root / "jobs"
    if not jobs_dir.exists():
        return []
    return sorted(path for path in jobs_dir.glob("*.json") if path.is_file())


def load_job(path: Path) -> dict[str, Any]:
    job = load_json(path)
    job.setdefault("attempts", {})
    job.setdefault("history", [])
    return job


def event_log_path(queue_root: Path, job_id: str) -> Path:
    return queue_root / "logs" / f"{job_id}.jsonl"


def append_event(queue_root: Path, job: dict[str, Any], event: dict[str, Any]) -> None:
    payload = {
        "time": iso_time(),
        "epoch": now(),
        "job_id": job.get("job_id"),
        "state": job.get("state"),
        **event,
    }
    path = event_log_path(queue_root, str(job["job_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


class JobFileLock:
    """Short critical-section lock around one job file.

    Directory creation is the only cross-process primitive used here because it
    works reliably enough over Windows SMB shares. The lock is intentionally
    short-lived; long-running work is guarded by the job lease in the JSON.
    """

    def __init__(self, job_file: Path, owner: str, timeout: float = 30.0, stale_after: float = 120.0):
        self.job_file = job_file
        self.lock_dir = job_file.with_name(f"{job_file.name}.lock")
        self.owner = owner
        self.timeout = timeout
        self.stale_after = stale_after

    def __enter__(self) -> "JobFileLock":
        deadline = now() + self.timeout
        while True:
            try:
                self.lock_dir.mkdir()
                atomic_write_json(
                    self.lock_dir / "owner.json",
                    {"owner": self.owner, "pid": os.getpid(), "created_at": now(), "created_at_iso": iso_time()},
                )
                return self
            except FileExistsError:
                self._break_stale_lock()
                if now() >= deadline:
                    raise TimeoutError(f"Timed out waiting for lock: {self.lock_dir}")
                time.sleep(0.2)

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            owner_path = self.lock_dir / "owner.json"
            if owner_path.exists():
                owner_path.unlink()
            self.lock_dir.rmdir()
        except OSError:
            pass

    def _break_stale_lock(self) -> None:
        try:
            age = now() - self.lock_dir.stat().st_mtime
        except OSError:
            return
        if age < self.stale_after:
            return
        try:
            for child in self.lock_dir.iterdir():
                if child.is_file():
                    child.unlink()
            self.lock_dir.rmdir()
        except OSError:
            pass


def with_job_lock(
    queue_root: Path,
    job_id: str,
    owner: str,
    update: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> dict[str, Any] | None:
    path = job_path(queue_root, job_id)
    if not path.exists():
        return None
    with JobFileLock(path, owner):
        job = load_job(path)
        updated = update(job)
        if updated is None:
            return None
        updated["updated_at"] = now()
        updated["updated_at_iso"] = iso_time(updated["updated_at"])
        atomic_write_json(path, updated)
        return updated


def make_job_id(video: dict[str, Any], index: int, used: set[str]) -> str:
    base = ascii_slug(str(video.get("source_id") or video.get("slug") or ""), f"job-{index + 1:04d}")
    job_id = base
    suffix = 2
    while job_id in used:
        job_id = f"{base}-{suffix}"
        suffix += 1
    used.add(job_id)
    return job_id


def enqueue(args: argparse.Namespace) -> int:
    queue_root = Path(args.queue_root).resolve()
    ensure_layout(queue_root)
    videos = load_manifest(args.manifest)
    used: set[str] = set()
    created = 0
    updated = 0
    for index, video in enumerate(videos):
        job_id = make_job_id(video, index, used)
        path = job_path(queue_root, job_id)
        if path.exists() and not args.replace:
            existing = load_job(path)
            existing["video"] = video
            existing["title"] = video.get("title")
            existing["source_id"] = video.get("source_id")
            existing["slug"] = video.get("slug")
            existing["updated_at"] = now()
            existing["updated_at_iso"] = iso_time(existing["updated_at"])
            atomic_write_json(path, existing)
            updated += 1
            continue
        payload = {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "state": "queued",
            "video": video,
            "source_id": video.get("source_id"),
            "slug": video.get("slug"),
            "title": video.get("title"),
            "attempts": {"prepare": 0, "codex": 0},
            "created_at": now(),
            "created_at_iso": iso_time(),
            "updated_at": now(),
            "updated_at_iso": iso_time(),
            "owner": None,
            "lease_until": None,
            "last_heartbeat": None,
            "last_error": None,
            "paths": {},
            "history": [],
        }
        atomic_write_json(path, payload)
        append_event(queue_root, payload, {"event": "enqueued"})
        created += 1
    print(json.dumps({"queue_root": str(queue_root), "created": created, "updated": updated}, ensure_ascii=False))
    return 0


def running_stage_for_state(state: str) -> str | None:
    if state == "prepare_running":
        return "prepare"
    if state == "codex_running":
        return "codex"
    return None


def is_lease_expired(job: dict[str, Any]) -> bool:
    lease_until = job.get("lease_until")
    return bool(lease_until and float(lease_until) < now())


def claim_job(queue_root: Path, stage: str, owner: str, args: argparse.Namespace) -> dict[str, Any] | None:
    if stage == "prepare":
        eligible = {"queued", "prepare_failed"}
        running = "prepare_running"
    elif stage == "codex":
        eligible = {"prepared", "codex_failed"}
        running = "codex_running"
    else:
        raise ValueError(stage)

    for path in iter_job_paths(queue_root):
        job_id = path.stem

        def update(job: dict[str, Any]) -> dict[str, Any] | None:
            state = str(job.get("state") or "")
            attempts = job.setdefault("attempts", {})
            stale = state == running and is_lease_expired(job)
            if state not in eligible and not stale:
                return None
            if int(attempts.get(stage, 0)) >= args.max_attempts and not args.ignore_max_attempts:
                return None
            attempts[stage] = int(attempts.get(stage, 0)) + 1
            previous_owner = job.get("owner")
            job["state"] = running
            job["owner"] = owner
            job["lease_until"] = now() + args.lease_seconds
            job["lease_until_iso"] = iso_time(job["lease_until"])
            job["last_heartbeat"] = now()
            job["last_heartbeat_iso"] = iso_time(job["last_heartbeat"])
            job["last_error"] = None
            job.setdefault("history", []).append(
                {
                    "time": iso_time(),
                    "event": "claimed",
                    "stage": stage,
                    "owner": owner,
                    "stale_reclaim": stale,
                    "previous_owner": previous_owner,
                    "attempt": attempts[stage],
                }
            )
            return job

        claimed = with_job_lock(queue_root, job_id, owner, update)
        if claimed:
            append_event(queue_root, claimed, {"event": "claimed", "stage": stage, "owner": owner})
            return claimed
    return None


def heartbeat_job(queue_root: Path, job_id: str, stage: str, owner: str, lease_seconds: int) -> bool:
    running_state = f"{stage}_running"

    def update(job: dict[str, Any]) -> dict[str, Any] | None:
        if job.get("state") != running_state or job.get("owner") != owner:
            return None
        job["lease_until"] = now() + lease_seconds
        job["lease_until_iso"] = iso_time(job["lease_until"])
        job["last_heartbeat"] = now()
        job["last_heartbeat_iso"] = iso_time(job["last_heartbeat"])
        return job

    return with_job_lock(queue_root, job_id, owner, update) is not None


def finish_job(
    queue_root: Path,
    job_id: str,
    stage: str,
    owner: str,
    success: bool,
    log_path: Path,
    exit_code: int,
    error: str | None = None,
    paths: dict[str, Any] | None = None,
) -> None:
    running_state = f"{stage}_running"
    success_state = "prepared" if stage == "prepare" else "done"
    failed_state = "prepare_failed" if stage == "prepare" else "codex_failed"

    def update(job: dict[str, Any]) -> dict[str, Any] | None:
        if job.get("state") != running_state or job.get("owner") != owner:
            return None
        job["state"] = success_state if success else failed_state
        job["owner"] = None
        job["lease_until"] = None
        job["lease_until_iso"] = None
        job["last_heartbeat"] = now()
        job["last_heartbeat_iso"] = iso_time(job["last_heartbeat"])
        if paths:
            job.setdefault("paths", {}).update(paths)
        if job.get("paths"):
            job["paths"] = normalize_artifact_paths(queue_root, job)
        if success:
            job["last_error"] = None
            job[f"{stage}_completed_at"] = now()
            job[f"{stage}_completed_at_iso"] = iso_time(job[f"{stage}_completed_at"])
        else:
            job["last_error"] = {
                "stage": stage,
                "message": error or f"{stage} failed",
                "exit_code": exit_code,
                "log": str(log_path),
                "time": iso_time(),
            }
        job.setdefault("history", []).append(
            {
                "time": iso_time(),
                "event": "finished",
                "stage": stage,
                "success": success,
                "exit_code": exit_code,
                "log": str(log_path),
            }
        )
        return job

    updated = with_job_lock(queue_root, job_id, owner, update)
    if updated:
        append_event(
            queue_root,
            updated,
            {"event": "finished", "stage": stage, "success": success, "exit_code": exit_code, "log": str(log_path)},
        )


def release_dry_run_claim(queue_root: Path, job_id: str, stage: str, owner: str) -> None:
    running_state = f"{stage}_running"
    previous_state = "queued" if stage == "prepare" else "prepared"

    def update(job: dict[str, Any]) -> dict[str, Any] | None:
        if job.get("state") != running_state or job.get("owner") != owner:
            return None
        attempts = job.setdefault("attempts", {})
        attempts[stage] = max(0, int(attempts.get(stage, 0)) - 1)
        job["state"] = previous_state
        job["owner"] = None
        job["lease_until"] = None
        job["lease_until_iso"] = None
        job["last_error"] = None
        job.setdefault("history", []).append({"time": iso_time(), "event": "dry-run-release", "stage": stage, "owner": owner})
        return job

    updated = with_job_lock(queue_root, job_id, owner, update)
    if updated:
        append_event(queue_root, updated, {"event": "dry-run-release", "stage": stage})


def command_log_path(queue_root: Path, job_id: str, stage: str) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return queue_root / "logs" / f"{job_id}_{stage}_{stamp}.log"


def run_with_heartbeat(
    command: list[str],
    cwd: Path,
    log_path: Path,
    queue_root: Path,
    job_id: str,
    stage: str,
    owner: str,
    lease_seconds: int,
    heartbeat_interval: int,
) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(json.dumps({"stage": stage, "command": command, "cwd": str(cwd), "time": iso_time()}, ensure_ascii=False) + "\n")
        log_file.flush()
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            env=env,
        )
        while True:
            exit_code = process.poll()
            if exit_code is not None:
                log_file.write(json.dumps({"stage": stage, "event": "process-exit", "exit_code": exit_code}, ensure_ascii=False) + "\n")
                log_file.flush()
                return int(exit_code)
            if not heartbeat_job(queue_root, job_id, stage, owner, lease_seconds):
                log_file.write(
                    json.dumps(
                        {"stage": stage, "event": "lease-lost", "owner": owner, "action": "terminate"},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                log_file.flush()
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                return 88
            time.sleep(max(1, heartbeat_interval))


def write_single_manifest(queue_root: Path, job: dict[str, Any]) -> Path:
    manifest_path = queue_root / "work" / "manifests" / f"{job['job_id']}.json"
    atomic_write_json(manifest_path, {"videos": [job["video"]]})
    return manifest_path


def copy_file_if_needed(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        try:
            src_stat = src.stat()
            dst_stat = dst.stat()
            if src_stat.st_size == dst_stat.st_size and src_stat.st_mtime <= dst_stat.st_mtime + 1:
                return
        except OSError:
            pass
    shutil.copy2(src, dst)


def copy_tree_merge(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(src)
    dst.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        target = dst / child.name
        if child.is_dir():
            copy_tree_merge(child, target)
        elif child.is_file():
            copy_file_if_needed(child, target)


def output_dir(project_root: Path, slug: str) -> Path:
    return project_root / "output" / slug


def media_dir(project_root: Path) -> Path:
    return project_root / "backend" / "local_storage" / "media"


def artifact_dir(queue_root: Path, job_id: str) -> Path:
    return queue_root / "artifacts" / job_id


def normalize_artifact_paths(queue_root: Path, job: dict[str, Any]) -> dict[str, Any]:
    paths = dict(job.get("paths") or {})
    if not paths:
        return paths
    job_id = str(job.get("job_id") or "")
    video = job.get("video") if isinstance(job.get("video"), dict) else {}
    slug = str(video.get("slug") or job.get("slug") or "")
    if not job_id:
        return paths
    base = artifact_dir(queue_root, job_id)
    paths["artifact_dir"] = str(base)
    if slug:
        paths["artifact_output"] = str(base / "output" / slug)
    video_filename = paths.get("video_filename")
    if not video_filename and paths.get("artifact_media"):
        video_filename = Path(str(paths["artifact_media"])).name
    if video_filename:
        media_name = Path(str(video_filename)).name
        paths["video_filename"] = media_name
        paths["artifact_media"] = str(base / "media" / media_name)
    return paths


def load_status_for_slug(project_root: Path, slug: str) -> dict[str, Any]:
    status_path = output_dir(project_root, slug) / "status.json"
    if not status_path.exists():
        raise FileNotFoundError(f"Missing status.json: {status_path}")
    return load_json(status_path)


def publish_prepared_artifact(project_root: Path, queue_root: Path, job: dict[str, Any]) -> dict[str, Any]:
    slug = str(job["video"]["slug"])
    job_artifact = artifact_dir(queue_root, str(job["job_id"]))
    local_output = output_dir(project_root, slug)
    if not local_output.exists():
        raise FileNotFoundError(f"Missing prepared output folder: {local_output}")
    status = load_status_for_slug(project_root, slug)
    video_filename = ((status.get("media") or {}).get("video_filename"))
    if not video_filename:
        raise RuntimeError(f"Prepared status has no media.video_filename: {local_output / 'status.json'}")
    local_media = media_dir(project_root) / Path(video_filename).name
    if not local_media.exists():
        raise FileNotFoundError(f"Missing cached video file: {local_media}")
    copy_tree_merge(local_output, job_artifact / "output" / slug)
    copy_file_if_needed(local_media, job_artifact / "media" / local_media.name)
    return {
        "artifact_dir": str(job_artifact),
        "artifact_output": str(job_artifact / "output" / slug),
        "artifact_media": str(job_artifact / "media" / local_media.name),
        "video_filename": local_media.name,
    }


def import_prepared_artifact(project_root: Path, queue_root: Path, job: dict[str, Any]) -> None:
    slug = str(job["video"]["slug"])
    job_artifact = artifact_dir(queue_root, str(job["job_id"]))
    artifact_output = job_artifact / "output" / slug
    artifact_media = job_artifact / "media"
    if not artifact_output.exists():
        raise FileNotFoundError(f"Missing artifact output folder: {artifact_output}")
    if not artifact_media.exists():
        raise FileNotFoundError(f"Missing artifact media folder: {artifact_media}")
    copy_tree_merge(artifact_output, output_dir(project_root, slug))
    for media_file in artifact_media.iterdir():
        if media_file.is_file():
            copy_file_if_needed(media_file, media_dir(project_root) / media_file.name)


def export_codex_artifact(project_root: Path, queue_root: Path, job: dict[str, Any]) -> dict[str, Any]:
    slug = str(job["video"]["slug"])
    job_artifact = artifact_dir(queue_root, str(job["job_id"]))
    local_output = output_dir(project_root, slug)
    if not local_output.exists():
        raise FileNotFoundError(f"Missing generated output folder: {local_output}")
    copy_tree_merge(local_output, job_artifact / "output" / slug)
    return {
        "artifact_dir": str(job_artifact),
        "artifact_output": str(job_artifact / "output" / slug),
    }


def codex_output_ok(project_root: Path, slug: str) -> tuple[bool, str | None]:
    out_dir = output_dir(project_root, slug)
    required = ["transcript.json", "notes.md", "notes.html", "backend_video_notes_quality.json"]
    for name in required:
        if not (out_dir / name).exists():
            return False, f"missing {name}"
    try:
        quality = load_json(out_dir / "backend_video_notes_quality.json").get("quality") or {}
    except Exception as exc:
        return False, f"quality json unreadable: {exc}"
    if quality.get("passed") is not True:
        return False, f"quality failed: {quality}"
    return True, None


def run_prepare_job(queue_root: Path, job: dict[str, Any], owner: str, args: argparse.Namespace) -> None:
    project_root = resolve_project_root(args.project_root)
    python_exe = Path(args.python or default_python(project_root, "prepare"))
    manifest_path = write_single_manifest(queue_root, job)
    selector = str(job["video"].get("source_id") or job["video"]["slug"])
    log_path = command_log_path(queue_root, str(job["job_id"]), "prepare")
    command = [
        str(python_exe),
        str(project_root / "tools" / "batch_video_notes.py"),
        "--manifest",
        str(manifest_path),
        "--only",
        selector,
        "--poll-interval",
        str(args.poll_interval),
        "--media-timeout",
        str(args.media_timeout),
        "--api-base",
        args.api_base.rstrip("/"),
        "--skip-codex",
    ]
    if args.force_asr:
        command.append("--force-asr")
    if args.dry_run:
        print(json.dumps({"dry_run": True, "stage": "prepare", "job_id": job["job_id"], "command": command}, ensure_ascii=False))
        release_dry_run_claim(queue_root, str(job["job_id"]), "prepare", owner)
        return
    exit_code = run_with_heartbeat(
        command,
        project_root,
        log_path,
        queue_root,
        str(job["job_id"]),
        "prepare",
        owner,
        args.lease_seconds,
        args.heartbeat_interval,
    )
    if exit_code == 0:
        try:
            paths = publish_prepared_artifact(project_root, queue_root, job)
            finish_job(queue_root, str(job["job_id"]), "prepare", owner, True, log_path, exit_code, paths=paths)
        except Exception as exc:
            finish_job(queue_root, str(job["job_id"]), "prepare", owner, False, log_path, exit_code, str(exc))
    else:
        finish_job(queue_root, str(job["job_id"]), "prepare", owner, False, log_path, exit_code, f"prepare exited {exit_code}")


def run_codex_job(queue_root: Path, job: dict[str, Any], owner: str, args: argparse.Namespace) -> None:
    project_root = resolve_project_root(args.project_root)
    python_exe = Path(args.python or default_python(project_root, "codex"))
    slug = str(job["video"]["slug"])
    selector = str(job["video"].get("source_id") or slug)
    log_path = command_log_path(queue_root, str(job["job_id"]), "codex")
    command = [
        str(python_exe),
        str(project_root / "tools" / "regenerate_video_notes_direct.py"),
        "--slug",
        selector,
        "--llm-timeout",
        str(args.llm_timeout),
        "--chunk-minutes",
        str(args.chunk_minutes),
        "--merge-group-size",
        str(args.merge_group_size),
        "--merge-strategy",
        args.merge_strategy,
    ]
    if args.max_tokens:
        command.extend(["--max-tokens", str(args.max_tokens)])
    if args.remarks:
        command.extend(["--remarks", args.remarks])
    if not args.quality_retry:
        command.append("--no-quality-retry")
    if not args.clear_screenshots:
        command.append("--no-clear-screenshots")
    if args.force_chunks:
        command.append("--force-chunks")
    if args.cache_after_epoch is not None:
        command.extend(["--cache-after-epoch", str(args.cache_after_epoch)])
    if args.dry_run:
        print(json.dumps({"dry_run": True, "stage": "codex", "job_id": job["job_id"], "command": command}, ensure_ascii=False))
        release_dry_run_claim(queue_root, str(job["job_id"]), "codex", owner)
        return
    try:
        import_prepared_artifact(project_root, queue_root, job)
    except Exception as exc:
        finish_job(queue_root, str(job["job_id"]), "codex", owner, False, log_path, 1, str(exc))
        return
    exit_code = run_with_heartbeat(
        command,
        project_root,
        log_path,
        queue_root,
        str(job["job_id"]),
        "codex",
        owner,
        args.lease_seconds,
        args.heartbeat_interval,
    )
    paths: dict[str, Any] = {}
    export_error: str | None = None
    try:
        paths = export_codex_artifact(project_root, queue_root, job)
    except Exception as exc:
        export_error = str(exc)
    ok, reason = codex_output_ok(project_root, slug)
    success = exit_code == 0 and ok and export_error is None
    error = export_error or reason or (None if success else f"codex exited {exit_code}")
    finish_job(queue_root, str(job["job_id"]), "codex", owner, success, log_path, exit_code, error, paths=paths)


def prepare_worker(args: argparse.Namespace) -> int:
    queue_root = Path(args.queue_root).resolve()
    ensure_layout(queue_root)
    preflight_worker(args, "prepare")
    owner = worker_id("prepare")
    if args.dry_run and args.once and not args.max_jobs:
        args.max_jobs = 1
    processed = 0
    while True:
        job = claim_job(queue_root, "prepare", owner, args)
        if not job:
            if args.once:
                return 0
            time.sleep(args.idle_sleep)
            continue
        print(json.dumps({"stage": "prepare", "event": "claimed", "job_id": job["job_id"], "title": job.get("title")}, ensure_ascii=False))
        run_prepare_job(queue_root, job, owner, args)
        processed += 1
        if args.max_jobs and processed >= args.max_jobs:
            return 0


def codex_worker(args: argparse.Namespace) -> int:
    queue_root = Path(args.queue_root).resolve()
    ensure_layout(queue_root)
    preflight_worker(args, "codex")
    owner = worker_id("codex")
    if args.dry_run and args.once and not args.max_jobs:
        args.max_jobs = max(1, args.jobs)
    processed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
        running: dict[concurrent.futures.Future[None], str] = {}
        while True:
            while len(running) < args.jobs and (not args.max_jobs or processed + len(running) < args.max_jobs):
                job = claim_job(queue_root, "codex", owner, args)
                if not job:
                    break
                print(json.dumps({"stage": "codex", "event": "claimed", "job_id": job["job_id"], "title": job.get("title")}, ensure_ascii=False))
                future = executor.submit(run_codex_job, queue_root, job, owner, args)
                running[future] = str(job["job_id"])
            if running:
                done, _ = concurrent.futures.wait(running, timeout=1, return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    job_id = running.pop(future)
                    try:
                        future.result()
                    except Exception as exc:
                        print(json.dumps({"stage": "codex", "event": "worker-error", "job_id": job_id, "error": str(exc)}, ensure_ascii=False))
                    processed += 1
                if args.max_jobs and processed >= args.max_jobs and not running:
                    return 0
                continue
            if args.once:
                return 0
            time.sleep(args.idle_sleep)


def worker(args: argparse.Namespace) -> int:
    if args.role == "gpu":
        return prepare_worker(args)
    if args.role == "cpu":
        return codex_worker(args)
    raise SystemExit(f"Unsupported worker role: {args.role}")


def status(args: argparse.Namespace) -> int:
    queue_root = Path(args.queue_root).resolve()
    rows = []
    counts: dict[str, int] = {}
    for path in iter_job_paths(queue_root):
        job = load_job(path)
        state = str(job.get("state") or "")
        counts[state] = counts.get(state, 0) + 1
        attempts = job.get("attempts") or {}
        error = (job.get("last_error") or {}).get("message") if job.get("last_error") else ""
        rows.append(
            {
                "job_id": job.get("job_id"),
                "state": state,
                "source_id": job.get("source_id"),
                "slug": job.get("slug"),
                "prepare_attempts": attempts.get("prepare", 0),
                "codex_attempts": attempts.get("codex", 0),
                "owner": job.get("owner") or "",
                "lease_until": job.get("lease_until_iso") or "",
                "updated_at": job.get("updated_at_iso") or "",
                "error": error or "",
            }
        )
    if args.json:
        print(json.dumps({"queue_root": str(queue_root), "counts": counts, "jobs": rows}, ensure_ascii=False, indent=2))
        return 0
    print(f"queue_root: {queue_root}")
    print("counts:", json.dumps(counts, ensure_ascii=False, sort_keys=True))
    headers = ["state", "job_id", "prepare", "codex", "updated_at", "error"]
    print("\t".join(headers))
    for row in rows:
        print(
            "\t".join(
                [
                    str(row["state"]),
                    str(row["job_id"]),
                    str(row["prepare_attempts"]),
                    str(row["codex_attempts"]),
                    str(row["updated_at"]),
                    str(row["error"])[:120],
                ]
            )
        )
    return 0


def requeue(args: argparse.Namespace) -> int:
    queue_root = Path(args.queue_root).resolve()
    owner = worker_id("requeue")
    targets = set(args.job or [])
    changed = 0
    for path in iter_job_paths(queue_root):
        job_id = path.stem
        if targets and job_id not in targets:
            continue

        def update(job: dict[str, Any]) -> dict[str, Any] | None:
            state = str(job.get("state") or "")
            if args.stage == "prepare":
                if state not in {"queued", "prepare_failed", "prepare_running", "codex_failed", "prepared"} and not args.force:
                    return None
                job["state"] = "queued"
            elif args.stage == "codex":
                if state not in {"prepared", "codex_failed", "codex_running", "done"} and not args.force:
                    return None
                job["state"] = "prepared"
            else:
                job["state"] = "queued"
            job["owner"] = None
            job["lease_until"] = None
            job["lease_until_iso"] = None
            job["last_error"] = None
            job.setdefault("history", []).append({"time": iso_time(), "event": "requeued", "stage": args.stage, "owner": owner})
            return job

        updated = with_job_lock(queue_root, job_id, owner, update)
        if updated:
            append_event(queue_root, updated, {"event": "requeued", "stage": args.stage})
            changed += 1
    print(json.dumps({"changed": changed}, ensure_ascii=False))
    return 0


def add_common_worker_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--queue-root", required=True, type=Path)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--python", type=Path)
    parser.add_argument("--lease-seconds", type=int, default=1800)
    parser.add_argument("--heartbeat-interval", type=int, default=60)
    parser.add_argument("--idle-sleep", type=int, default=30)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--ignore-max-attempts", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-jobs", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Distributed Media2Markdown video-note workers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    enqueue_parser = subparsers.add_parser("enqueue", help="Create or update queue jobs from a manifest.")
    enqueue_parser.add_argument("--queue-root", required=True, type=Path)
    enqueue_parser.add_argument("--manifest", required=True, type=Path)
    enqueue_parser.add_argument("--replace", action="store_true", help="Replace existing job files for matching ids.")
    enqueue_parser.set_defaults(func=enqueue)

    worker_parser = subparsers.add_parser("worker", help="Run one standardized worker role.")
    worker_parser.add_argument("--role", choices=["cpu", "gpu"], required=True)
    add_common_worker_args(worker_parser)
    worker_parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    worker_parser.add_argument("--poll-interval", type=int, default=30)
    worker_parser.add_argument("--media-timeout", type=int, default=1800)
    worker_parser.add_argument("--force-asr", action="store_true")
    worker_parser.add_argument("--jobs", type=int, default=2)
    worker_parser.add_argument("--chunk-minutes", type=int, default=12)
    worker_parser.add_argument("--llm-timeout", type=int, default=3600)
    worker_parser.add_argument("--max-tokens", type=int)
    worker_parser.add_argument("--remarks", default="")
    worker_parser.add_argument("--no-quality-retry", dest="quality_retry", action="store_false")
    worker_parser.add_argument("--no-clear-screenshots", dest="clear_screenshots", action="store_false")
    worker_parser.add_argument("--force-chunks", action="store_true")
    worker_parser.add_argument("--cache-after-epoch", type=float)
    worker_parser.add_argument("--merge-group-size", type=int, default=3)
    worker_parser.add_argument("--merge-strategy", choices=["codex", "assemble"], default="assemble")
    worker_parser.set_defaults(func=worker, quality_retry=True, clear_screenshots=True)

    status_parser = subparsers.add_parser("status", help="Print queue status.")
    status_parser.add_argument("--queue-root", required=True, type=Path)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=status)

    requeue_parser = subparsers.add_parser("requeue", help="Move failed or stale jobs back to a runnable state.")
    requeue_parser.add_argument("--queue-root", required=True, type=Path)
    requeue_parser.add_argument("--job", action="append", help="Job id to requeue. Can be repeated. Defaults to all eligible jobs.")
    requeue_parser.add_argument("--stage", choices=["prepare", "codex", "all"], default="all")
    requeue_parser.add_argument("--force", action="store_true")
    requeue_parser.set_defaults(func=requeue)

    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""Validate and repair the AI-Media2Doc storage layout contract."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import distributed_video_notes as queue


ROOT = Path(__file__).resolve().parents[1]
RUNNING_STATES = {"prepare_running", "codex_running"}
QUEUE_CHILDREN = ["jobs", "artifacts", "logs", "work", "work/manifests"]


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def queue_layout(queue_root: Path) -> dict[str, str]:
    return {name: str(queue_root / name) for name in QUEUE_CHILDREN}


def expected_paths(queue_root: Path, job: dict[str, Any]) -> dict[str, str]:
    queue_root = queue_root.resolve()
    paths = job.get("paths") if isinstance(job.get("paths"), dict) else {}
    job_id = str(job.get("job_id") or "")
    video = job.get("video") if isinstance(job.get("video"), dict) else {}
    slug = str(video.get("slug") or job.get("slug") or "")
    base = queue_root / "artifacts" / job_id
    result = {
        "artifact_dir": str(base),
    }
    if slug:
        result["artifact_output"] = str(base / "output" / slug)
    video_filename = paths.get("video_filename")
    if not video_filename and paths.get("artifact_media"):
        video_filename = Path(str(paths["artifact_media"])).name
    if video_filename:
        media_name = Path(str(video_filename)).name
        result["video_filename"] = media_name
        result["artifact_media"] = str(base / "media" / media_name)
    return result


def path_mismatches(queue_root: Path, job: dict[str, Any]) -> dict[str, dict[str, str]]:
    paths = job.get("paths") if isinstance(job.get("paths"), dict) else {}
    if not paths:
        return {}
    expected = expected_paths(queue_root, job)
    mismatches: dict[str, dict[str, str]] = {}
    for key, expected_value in expected.items():
        actual_value = str(paths.get(key) or "")
        actual_path = Path(actual_value).resolve(strict=False) if actual_value else None
        expected_path = Path(expected_value).resolve(strict=False)
        if actual_path and actual_path != expected_path:
            mismatches[key] = {"actual": actual_value, "expected": expected_value}
    return mismatches


def job_paths(queue_root: Path) -> list[Path]:
    jobs_dir = queue_root / "jobs"
    if not jobs_dir.exists():
        return []
    return sorted(path for path in jobs_dir.glob("*.json") if path.is_file())


def repair_job_paths(queue_root: Path, job_path: Path, include_running: bool) -> bool:
    queue_root = queue_root.resolve()

    def update(job: dict[str, Any]) -> dict[str, Any] | None:
        if str(job.get("state") or "") in RUNNING_STATES and not include_running:
            return None
        if not path_mismatches(queue_root, job):
            return None
        paths = job.setdefault("paths", {})
        paths.update(expected_paths(queue_root, job))
        job.setdefault("history", []).append(
            {
                "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "event": "storage-path-normalized",
                "stage": "metadata",
                "owner": "check_storage_layout",
            }
        )
        return job

    return queue.with_job_lock(queue_root, job_path.stem, "check_storage_layout", update) is not None


def build_report(project_root: Path, queue_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    queue_root = queue_root.resolve()
    share_root = queue_root.parent
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    jobs_checked = 0
    stale_jobs: list[dict[str, Any]] = []

    for child in ["backend", "frontend", "tools"]:
        path = project_root / child
        if not path.exists():
            errors.append({"code": "missing-project-dir", "path": str(path)})

    if project_root == queue_root or is_relative_to(project_root, queue_root):
        errors.append({"code": "project-inside-queue-root", "project_root": str(project_root), "queue_root": str(queue_root)})

    for name in QUEUE_CHILDREN:
        path = queue_root / name
        if not path.exists():
            errors.append({"code": "missing-queue-dir", "path": str(path)})

    for legacy_name in ["logs", "artifacts"]:
        legacy_path = share_root / legacy_name
        if legacy_path.exists():
            errors.append({"code": "legacy-share-child", "path": str(legacy_path)})

    for job_path in job_paths(queue_root):
        jobs_checked += 1
        try:
            job = load_json(job_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append({"code": "unreadable-job", "path": str(job_path), "message": str(exc)})
            continue
        mismatches = path_mismatches(queue_root, job)
        if mismatches:
            stale = {
                "job_id": job.get("job_id") or job_path.stem,
                "state": job.get("state"),
                "path": str(job_path),
                "running": str(job.get("state") or "") in RUNNING_STATES,
                "mismatches": mismatches,
            }
            stale_jobs.append(stale)
            warnings.append({"code": "stale-job-artifact-paths", **stale})

    return {
        "ok": not errors,
        "project_root": str(project_root),
        "share_root": str(share_root),
        "queue_root": str(queue_root),
        "layout": {
            "final_output_root": str(project_root / "output"),
            "backend_storage": {
                "media": str(project_root / "backend" / "local_storage" / "media"),
                "uploads": str(project_root / "backend" / "local_storage" / "uploads"),
                "screenshots": str(project_root / "backend" / "local_storage" / "screenshots"),
                "logs": str(project_root / "backend" / "local_storage" / "logs"),
            },
            "queue": queue_layout(queue_root),
        },
        "jobs_checked": jobs_checked,
        "stale_job_paths": stale_jobs,
        "errors": errors,
        "warnings": warnings,
    }


def print_human(report: dict[str, Any], repaired: int = 0) -> None:
    print(f"storage layout: {'OK' if report['ok'] else 'FAILED'}")
    print(f"project_root: {report['project_root']}")
    print(f"queue_root: {report['queue_root']}")
    print(f"jobs_checked: {report['jobs_checked']}")
    if repaired:
        print(f"repaired_jobs: {repaired}")
    for warning in report["warnings"]:
        print(f"WARNING {warning['code']}: {warning.get('job_id') or warning.get('path')}")
    for error in report["errors"]:
        print(f"ERROR {error['code']}: {error.get('path') or error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AI-Media2Doc storage layout and queued path metadata.")
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--queue-root", type=Path, default=ROOT.parent / "_queue")
    parser.add_argument("--fix", action="store_true", help="Repair stale non-running job artifact path metadata.")
    parser.add_argument("--include-running", action="store_true", help="Allow --fix to update running job metadata too.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when errors are found.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repaired = 0
    if args.fix:
        for path in job_paths(args.queue_root):
            if repair_job_paths(args.queue_root, path, args.include_running):
                repaired += 1

    report = build_report(args.project_root, args.queue_root)
    report["repaired_jobs"] = repaired
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report, repaired)
    return 1 if args.strict and not report["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

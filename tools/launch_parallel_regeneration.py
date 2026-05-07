# -*- coding: utf-8 -*-
"""Launch direct video note regeneration jobs with bounded parallelism."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from video_manifest import load_manifest, safe_output_name


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "output"


def default_python() -> Path:
    explicit = os.environ.get("M2M_PYTHON")
    if explicit:
        return Path(explicit)
    for name in (".venv-cpu", ".venv-gpu"):
        candidate = ROOT / name / "Scripts" / "python.exe"
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def log_event(event: dict) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def load_status(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def job_key(job: dict) -> str:
    return str(job.get("selector") or job.get("slug") or "")


def unique_jobs(jobs: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for job in jobs:
        key = job_key(job)
        if key and key not in seen:
            seen.add(key)
            result.append(job)
    return result


def discover_output_jobs() -> list[dict]:
    if not OUTPUT_ROOT.exists():
        return []
    jobs = []
    for path in sorted(OUTPUT_ROOT.iterdir()):
        if not path.is_dir():
            continue
        status_path = path / "status.json"
        if status_path.exists() and (path / "transcript.json").exists():
            try:
                status = load_status(status_path)
            except Exception:
                status = {}
            selector = status.get("source_id") or status.get("legacy_slug") or path.name
            jobs.append({"selector": selector, "slug": path.name})
    return jobs


def resolve_output_dir(selector: str) -> Path | None:
    exact = OUTPUT_ROOT / selector
    if (exact / "status.json").exists():
        return exact
    if not OUTPUT_ROOT.exists():
        return None
    for path in OUTPUT_ROOT.iterdir():
        status_path = path / "status.json"
        if not path.is_dir() or not status_path.exists():
            continue
        try:
            status = load_status(status_path)
        except Exception:
            continue
        if selector in {
            path.name,
            status.get("slug"),
            status.get("source_id"),
            status.get("legacy_slug"),
            status.get("title"),
        }:
            return path
    return None


def resolve_jobs(args) -> list[dict]:
    jobs = [{"selector": slug, "slug": (resolve_output_dir(slug) or (OUTPUT_ROOT / slug)).name} for slug in (args.slug or [])]
    if args.manifest:
        jobs.extend(
            {
                "selector": video.get("source_id") or video["slug"],
                "slug": video["slug"],
            }
            for video in load_manifest(args.manifest)
        )
    if args.all_output:
        jobs.extend(discover_output_jobs())
    selected = unique_jobs(jobs)
    if not selected:
        raise RuntimeError("No videos selected. Use --slug, --manifest, or --all-output.")
    return selected


def build_child_command(job: dict, args) -> list[str]:
    python_exe = str(args.python or default_python())
    command = [
        python_exe,
        str(ROOT / "tools" / "regenerate_video_notes_direct.py"),
        "--slug",
        job["selector"],
        "--llm-timeout",
        str(args.llm_timeout),
        "--chunk-minutes",
        str(args.chunk_minutes),
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
    if args.merge_group_size is not None:
        command.extend(["--merge-group-size", str(args.merge_group_size)])
    if args.merge_strategy:
        command.extend(["--merge-strategy", args.merge_strategy])
    return command


def log_file_stem(slug: str) -> str:
    return safe_output_name(slug, "video", limit=80)


def read_quality(slug: str) -> dict | None:
    out_dir = resolve_output_dir(slug) or (OUTPUT_ROOT / slug)
    quality_path = out_dir / "backend_video_notes_quality.json"
    if not quality_path.exists():
        return None
    try:
        return json.loads(quality_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def note_size_kb(slug: str) -> float:
    out_dir = resolve_output_dir(slug) or (OUTPUT_ROOT / slug)
    notes_path = out_dir / "notes.md"
    if not notes_path.exists():
        return 0.0
    return round(notes_path.stat().st_size / 1024, 1)


def summarize(jobs: list[dict], results: dict[str, dict], summary_path: Path) -> list[dict]:
    summary = []
    for job in jobs:
        slug = job["slug"]
        selector = job["selector"]
        quality_payload = read_quality(slug)
        quality = (quality_payload or {}).get("quality") or {}
        result = results.get(selector) or {}
        summary.append(
            {
                "slug": slug,
                "selector": selector,
                "exit_code": result.get("exit_code"),
                "log": result.get("log"),
                "notes_kb": note_size_kb(slug),
                "passed": quality.get("passed"),
                "chars": quality.get("chars"),
                "images": quality.get("image_markers"),
                "chunked": (quality_payload or {}).get("chunked"),
                "chunks": (quality_payload or {}).get("chunk_count"),
                "retried": (quality_payload or {}).get("retried"),
            }
        )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def launch_jobs(jobs: list[dict], args) -> int:
    log_dir = Path(args.log_dir or OUTPUT_ROOT)
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    launcher_log = log_dir / f"parallel_launcher_{stamp}.log"
    summary_path = log_dir / f"parallel_summary_{stamp}.json"
    launcher_log.write_text(
        json.dumps({"stage": "start", "jobs": jobs, "parallelism": args.jobs, "time": time.time()}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    pending = list(jobs)
    running = []
    results: dict[str, dict] = {}
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    while pending or running:
        while pending and len(running) < args.jobs:
            job = pending.pop(0)
            slug = job["slug"]
            selector = job["selector"]
            log_path = log_dir / f"parallel_{log_file_stem(slug)}_{stamp}.log"
            command = build_child_command(job, args)
            if args.dry_run:
                results[selector] = {"exit_code": 0, "log": str(log_path), "command": command}
                log_event({"stage": "dry-run", "slug": slug, "selector": selector, "command": command})
                continue

            log_file = log_path.open("w", encoding="utf-8")
            log_file.write(json.dumps({"stage": "start", "slug": slug, "selector": selector, "command": command}, ensure_ascii=False) + "\n")
            log_file.flush()
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                env=env,
            )
            running.append({"slug": slug, "selector": selector, "process": process, "log_file": log_file, "log_path": log_path})
            log_event({"stage": "launched", "slug": slug, "selector": selector, "pid": process.pid, "log": str(log_path)})
            with launcher_log.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps({"stage": "launched", "slug": slug, "selector": selector, "pid": process.pid, "log": str(log_path)}, ensure_ascii=False) + "\n")

        if args.dry_run:
            continue

        time.sleep(args.poll_interval)
        for item in list(running):
            exit_code = item["process"].poll()
            if exit_code is None:
                continue
            item["log_file"].write(json.dumps({"stage": "finished", "slug": item["slug"], "exit_code": exit_code}, ensure_ascii=False) + "\n")
            item["log_file"].close()
            running.remove(item)
            results[item["selector"]] = {"exit_code": exit_code, "log": str(item["log_path"])}
            log_event({"stage": "finished", "slug": item["slug"], "selector": item["selector"], "exit_code": exit_code, "log": str(item["log_path"])})
            with launcher_log.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps({"stage": "finished", "slug": item["slug"], "selector": item["selector"], "exit_code": exit_code}, ensure_ascii=False) + "\n")

    summary = summarize(jobs, results, summary_path)
    log_event({"stage": "summary", "path": str(summary_path), "items": summary})
    if args.shutdown and not args.dry_run:
        subprocess.run(
            [
                "shutdown.exe",
                "/s",
                "/t",
                "180",
                "/c",
                f"parallel video note regeneration finished; shutdown in 3 minutes; summary: {summary_path}",
            ],
            check=False,
        )
    return 1 if any((item.get("exit_code") or 0) != 0 for item in summary) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run direct video note regeneration jobs in parallel.")
    parser.add_argument("--manifest", type=Path, help="JSON/JSONL video manifest; only slugs are used here.")
    parser.add_argument("--slug", action="append", help="Slug to process. Can be repeated.")
    parser.add_argument("--all-output", action="store_true", help="Process all output folders with status.json and transcript.json.")
    parser.add_argument("--jobs", type=int, default=2, help="Maximum concurrent Codex CLI jobs.")
    parser.add_argument("--chunk-minutes", type=int, default=12)
    parser.add_argument("--llm-timeout", type=int, default=3600)
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--remarks", default="请按讲义式高密度技术复习资料输出，用自然段解释机制和取舍，不要把主体写成项目符号清单，也不要压缩关键细节。")
    parser.add_argument("--no-quality-retry", dest="quality_retry", action="store_false")
    parser.add_argument("--no-clear-screenshots", dest="clear_screenshots", action="store_false")
    parser.add_argument("--force-chunks", action="store_true")
    parser.add_argument(
        "--cache-after-epoch",
        type=float,
        help="Only reuse existing chunk files modified at or after this epoch timestamp.",
    )
    parser.add_argument("--merge-group-size", type=int, default=3)
    parser.add_argument("--merge-strategy", choices=["codex", "assemble"], default="codex")
    parser.add_argument("--poll-interval", type=int, default=5)
    parser.add_argument("--log-dir", type=Path)
    parser.add_argument("--python", type=Path, help="Python executable to run child jobs.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--shutdown", action="store_true")
    parser.set_defaults(quality_retry=True, clear_screenshots=True)
    args = parser.parse_args()

    if args.jobs < 1:
        raise RuntimeError("--jobs must be >= 1")
    python_exe = Path(args.python or default_python())
    if not args.dry_run and not python_exe.exists():
        raise RuntimeError(f"Python executable not found: {python_exe}")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    jobs = resolve_jobs(args)
    return launch_jobs(jobs, args)


if __name__ == "__main__":
    raise SystemExit(main())

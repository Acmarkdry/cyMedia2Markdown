# -*- coding: utf-8 -*-
"""Launch direct video note regeneration jobs with bounded parallelism."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from video_manifest import load_manifest, unique_slugs


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "output"
DEFAULT_PYTHON = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"


def log_event(event: dict) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def discover_output_slugs() -> list[str]:
    if not OUTPUT_ROOT.exists():
        return []
    slugs = []
    for path in sorted(OUTPUT_ROOT.iterdir()):
        if not path.is_dir() or not path.name.startswith("BV"):
            continue
        if (path / "status.json").exists() and (path / "transcript.json").exists():
            slugs.append(path.name)
    return slugs


def resolve_slugs(args) -> list[str]:
    slugs = list(args.slug or [])
    if args.manifest:
        slugs.extend(video["slug"] for video in load_manifest(args.manifest))
    if args.all_output:
        slugs.extend(discover_output_slugs())
    selected = unique_slugs(slugs)
    if not selected:
        raise RuntimeError("No slugs selected. Use --slug, --manifest, or --all-output.")
    return selected


def build_child_command(slug: str, args) -> list[str]:
    python_exe = str(args.python or DEFAULT_PYTHON)
    command = [
        python_exe,
        str(ROOT / "tools" / "regenerate_video_notes_direct.py"),
        "--slug",
        slug,
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
    return command


def read_quality(slug: str) -> dict | None:
    quality_path = OUTPUT_ROOT / slug / "backend_video_notes_quality.json"
    if not quality_path.exists():
        return None
    try:
        return json.loads(quality_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def note_size_kb(slug: str) -> float:
    notes_path = OUTPUT_ROOT / slug / "notes.md"
    if not notes_path.exists():
        return 0.0
    return round(notes_path.stat().st_size / 1024, 1)


def summarize(slugs: list[str], results: dict[str, dict], summary_path: Path) -> list[dict]:
    summary = []
    for slug in slugs:
        quality_payload = read_quality(slug)
        quality = (quality_payload or {}).get("quality") or {}
        result = results.get(slug) or {}
        summary.append(
            {
                "slug": slug,
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


def launch_jobs(slugs: list[str], args) -> int:
    log_dir = Path(args.log_dir or OUTPUT_ROOT)
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    launcher_log = log_dir / f"parallel_launcher_{stamp}.log"
    summary_path = log_dir / f"parallel_summary_{stamp}.json"
    launcher_log.write_text(
        json.dumps({"stage": "start", "slugs": slugs, "jobs": args.jobs, "time": time.time()}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    pending = list(slugs)
    running = []
    results: dict[str, dict] = {}
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    while pending or running:
        while pending and len(running) < args.jobs:
            slug = pending.pop(0)
            log_path = log_dir / f"parallel_{slug}_{stamp}.log"
            command = build_child_command(slug, args)
            if args.dry_run:
                results[slug] = {"exit_code": 0, "log": str(log_path), "command": command}
                log_event({"stage": "dry-run", "slug": slug, "command": command})
                continue

            log_file = log_path.open("w", encoding="utf-8")
            log_file.write(json.dumps({"stage": "start", "slug": slug, "command": command}, ensure_ascii=False) + "\n")
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
            running.append({"slug": slug, "process": process, "log_file": log_file, "log_path": log_path})
            log_event({"stage": "launched", "slug": slug, "pid": process.pid, "log": str(log_path)})
            with launcher_log.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps({"stage": "launched", "slug": slug, "pid": process.pid, "log": str(log_path)}, ensure_ascii=False) + "\n")

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
            results[item["slug"]] = {"exit_code": exit_code, "log": str(item["log_path"])}
            log_event({"stage": "finished", "slug": item["slug"], "exit_code": exit_code, "log": str(item["log_path"])})
            with launcher_log.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps({"stage": "finished", "slug": item["slug"], "exit_code": exit_code}, ensure_ascii=False) + "\n")

    summary = summarize(slugs, results, summary_path)
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
    parser.add_argument("--all-output", action="store_true", help="Process all output/BV* folders with status.json and transcript.json.")
    parser.add_argument("--jobs", type=int, default=2, help="Maximum concurrent Codex CLI jobs.")
    parser.add_argument("--chunk-minutes", type=int, default=12)
    parser.add_argument("--llm-timeout", type=int, default=3600)
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--remarks", default="请按高密度技术复习资料输出，不要压缩关键细节。")
    parser.add_argument("--no-quality-retry", dest="quality_retry", action="store_false")
    parser.add_argument("--no-clear-screenshots", dest="clear_screenshots", action="store_false")
    parser.add_argument("--force-chunks", action="store_true")
    parser.add_argument("--poll-interval", type=int, default=5)
    parser.add_argument("--log-dir", type=Path)
    parser.add_argument("--python", type=Path, help="Python executable to run child jobs.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--shutdown", action="store_true")
    parser.set_defaults(quality_retry=True, clear_screenshots=True)
    args = parser.parse_args()

    if args.jobs < 1:
        raise RuntimeError("--jobs must be >= 1")
    python_exe = Path(args.python or DEFAULT_PYTHON)
    if not args.dry_run and not python_exe.exists():
        raise RuntimeError(f"Python executable not found: {python_exe}")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    slugs = resolve_slugs(args)
    return launch_jobs(slugs, args)


if __name__ == "__main__":
    raise SystemExit(main())

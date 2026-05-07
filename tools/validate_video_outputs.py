# -*- coding: utf-8 -*-
"""Validate generated video-note output folders.

This checker intentionally avoids calling ASR, Codex, ffmpeg, or the network.
It verifies the artifact contract after a video job has produced files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


IMAGE_RE = re.compile(r"!\[([^\]]*)\]\((screenshots/[^)]+)\)")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def output_matches(out_dir: Path, slugs: set[str], source_ids: set[str]) -> bool:
    if not slugs and not source_ids:
        return True
    if out_dir.name in slugs:
        return True
    status_path = out_dir / "status.json"
    if not status_path.exists():
        return False
    try:
        status = load_json(status_path)
    except Exception:
        return False
    return bool(status.get("source_id") in source_ids or status.get("slug") in slugs)


def iter_output_dirs(output_root: Path, slugs: set[str], source_ids: set[str]) -> list[Path]:
    if not output_root.exists():
        return []
    dirs = [path for path in output_root.iterdir() if path.is_dir()]
    return sorted(path for path in dirs if output_matches(path, slugs, source_ids))


def validate_output_dir(out_dir: Path) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    required = {
        "status": out_dir / "status.json",
        "transcript": out_dir / "transcript.json",
        "notes": out_dir / "notes.md",
        "html": out_dir / "notes.html",
        "quality": out_dir / "backend_video_notes_quality.json",
    }
    for label, path in required.items():
        if not path.exists():
            problems.append({"output": out_dir.name, "code": "missing-file", "file": label, "path": str(path)})

    quality_path = required["quality"]
    if quality_path.exists():
        try:
            quality = load_json(quality_path).get("quality") or {}
        except Exception as exc:
            problems.append({"output": out_dir.name, "code": "quality-unreadable", "message": str(exc)})
        else:
            if quality.get("passed") is not True:
                problems.append(
                    {
                        "output": out_dir.name,
                        "code": "quality-failed",
                        "message": quality.get("problems") or quality,
                    }
                )

    notes_path = required["notes"]
    refs: list[str] = []
    if notes_path.exists():
        text = notes_path.read_text(encoding="utf-8", errors="replace")
        if "#image[" in text:
            problems.append({"output": out_dir.name, "code": "unfinalized-image-marker"})
        for match in IMAGE_RE.finditer(text):
            alt = match.group(1).strip()
            rel = match.group(2)
            refs.append(rel)
            if re.fullmatch(r"\d+", alt):
                problems.append({"output": out_dir.name, "code": "numeric-image-alt", "alt": alt})
            if not (out_dir / rel).exists():
                problems.append({"output": out_dir.name, "code": "missing-screenshot", "path": rel})

    screenshots_dir = out_dir / "screenshots"
    screenshot_count = len(list(screenshots_dir.glob("*.jpg"))) if screenshots_dir.exists() else 0
    if refs and screenshot_count < len(set(refs)):
        problems.append(
            {
                "output": out_dir.name,
                "code": "screenshot-count-mismatch",
                "refs": len(set(refs)),
                "files": screenshot_count,
            }
        )
    return problems


def build_report(output_root: Path, slugs: set[str], source_ids: set[str]) -> dict[str, Any]:
    output_dirs = iter_output_dirs(output_root, slugs, source_ids)
    problems: list[dict[str, Any]] = []
    for out_dir in output_dirs:
        problems.extend(validate_output_dir(out_dir))
    return {
        "ok": not problems,
        "output_root": str(output_root),
        "checked": [str(path) for path in output_dirs],
        "problems": problems,
    }


def print_human(report: dict[str, Any]) -> None:
    print(f"video output validation: {'OK' if report['ok'] else 'FAILED'}")
    print(f"output_root: {report['output_root']}")
    print(f"checked: {len(report['checked'])}")
    for problem in report["problems"]:
        print(json.dumps(problem, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated video-note output folders.")
    parser.add_argument("--output-root", type=Path, default=Path("output"))
    parser.add_argument("--slug", action="append", default=[])
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_report(args.output_root, set(args.slug), set(args.source_id))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

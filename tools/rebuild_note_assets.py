# -*- coding: utf-8 -*-
"""Rebuild generated note image references, screenshots, and HTML.

This keeps Codex output intact by reading notes_raw.md, then reapplies the
current Markdown image rendering and screenshot extraction rules.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from batch_video_notes import finalize_notes, render_html


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "output"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def iter_note_dirs(slugs: list[str]) -> list[Path]:
    if slugs:
        return [OUTPUT_ROOT / slug for slug in slugs]
    if not OUTPUT_ROOT.exists():
        return []
    return sorted(path for path in OUTPUT_ROOT.iterdir() if path.is_dir() and path.name.startswith("BV"))


def assert_workspace_screenshots_dir(path: Path) -> None:
    resolved = path.resolve()
    output_resolved = OUTPUT_ROOT.resolve()
    if output_resolved not in resolved.parents:
        raise RuntimeError(f"Refusing to remove screenshots outside output/: {resolved}")
    if resolved.name != "screenshots":
        raise RuntimeError(f"Refusing to remove unexpected directory: {resolved}")


def rebuild_one(out_dir: Path, refresh_screenshots: bool) -> dict:
    if not out_dir.exists():
        raise RuntimeError(f"Output directory not found: {out_dir}")

    status_path = out_dir / "status.json"
    transcript_path = out_dir / "transcript.json"
    raw_path = out_dir / "notes_raw.md"
    if not status_path.exists():
        raise RuntimeError(f"Missing status.json: {status_path}")
    if not transcript_path.exists():
        raise RuntimeError(f"Missing transcript.json: {transcript_path}")
    if not raw_path.exists():
        raise RuntimeError(f"Missing notes_raw.md: {raw_path}")

    status = load_json(status_path)
    media = status.get("media") or {}
    video_filename = media.get("video_filename")
    if not video_filename:
        raise RuntimeError(f"Missing media.video_filename in {status_path}")

    screenshots_dir = out_dir / "screenshots"
    if refresh_screenshots and screenshots_dir.exists():
        assert_workspace_screenshots_dir(screenshots_dir)
        shutil.rmtree(screenshots_dir)

    segments = load_json(transcript_path)
    times = finalize_notes(ROOT, out_dir, video_filename, segments)
    render_html(out_dir)

    status["screenshots"] = times
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"slug": out_dir.name, "screenshots": len(times), "refreshed": refresh_screenshots}


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild generated note screenshots and HTML.")
    parser.add_argument("slugs", nargs="*", help="Output slugs to rebuild, for example BV1mT4y167Fm.")
    parser.add_argument(
        "--refresh-screenshots",
        action="store_true",
        help="Delete generated screenshots and extract them again at the current quality settings.",
    )
    args = parser.parse_args()

    failures = []
    for out_dir in iter_note_dirs(args.slugs):
        try:
            result = rebuild_one(out_dir, args.refresh_screenshots)
            print(json.dumps({"stage": "rebuilt", **result}, ensure_ascii=False), flush=True)
        except Exception as exc:
            failures.append({"slug": out_dir.name, "error": str(exc)})
            print(json.dumps({"stage": "failed", "slug": out_dir.name, "error": str(exc)}, ensure_ascii=False), flush=True)

    if failures:
        print(json.dumps({"stage": "summary", "failures": failures}, ensure_ascii=False), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

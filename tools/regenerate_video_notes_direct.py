# -*- coding: utf-8 -*-
"""Regenerate one saved video note directly through Codex CLI.

This runner bypasses the backend HTTP endpoint so multiple videos can be run in
parallel. It still reuses the backend prompt, chunking, merge, and quality
helpers to keep output quality aligned with the app workflow.
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from batch_video_notes import finalize_notes, render_html  # noqa: E402
from routers.llm import (  # noqa: E402
    assess_markdown_quality,
    build_merge_prompt,
    build_retry_prompt,
    build_video_notes_prompt,
    format_time_ms,
    format_transcript_segments,
    notes_density_targets,
    prepare_segments,
    run_codex_cli,
    split_segments,
)


def log_event(event: dict):
    print(json.dumps(event, ensure_ascii=False), flush=True)


def load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def load_segments(out_dir: Path) -> list[dict]:
    transcript_path = out_dir / "transcript.json"
    if not transcript_path.exists():
        raise RuntimeError(f"Missing transcript.json: {transcript_path}")
    return prepare_segments(load_json(transcript_path))


def load_status(out_dir: Path) -> dict:
    status_path = out_dir / "status.json"
    if not status_path.exists():
        raise RuntimeError(f"Missing status.json: {status_path}")
    return load_json(status_path)


def resolve_video(out_dir: Path, slug: str) -> dict:
    status = load_status(out_dir)
    media = status.get("media") or {}
    video_filename = media.get("video_filename")
    if not video_filename:
        raise RuntimeError(f"status.json has no media.video_filename for {slug}")
    video_path = ROOT / "backend" / "local_storage" / "media" / video_filename
    if not video_path.exists():
        raise RuntimeError(f"Cached video file is missing: {video_path}")
    return {
        "slug": slug,
        "source_id": status.get("source_id") or media.get("source_id") or media.get("bv_id"),
        "legacy_slug": status.get("legacy_slug"),
        "title": status.get("title") or media.get("title") or slug,
        "source_url": media.get("source_url"),
        "media": media,
        "video_filename": video_filename,
    }


def should_chunk(segments: list[dict]) -> bool:
    targets = notes_density_targets(segments)
    return targets["duration_seconds"] >= 45 * 60 or len(format_transcript_segments(segments)) > 90000


def run_chunked(video: dict, out_dir: Path, segments: list[dict], args) -> tuple[str, str, int]:
    chunk_dir = out_dir / "direct_chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunks = split_segments(segments, args.chunk_minutes)
    chunk_notes = []
    for index, chunk in enumerate(chunks):
        note_path = chunk_dir / f"chunk_{index + 1:02d}.md"
        prompt_path = chunk_dir / f"chunk_{index + 1:02d}.prompt.md"
        part_label = (
            f"{index + 1}/{len(chunks)} "
            f"[{format_time_ms(chunk[0]['start_time'])}-{format_time_ms(chunk[-1]['end_time'])}]"
        )
        prompt = build_video_notes_prompt(
            title=video["title"],
            source_url=video.get("source_url"),
            segments=chunk,
            remarks=args.remarks,
            part_label=part_label,
            max_tokens=args.max_tokens,
        )
        prompt_path.write_text(prompt, encoding="utf-8")
        if note_path.exists() and not args.force_chunks:
            note = note_path.read_text(encoding="utf-8")
            log_event({"stage": "chunk-cache", "slug": video["slug"], "chunk": index + 1, "chunks": len(chunks)})
        else:
            log_event({"stage": "chunk-start", "slug": video["slug"], "chunk": index + 1, "chunks": len(chunks)})
            note = run_codex_cli(prompt, args.llm_timeout)
            note_path.write_text(note, encoding="utf-8")
            log_event({"stage": "chunk-done", "slug": video["slug"], "chunk": index + 1, "chars": len(note)})
        chunk_notes.append(note)

    targets = notes_density_targets(segments)
    merge_prompt = build_merge_prompt(
        video["title"],
        video.get("source_url"),
        chunk_notes,
        targets,
        args.remarks,
        max_tokens=args.max_tokens,
    )
    merge_prompt_path = out_dir / "direct_merge_prompt.md"
    merge_prompt_path.write_text(merge_prompt, encoding="utf-8")
    log_event({"stage": "merge-start", "slug": video["slug"], "chunks": len(chunks)})
    content = run_codex_cli(merge_prompt, args.llm_timeout)
    log_event({"stage": "merge-done", "slug": video["slug"], "chars": len(content)})
    return content, merge_prompt, len(chunks)


def run_single(video: dict, out_dir: Path, segments: list[dict], args) -> tuple[str, str, int, bool]:
    chunked = should_chunk(segments)
    if chunked:
        content, prompt_used, chunk_count = run_chunked(video, out_dir, segments, args)
        return content, prompt_used, chunk_count, True
    prompt = build_video_notes_prompt(
        title=video["title"],
        source_url=video.get("source_url"),
        segments=segments,
        remarks=args.remarks,
        max_tokens=args.max_tokens,
    )
    (out_dir / "direct_prompt.md").write_text(prompt, encoding="utf-8")
    log_event({"stage": "single-start", "slug": video["slug"]})
    content = run_codex_cli(prompt, args.llm_timeout)
    log_event({"stage": "single-done", "slug": video["slug"], "chars": len(content)})
    return content, prompt, 1, False


def process_slug(slug: str, args) -> dict:
    out_dir = ROOT / "output" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    video = resolve_video(out_dir, slug)
    segments = load_segments(out_dir)
    log_event({"stage": "start", "slug": slug, "title": video["title"], "segments": len(segments)})

    content, prompt_used, chunk_count, chunked = run_single(video, out_dir, segments, args)
    targets = notes_density_targets(segments)
    quality = assess_markdown_quality(content, targets)
    retried = False

    if args.quality_retry and not quality["passed"]:
        retry_prompt = build_retry_prompt(prompt_used, content, quality)
        (out_dir / "direct_retry_prompt.md").write_text(retry_prompt, encoding="utf-8")
        log_event({"stage": "retry-start", "slug": slug, "quality": quality})
        retry_content = run_codex_cli(retry_prompt, args.llm_timeout)
        retry_quality = assess_markdown_quality(retry_content, targets)
        if retry_quality["passed"] or retry_quality["chars"] > quality["chars"]:
            content = retry_content
            quality = retry_quality
            retried = True
        log_event({"stage": "retry-done", "slug": slug, "accepted": retried, "quality": retry_quality})

    (out_dir / "notes_raw.md").write_text(content, encoding="utf-8")
    quality_payload = {
        "quality": quality,
        "chunked": chunked,
        "chunk_count": chunk_count,
        "retried": retried,
        "generated_at": time.time(),
        "runner": "direct-parallel",
    }
    (out_dir / "backend_video_notes_quality.json").write_text(
        json.dumps(quality_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    screenshots_dir = out_dir / "screenshots"
    if args.clear_screenshots and screenshots_dir.exists():
        shutil.rmtree(screenshots_dir)
    times = finalize_notes(ROOT, out_dir, video["video_filename"], segments)
    render_html(out_dir)

    status = {
        "slug": slug,
        "source_id": video.get("source_id"),
        "legacy_slug": video.get("legacy_slug"),
        "title": video["title"],
        "out_dir": str(out_dir),
        "media": video["media"],
        "segments": len(segments),
        "screenshots": times,
        "quality": quality,
        "chunked": chunked,
        "chunk_count": chunk_count,
        "retried": retried,
        "runner": "direct-parallel",
    }
    (out_dir / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    log_event(
        {
            "stage": "done",
            "slug": slug,
            "quality": quality,
            "screenshots": len(times),
            "chunked": chunked,
            "chunk_count": chunk_count,
            "retried": retried,
        }
    )
    return status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    parser.add_argument("--chunk-minutes", type=int, default=12)
    parser.add_argument("--llm-timeout", type=int, default=3600)
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--remarks", default="请按高密度技术复习资料输出，不要压缩关键细节。")
    parser.add_argument("--no-quality-retry", dest="quality_retry", action="store_false")
    parser.add_argument("--no-clear-screenshots", dest="clear_screenshots", action="store_false")
    parser.add_argument("--force-chunks", action="store_true")
    parser.set_defaults(quality_retry=True, clear_screenshots=True)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    try:
        process_slug(args.slug, args)
    except Exception as exc:
        log_event({"stage": "failed", "slug": args.slug, "error": str(exc)})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""Regenerate saved video notes through the backend video-notes workflow.

This script reuses existing downloaded media and transcript.json files, then calls
the backend /llm/video-notes endpoint so batch regeneration follows the same
chunking, merge, and quality retry path used by the app.
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from urllib.error import HTTPError

from batch_video_notes import finalize_notes, post_json, render_html, write_transcripts
from video_manifest import load_manifest, select_videos as select_manifest_videos


API_BASE = "http://127.0.0.1:8080/api/v1"


def log_event(event: dict):
    print(json.dumps(event, ensure_ascii=False), flush=True)


def load_segments(out_dir: Path) -> list[dict]:
    transcript_path = out_dir / "transcript.json"
    if not transcript_path.exists():
        return []
    segments = json.loads(transcript_path.read_text(encoding="utf-8"))
    return [
        {
            "id": index,
            "start_time": int(segment["start_time"]),
            "end_time": int(segment["end_time"]),
            "text": str(segment.get("text") or "").strip(),
        }
        for index, segment in enumerate(segments)
        if str(segment.get("text") or "").strip()
    ]


def fetch_media(video: dict, timeout: int) -> dict:
    payload = post_json(
        f"{API_BASE}/files/media-from-url",
        {"url": video["url"]},
        timeout=timeout,
    )
    if not payload.get("success"):
        raise RuntimeError(payload)
    return payload["data"]


def generate_notes(video: dict, segments: list[dict], args) -> dict:
    data = {
        "title": video["title"],
        "source_url": video["url"],
        "transcript_segments": segments,
        "remarks": args.remarks,
        "chunk_minutes": args.chunk_minutes,
        "enable_chunking": True,
        "quality_retry": args.quality_retry,
        "timeout": args.llm_timeout,
    }
    if args.max_tokens:
        data["max_tokens"] = args.max_tokens

    try:
        response = post_json(
            f"{API_BASE}/llm/video-notes",
            data,
            timeout=args.request_timeout,
        )
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"video-notes HTTP {exc.code}: {details}") from exc

    if not response.get("success"):
        raise RuntimeError(response)
    content = response["data"]["choices"][0]["message"]["content"]
    return {
        "content": content,
        "quality": response["data"].get("quality"),
        "chunked": response["data"].get("chunked"),
        "chunk_count": response["data"].get("chunk_count"),
        "retried": response["data"].get("retried"),
    }


def process_video(root: Path, video: dict, args) -> dict:
    out_dir = root / "output" / video["slug"]
    out_dir.mkdir(parents=True, exist_ok=True)
    log_event({"stage": "start", "slug": video["slug"], "title": video["title"]})

    media = fetch_media(video, args.media_timeout)
    video["title"] = media.get("title") or video["title"]
    log_event(
        {
            "stage": "media",
            "slug": video["slug"],
            "cache_hit": media.get("cache_hit"),
            "cache_source": media.get("cache_source"),
            "duration": media.get("duration"),
        }
    )

    segments = load_segments(out_dir)
    if not segments and media.get("transcript_segments"):
        segments = media["transcript_segments"]
        write_transcripts(out_dir, segments)
    if not segments:
        raise RuntimeError(f"No reusable transcript found for {video['slug']}")

    log_event({"stage": "transcript", "slug": video["slug"], "segments": len(segments)})
    result = generate_notes(video, segments, args)
    (out_dir / "notes_raw.md").write_text(result["content"], encoding="utf-8")
    (out_dir / "backend_video_notes_quality.json").write_text(
        json.dumps(
            {
                "quality": result["quality"],
                "chunked": result["chunked"],
                "chunk_count": result["chunk_count"],
                "retried": result["retried"],
                "generated_at": time.time(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    screenshots_dir = out_dir / "screenshots"
    if args.clear_screenshots and screenshots_dir.exists():
        shutil.rmtree(screenshots_dir)
    times = finalize_notes(root, out_dir, media["video_filename"], segments)
    render_html(out_dir)

    status = {
        "slug": video["slug"],
        "title": video["title"],
        "out_dir": str(out_dir),
        "media": media,
        "segments": len(segments),
        "screenshots": times,
        "quality": result["quality"],
        "chunked": result["chunked"],
        "chunk_count": result["chunk_count"],
        "retried": result["retried"],
    }
    (out_dir / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    log_event(
        {
            "stage": "done",
            "slug": video["slug"],
            "screenshots": len(times),
            "quality": result["quality"],
            "chunked": result["chunked"],
            "chunk_count": result["chunk_count"],
            "retried": result["retried"],
        }
    )
    return status


def load_selected_videos(args) -> list[dict]:
    return select_manifest_videos(load_manifest(args.manifest), args.only, args.start_at)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path, help="JSON/JSONL video manifest with slug, title, url")
    parser.add_argument("--only", nargs="*", help="Only process these slugs")
    parser.add_argument("--start-at", help="Start at this slug")
    parser.add_argument("--media-timeout", type=int, default=900)
    parser.add_argument("--request-timeout", type=int, default=21600)
    parser.add_argument("--llm-timeout", type=int, default=3600)
    parser.add_argument("--chunk-minutes", type=int, default=12)
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--remarks", default="请按高密度技术复习资料输出，不要压缩关键细节。")
    parser.add_argument("--no-quality-retry", dest="quality_retry", action="store_false")
    parser.add_argument("--no-clear-screenshots", dest="clear_screenshots", action="store_false")
    parser.set_defaults(quality_retry=True, clear_screenshots=True)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    root = Path(__file__).resolve().parents[1]
    statuses = []
    for video in load_selected_videos(args):
        try:
            statuses.append(process_video(root, dict(video), args))
        except Exception as exc:
            failure = {"slug": video["slug"], "title": video["title"], "error": str(exc)}
            statuses.append(failure)
            log_event({"stage": "failed", **failure})

    batch_path = root / "output" / "backend_regenerate_status.json"
    batch_path.write_text(json.dumps(statuses, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if any("error" in status for status in statuses) else 0


if __name__ == "__main__":
    raise SystemExit(main())

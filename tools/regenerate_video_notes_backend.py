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


API_BASE = "http://127.0.0.1:8080/api/v1"


VIDEOS = [
    {
        "slug": "BV13D4y1v7xx",
        "title": "[UOD2022]Mass框架相关技术演讲",
        "url": "https://www.bilibili.com/video/BV13D4y1v7xx/",
    },
    {
        "slug": "BV1nB4y1y7cX",
        "title": "[技术演讲]在UE5中用Mass框架构建海量实体(官方字幕)",
        "url": "https://www.bilibili.com/video/BV1nB4y1y7cX/",
    },
    {
        "slug": "BV1mT4y167Fm",
        "title": "[技术演讲]Lyra跨平台UI开发(官方字幕)",
        "url": "https://www.bilibili.com/video/BV1mT4y167Fm/",
    },
    {
        "slug": "BV1we411N7qu",
        "title": "[UOD2022]Lyra中AbilitySystem的应用 | Epic 陈宝康",
        "url": "https://www.bilibili.com/video/BV1we411N7qu/",
    },
    {
        "slug": "BV1hSW4zTEgQ",
        "title": "[UFSH2025]《鸣潮》中的光线追踪: 用光线构建动漫风格开放世界 | 王鑫 库洛游戏《鸣潮》图形渲染组长",
        "url": "https://www.bilibili.com/video/BV1hSW4zTEgQ/",
    },
    {
        "slug": "BV1yG4y187y6",
        "title": "[英文直播]分析Lyra中的动画(官方字幕)",
        "url": "https://www.bilibili.com/video/BV1yG4y187y6/",
    },
    {
        "slug": "BV1L94y197kh",
        "title": "[英文直播]Lyra导览与问答(官方字幕)",
        "url": "https://www.bilibili.com/video/BV1L94y197kh/",
    },
    {
        "slug": "BV1Ce4y1X7k5",
        "title": "[UnrealCircle]《Lyra初学者游戏包工程解读》 | quabqi",
        "url": "https://www.bilibili.com/video/BV1Ce4y1X7k5/",
    },
    {
        "slug": "BV1X5411V7jh",
        "title": "[中文直播]第31期｜GAS插件介绍（入门篇） | 伍德 大钊",
        "url": "https://www.bilibili.com/video/BV1X5411V7jh/",
    },
    {
        "slug": "BV1zD4y1X77M",
        "title": "[UnrealOpenDay2020]深入GAS架构设计 | EpicGames 大钊",
        "url": "https://www.bilibili.com/video/BV1zD4y1X77M/",
    },
]


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


def select_videos(args) -> list[dict]:
    videos = list(VIDEOS)
    if args.only:
        allowed = set(args.only)
        videos = [video for video in videos if video["slug"] in allowed]
    if args.start_at:
        slugs = [video["slug"] for video in videos]
        if args.start_at not in slugs:
            raise RuntimeError(f"Unknown --start-at slug: {args.start_at}")
        videos = videos[slugs.index(args.start_at) :]
    return videos


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="Only process these BV slugs")
    parser.add_argument("--start-at", help="Start at this BV slug")
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
    for video in select_videos(args):
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

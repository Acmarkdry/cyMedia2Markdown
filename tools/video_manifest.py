# -*- coding: utf-8 -*-
"""Helpers for loading batch video manifests."""

import json
import re
from pathlib import Path
from urllib.parse import urlparse


BV_RE = re.compile(r"(BV[0-9A-Za-z]+)")
INVALID_PATH_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
SPACE_RE = re.compile(r"\s+")
ASCII_SLUG_RE = re.compile(r"[^0-9A-Za-z_.-]+")


def truncate_name(value: str, limit: int = 120) -> str:
    if len(value) <= limit:
        return value
    return value[:limit].rstrip(" .-_")


def safe_output_name(value: str, fallback: str, limit: int = 120) -> str:
    name = INVALID_PATH_CHARS_RE.sub(" ", value)
    name = SPACE_RE.sub(" ", name).strip(" .-_")
    return truncate_name(name, limit) or fallback


def ascii_slug(value: str, fallback: str) -> str:
    slug = ASCII_SLUG_RE.sub("-", value).strip("-._")
    return truncate_name(slug, 96) or fallback


def infer_source_id(url: str, index: int) -> str:
    match = BV_RE.search(url)
    if match:
        return match.group(1)
    parsed = urlparse(url)
    path_name = Path(parsed.path).stem if parsed.path else ""
    return ascii_slug(path_name, f"video-{index + 1:03d}")


def make_unique_slug(slug: str, seen: set[str]) -> str:
    if slug not in seen:
        seen.add(slug)
        return slug
    base = truncate_name(slug, 112) or "video"
    suffix = 2
    while True:
        candidate = f"{base}-{suffix}"
        if candidate not in seen:
            seen.add(candidate)
            return candidate
        suffix += 1


def normalize_video(item, index: int) -> dict:
    if isinstance(item, str):
        item = {"url": item}
    if not isinstance(item, dict):
        raise ValueError(f"Video item #{index + 1} must be an object or URL string")

    url = str(item.get("url") or item.get("source_url") or "").strip()
    title = str(item.get("title") or item.get("name") or "").strip()
    source_id = str(item.get("source_id") or item.get("bv") or item.get("id") or "").strip()
    slug = str(item.get("slug") or item.get("output_name") or item.get("folder") or "").strip()
    if not url:
        raise ValueError(f"Video item #{index + 1} is missing url")
    if not source_id:
        source_id = infer_source_id(url, index)
    if not title:
        title = source_id
    if not slug:
        slug = safe_output_name(title, source_id)
    else:
        slug = safe_output_name(slug, source_id)
    return {"slug": slug, "source_id": source_id, "title": title, "url": url}


def load_manifest(path: str | Path) -> list[dict]:
    manifest_path = Path(path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    if manifest_path.suffix.lower() in {".jsonl", ".ndjson"}:
        raw_items = [
            json.loads(line)
            for line in manifest_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    else:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            raw_items = payload.get("videos") or payload.get("items")
        else:
            raw_items = payload

    if not isinstance(raw_items, list):
        raise ValueError("Manifest must be a JSON list or an object with a videos list")
    seen = set()
    videos = []
    for index, item in enumerate(raw_items):
        video = normalize_video(item, index)
        video["slug"] = make_unique_slug(video["slug"], seen)
        videos.append(video)
    if not videos:
        raise ValueError(f"Manifest has no videos: {manifest_path}")
    return videos


def matches_selector(video: dict, selector: str) -> bool:
    return selector in {
        video.get("slug"),
        video.get("source_id"),
        video.get("title"),
    }


def select_videos(videos: list[dict], only: list[str] | None = None, start_at: str | None = None) -> list[dict]:
    selected = list(videos)
    if only:
        selected = [video for video in selected if any(matches_selector(video, item) for item in only)]
    if start_at:
        start_index = next(
            (index for index, video in enumerate(selected) if matches_selector(video, start_at)),
            None,
        )
        if start_index is None:
            raise RuntimeError(f"Unknown --start-at selector: {start_at}")
        selected = selected[start_index:]
    if not selected:
        raise RuntimeError("No videos selected")
    return selected


def unique_slugs(slugs: list[str]) -> list[str]:
    seen = set()
    result = []
    for slug in slugs:
        if slug and slug not in seen:
            seen.add(slug)
            result.append(slug)
    return result

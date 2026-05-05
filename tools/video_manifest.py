# -*- coding: utf-8 -*-
"""Helpers for loading batch video manifests."""

import json
import re
from pathlib import Path
from urllib.parse import urlparse


BV_RE = re.compile(r"(BV[0-9A-Za-z]+)")
SLUG_RE = re.compile(r"[^0-9A-Za-z_.-]+")


def slugify(value: str, fallback: str) -> str:
    slug = SLUG_RE.sub("-", value).strip("-._")
    return slug[:96] or fallback


def infer_slug(url: str, title: str, index: int) -> str:
    match = BV_RE.search(url)
    if match:
        return match.group(1)
    parsed = urlparse(url)
    path_name = Path(parsed.path).stem if parsed.path else ""
    return slugify(path_name or title, f"video-{index + 1:03d}")


def normalize_video(item, index: int) -> dict:
    if isinstance(item, str):
        item = {"url": item}
    if not isinstance(item, dict):
        raise ValueError(f"Video item #{index + 1} must be an object or URL string")

    url = str(item.get("url") or item.get("source_url") or "").strip()
    title = str(item.get("title") or item.get("name") or "").strip()
    slug = str(item.get("slug") or item.get("id") or "").strip()
    if not url:
        raise ValueError(f"Video item #{index + 1} is missing url")
    if not slug:
        slug = infer_slug(url, title, index)
    if not title:
        title = slug
    return {"slug": slug, "title": title, "url": url}


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
    videos = [normalize_video(item, index) for index, item in enumerate(raw_items)]
    if not videos:
        raise ValueError(f"Manifest has no videos: {manifest_path}")
    return videos


def select_videos(videos: list[dict], only: list[str] | None = None, start_at: str | None = None) -> list[dict]:
    selected = list(videos)
    if only:
        allowed = set(only)
        selected = [video for video in selected if video["slug"] in allowed]
    if start_at:
        slugs = [video["slug"] for video in selected]
        if start_at not in slugs:
            raise RuntimeError(f"Unknown --start-at slug: {start_at}")
        selected = selected[slugs.index(start_at) :]
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

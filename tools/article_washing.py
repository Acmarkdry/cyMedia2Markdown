# -*- coding: utf-8 -*-
"""赛博洗稿 v2 — 批量文章内容精炼工具（两阶段 AI 流水线）。

从清单文件读取文章 URL 列表，调用后端 /washing/wash API（两阶段：
领域理解 → 深度精炼），将精炼后的 Markdown 笔记、领域脉络、原文和
源码参考保存到指定输出目录。

清单支持 articles 和可选的 code_projects 字段。
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

API_BASE = "http://127.0.0.1:8080/api/v1"

# ---- sanitise helpers -------------------------------------------------------

_INVALID_PATH_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_SPACE_RE = re.compile(r"\s+")
_ASCII_SLUG_RE = re.compile(r"[^0-9A-Za-z_.-]+")


def _truncate(value: str, limit: int = 120) -> str:
    if len(value) <= limit:
        return value
    return value[:limit].rstrip(" .-_")


def _safe_name(value: str, fallback: str) -> str:
    name = _INVALID_PATH_CHARS_RE.sub(" ", value)
    name = _SPACE_RE.sub(" ", name).strip(" .-_")
    return _truncate(name) or fallback


def _ascii_slug(value: str, fallback: str) -> str:
    slug = _ASCII_SLUG_RE.sub("-", value).strip("-._")
    return _truncate(slug, 96) or fallback


def _url_hash(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _make_batch_slug(articles: list[dict]) -> str:
    """Generate a batch slug from the first article's title or URL."""
    if not articles:
        return "washed"
    first = articles[0]
    title = str(first.get("title") or "").strip()
    url = str(first.get("url") or "").strip()
    if title:
        return _safe_name(title, _ascii_slug(title, _url_hash(url)))
    return _url_hash(url)


# ---- HTTP helpers (same style as batch_video_notes.py) ----------------------

def post_json(url: str, data: dict, timeout: int = 60) -> dict:
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str, timeout: int = 60) -> dict:
    with urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---- manifest loading -------------------------------------------------------

def load_article_manifest(path: Path) -> dict:
    """Load article manifest (JSON array or object with articles/code_projects).

    Returns dict with keys: articles (list of {url, title, slug}), code_projects (list or None).
    """
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(raw, list):
        items = raw
        code_projects = None
    elif isinstance(raw, dict):
        items = raw.get("articles") or raw.get("items") or []
        code_projects = raw.get("code_projects")
    else:
        raise ValueError("Manifest must be a JSON list or an object with 'articles' key")

    if not isinstance(items, list):
        raise ValueError("Manifest must contain a list of articles")

    articles = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        title = str(item.get("title") or "").strip()
        slug = _make_batch_slug([item])
        articles.append({"slug": slug, "title": title, "url": url})

    if not articles:
        raise ValueError(f"Manifest has no valid articles: {path}")

    return {"articles": articles, "code_projects": code_projects}


# ---- core processing --------------------------------------------------------

def process_batch(args, out_dir: Path) -> dict:
    """Send ALL articles in one batch to the v2 /washing/wash endpoint."""
    manifest_data = load_article_manifest(args.manifest)
    articles = manifest_data["articles"]
    code_projects = manifest_data.get("code_projects") or args.code_projects_json

    slug = _make_batch_slug(articles)
    status = {
        "slug": slug,
        "article_count": len(articles),
        "articles": [{"title": a["title"], "url": a["url"]} for a in articles],
    }

    # Build API payload
    payload = {
        "articles": [{"url": a["url"], "title": a["title"] or None} for a in articles],
        "context_prompt": args.context_prompt,
        "refinement_prompt": args.refinement_prompt,
        "style": args.style,
        "max_tokens": args.max_tokens,
        "timeout": args.timeout,
    }

    if code_projects:
        payload["code_projects"] = code_projects
        status["code_projects"] = code_projects

    print(
        json.dumps(
            {
                "stage": "request",
                "slug": slug,
                "articles": len(articles),
                "code_projects": len(code_projects) if code_projects else 0,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    result = post_json(f"{API_BASE}/washing/wash", payload, timeout=args.timeout)
    data = result.get("data", result)

    # Extract v2 response fields
    extracted_articles = data.get("extracted_articles") or []
    code_files = data.get("code_files") or []
    domain_summary = data.get("domain_summary") or ""
    refined_output = data.get("refined_output") or ""
    stage1_prompt = data.get("stage1_prompt") or ""
    stage2_prompt = data.get("stage2_prompt") or ""

    # Create output directory
    batch_dir = out_dir / slug
    batch_dir.mkdir(parents=True, exist_ok=True)

    # Save refined output
    notes_path = batch_dir / "notes.md"
    notes_path.write_text(refined_output, encoding="utf-8")
    status["notes_chars"] = len(refined_output)

    # Save domain summary
    if domain_summary:
        (batch_dir / "domain_summary.md").write_text(domain_summary, encoding="utf-8")

    # Save sources (extracted articles metadata)
    sources = []
    for art in extracted_articles:
        sources.append({
            "url": art.get("url", ""),
            "title": art.get("title", ""),
            "extraction_method": art.get("extraction_method", ""),
            "key_points": art.get("key_points", ""),
            "metadata": art.get("metadata"),
        })
    (batch_dir / "sources.json").write_text(
        json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Save code files reference
    if code_files:
        (batch_dir / "code_files.json").write_text(
            json.dumps(code_files, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Save prompts for reproducibility
    if stage1_prompt:
        (batch_dir / "stage1_prompt.md").write_text(stage1_prompt, encoding="utf-8")
    if stage2_prompt:
        (batch_dir / "stage2_prompt.md").write_text(stage2_prompt, encoding="utf-8")

    status["sources"] = len(sources)
    status["code_files"] = len(code_files)
    status["has_domain_summary"] = bool(domain_summary)

    print(
        json.dumps(
            {
                "stage": "done",
                "slug": slug,
                "notes_chars": len(refined_output),
                "sources": len(sources),
                "code_files": len(code_files),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return status


# ---- main -------------------------------------------------------------------

def main() -> int:
    global API_BASE
    parser = argparse.ArgumentParser(
        description="Batch article washing / content refinement (v2 two-stage pipeline)"
    )
    parser.add_argument(
        "--manifest", required=True, type=Path,
        help="JSON manifest of articles [{url, title}] or {articles: [...], code_projects: [...]}"
    )
    parser.add_argument("--api-base", default=API_BASE, help="Backend API base URL")
    parser.add_argument(
        "--context-prompt", required=True,
        help="Stage 1 context prompt describing what the articles are about"
    )
    parser.add_argument(
        "--refinement-prompt", required=True,
        help="Stage 2 refinement prompt for how to deepen the knowledge"
    )
    parser.add_argument(
        "--code-projects", default=None,
        help="JSON string of code projects [{label, path, file_patterns?}]. "
             "Overrides code_projects in manifest."
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Output directory (default: <project>/output/article_washing)"
    )
    parser.add_argument(
        "--style", default="deep",
        choices=["deep", "concise", "comprehensive"],
        help="Output style (default: deep)"
    )
    parser.add_argument("--timeout", type=int, default=900, help="API timeout in seconds")
    parser.add_argument("--max-tokens", type=int, default=16384, help="Max output tokens")
    args = parser.parse_args()

    API_BASE = args.api_base.rstrip("/")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    # Parse code-projects JSON if provided
    args.code_projects_json = None
    if args.code_projects:
        try:
            args.code_projects_json = json.loads(args.code_projects)
        except json.JSONDecodeError as exc:
            print(f"Error parsing --code-projects JSON: {exc}", file=sys.stderr)
            return 1

    root = Path(__file__).resolve().parents[1]
    out_dir = args.output_dir or (root / "output" / "article_washing")

    try:
        status = process_batch(args, out_dir)
    except Exception as exc:
        print(
            json.dumps({"stage": "failed", "error": str(exc)}, ensure_ascii=False),
            flush=True,
        )
        return 1

    batch_path = out_dir / "batch_status.json"
    existing = []
    if batch_path.exists():
        try:
            existing = json.loads(batch_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    existing.append(status)
    batch_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nDone! Output: {out_dir / status['slug']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

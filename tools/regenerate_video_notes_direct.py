# -*- coding: utf-8 -*-
"""Regenerate one saved video note directly through Codex CLI.

This runner bypasses the backend HTTP endpoint so multiple videos can be run in
parallel. It still reuses the backend prompt, chunking, merge, and quality
helpers to keep output quality aligned with the app workflow.
"""

import argparse
import json
import re
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
    scale_merge_targets,
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


def completed_after_cache_epoch(out_dir: Path, args) -> bool:
    if args.cache_after_epoch is None:
        return False
    quality_path = out_dir / "backend_video_notes_quality.json"
    notes_path = out_dir / "notes.md"
    html_path = out_dir / "notes.html"
    if not quality_path.exists() or not notes_path.exists() or not html_path.exists():
        return False
    if quality_path.stat().st_mtime < args.cache_after_epoch:
        return False
    try:
        payload = load_json(quality_path)
    except Exception:
        return False
    return bool((payload.get("quality") or {}).get("passed"))


def matches_selector(status: dict, selector: str, folder_name: str) -> bool:
    return selector in {
        folder_name,
        status.get("slug"),
        status.get("source_id"),
        status.get("legacy_slug"),
        status.get("title"),
    }


def resolve_output_dir(selector: str) -> Path:
    exact = ROOT / "output" / selector
    if (exact / "status.json").exists():
        return exact

    output_root = ROOT / "output"
    if output_root.exists():
        for candidate in output_root.iterdir():
            status_path = candidate / "status.json"
            if not candidate.is_dir() or not status_path.exists():
                continue
            try:
                status = load_json(status_path)
            except Exception:
                continue
            if matches_selector(status, selector, candidate.name):
                return candidate
    raise RuntimeError(f"Output folder not found for selector: {selector}")


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


def chunk_cache_is_valid(note_path: Path, args) -> bool:
    if not note_path.exists() or args.force_chunks:
        return False
    if args.cache_after_epoch is None:
        return True
    return note_path.stat().st_mtime >= args.cache_after_epoch


RECURRING_ASSEMBLY_SECTION_ORDER = [
    "核心结论",
    "易错点与调试建议",
    "术语表",
    "实践清单",
    "复习问题",
]
RECURRING_ASSEMBLY_SECTIONS = set(RECURRING_ASSEMBLY_SECTION_ORDER)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TIME_SUFFIX_RE = re.compile(r"\s*\[[^\]]+\]\s*$")


def normalize_heading_title(title: str) -> str:
    return TIME_SUFFIX_RE.sub("", title.strip()).strip()


def is_recurring_container_heading(title: str) -> bool:
    return sum(1 for section in RECURRING_ASSEMBLY_SECTIONS if section in title) >= 2


def add_recurring_line(recurring_sections: dict[str, list[str]], section: str, line: str) -> None:
    value = line.strip()
    if not value or value.startswith("#image["):
        return
    bucket = recurring_sections.setdefault(section, [])
    key = re.sub(r"\s+", "", re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", value))
    seen_keys = {
        re.sub(r"\s+", "", re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", item.strip()))
        for item in bucket
    }
    if key and key not in seen_keys:
        bucket.append(value)


def normalize_chunk_note_for_assembly(note: str, recurring_sections: dict[str, list[str]] | None = None) -> str:
    lines = []
    recurring_section: str | None = None
    for raw_line in note.strip().splitlines():
        line = raw_line.rstrip()
        heading_match = HEADING_RE.match(line)
        if heading_match and len(heading_match.group(1)) <= 3:
            heading = heading_match.group(2).strip()
            normalized_heading = normalize_heading_title(heading)
            if recurring_sections is not None and normalized_heading in RECURRING_ASSEMBLY_SECTIONS:
                recurring_section = normalized_heading
                recurring_sections.setdefault(recurring_section, [])
                continue
            if recurring_sections is not None and is_recurring_container_heading(normalized_heading):
                recurring_section = None
                continue
            recurring_section = None
            if len(heading_match.group(1)) == 1:
                continue
            lines.append(f"### {heading}")
            continue

        if recurring_section:
            if recurring_sections is not None:
                add_recurring_line(recurring_sections, recurring_section, line)
            continue

        if line.startswith("#### "):
            heading = re.sub(r"^#+\s+", "", line).strip()
            lines.append(f"**{heading}**")
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def overall_chunk_range(chunk_ranges: list[str]) -> str:
    valid_ranges = [item for item in chunk_ranges if "-" in item]
    if not valid_ranges:
        return ""
    start = valid_ranges[0].split("-", 1)[0].strip()
    end = valid_ranges[-1].rsplit("-", 1)[-1].strip()
    if not start or not end:
        return ""
    return f"{start}-{end}"


def render_recurring_sections(recurring_sections: dict[str, list[str]], time_range: str) -> str:
    parts = []
    heading = "## 汇总复习材料"
    if time_range:
        heading += f" [{time_range}]"
    for section in RECURRING_ASSEMBLY_SECTION_ORDER:
        lines = recurring_sections.get(section) or []
        if not lines:
            continue
        if not parts:
            parts.append(heading)
        subheading = f"### 全局{section}"
        if time_range:
            subheading += f" [{time_range}]"
        parts.extend(["", subheading, *lines])
    return "\n".join(parts).strip()


def assemble_chunk_notes(title: str, source_url: str | None, chunk_notes: list[str], chunk_ranges: list[str]) -> str:
    learning_range = overall_chunk_range(chunk_ranges)
    learning_heading = "## 学习路线"
    if learning_range:
        learning_heading += f" [{learning_range}]"
    parts = [
        f"# {title}",
        "",
        learning_heading,
        "这份笔记按视频时间顺序组织，每一部分对应原视频的一个连续时间段。内容保留分块生成时的讲义式说明、关键截图标记和技术细节，便于后续按主题或时间回看。",
    ]
    if source_url:
        parts.extend(["", f"来源：{source_url}"])
    recurring_sections: dict[str, list[str]] = {}
    for index, note in enumerate(chunk_notes):
        time_range = chunk_ranges[index] if index < len(chunk_ranges) else ""
        heading = f"## 第 {index + 1} 部分"
        if time_range:
            heading += f" [{time_range}]"
        parts.extend(["", heading, "", normalize_chunk_note_for_assembly(note, recurring_sections)])
    recurring_summary = render_recurring_sections(recurring_sections, learning_range)
    if recurring_summary:
        parts.extend(["", recurring_summary])
    return "\n".join(part for part in parts if part is not None).strip() + "\n"


def run_chunked(video: dict, out_dir: Path, segments: list[dict], args) -> tuple[str, str, int]:
    chunk_dir = out_dir / "direct_chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunks = split_segments(segments, args.chunk_minutes)
    chunk_notes = []
    chunk_ranges = []
    for index, chunk in enumerate(chunks):
        note_path = chunk_dir / f"chunk_{index + 1:02d}.md"
        prompt_path = chunk_dir / f"chunk_{index + 1:02d}.prompt.md"
        part_label = (
            f"{index + 1}/{len(chunks)} "
            f"[{format_time_ms(chunk[0]['start_time'])}-{format_time_ms(chunk[-1]['end_time'])}]"
        )
        chunk_ranges.append(f"{format_time_ms(chunk[0]['start_time'])}-{format_time_ms(chunk[-1]['end_time'])}")
        prompt = build_video_notes_prompt(
            title=video["title"],
            source_url=video.get("source_url"),
            segments=chunk,
            remarks=args.remarks,
            part_label=part_label,
            max_tokens=args.max_tokens,
        )
        prompt_path.write_text(prompt, encoding="utf-8")
        if chunk_cache_is_valid(note_path, args):
            note = note_path.read_text(encoding="utf-8")
            log_event({"stage": "chunk-cache", "slug": video["slug"], "chunk": index + 1, "chunks": len(chunks)})
        else:
            log_event({"stage": "chunk-start", "slug": video["slug"], "chunk": index + 1, "chunks": len(chunks)})
            note = run_codex_cli(prompt, args.llm_timeout)
            note_path.write_text(note, encoding="utf-8")
            log_event({"stage": "chunk-done", "slug": video["slug"], "chunk": index + 1, "chars": len(note)})
        chunk_notes.append(note)

    targets = notes_density_targets(segments)
    if args.merge_strategy == "assemble":
        log_event({"stage": "merge-assemble", "slug": video["slug"], "chunks": len(chunks)})
        content = assemble_chunk_notes(video["title"], video.get("source_url"), chunk_notes, chunk_ranges)
        prompt_used = "local chunk assembly; no Codex merge prompt"
        (out_dir / "direct_merge_prompt.md").write_text(prompt_used, encoding="utf-8")
        return content, prompt_used, len(chunks)

    merge_inputs = chunk_notes
    if args.merge_group_size >= 2 and len(chunk_notes) > args.merge_group_size:
        grouped_notes = []
        group_count = (len(chunk_notes) + args.merge_group_size - 1) // args.merge_group_size
        for start in range(0, len(chunk_notes), args.merge_group_size):
            group_index = start // args.merge_group_size + 1
            group = chunk_notes[start : start + args.merge_group_size]
            note_path = chunk_dir / f"merge_group_g{args.merge_group_size}_{group_index:02d}.md"
            prompt_path = chunk_dir / f"merge_group_g{args.merge_group_size}_{group_index:02d}.prompt.md"
            group_targets = scale_merge_targets(targets, len(group), len(chunk_notes))
            group_prompt = build_merge_prompt(
                f"{video['title']} 分组合并 {group_index}/{group_count}",
                video.get("source_url"),
                group,
                group_targets,
                args.remarks,
                max_tokens=args.max_tokens,
            )
            prompt_path.write_text(group_prompt, encoding="utf-8")
            if chunk_cache_is_valid(note_path, args):
                grouped_note = note_path.read_text(encoding="utf-8")
                log_event({"stage": "merge-group-cache", "slug": video["slug"], "group": group_index, "groups": group_count})
            else:
                log_event({"stage": "merge-group-start", "slug": video["slug"], "group": group_index, "groups": group_count})
                grouped_note = run_codex_cli(group_prompt, args.llm_timeout)
                note_path.write_text(grouped_note, encoding="utf-8")
                log_event({"stage": "merge-group-done", "slug": video["slug"], "group": group_index, "chars": len(grouped_note)})
            grouped_notes.append(grouped_note)
        merge_inputs = grouped_notes

    merge_prompt = build_merge_prompt(
        video["title"],
        video.get("source_url"),
        merge_inputs,
        targets,
        args.remarks,
        max_tokens=args.max_tokens,
    )
    merge_prompt_path = out_dir / "direct_merge_prompt.md"
    merge_prompt_path.write_text(merge_prompt, encoding="utf-8")
    log_event({"stage": "merge-start", "slug": video["slug"], "chunks": len(chunks), "inputs": len(merge_inputs)})
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
    out_dir = resolve_output_dir(slug)
    slug = out_dir.name
    if completed_after_cache_epoch(out_dir, args):
        log_event({"stage": "skip-complete", "slug": slug, "cache_after_epoch": args.cache_after_epoch})
        return load_status(out_dir)
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
    parser.add_argument("--remarks", default="请按讲义式高密度技术复习资料输出，用自然段解释机制和取舍，不要把主体写成项目符号清单，也不要压缩关键细节。")
    parser.add_argument("--no-quality-retry", dest="quality_retry", action="store_false")
    parser.add_argument("--no-clear-screenshots", dest="clear_screenshots", action="store_false")
    parser.add_argument("--force-chunks", action="store_true")
    parser.add_argument(
        "--cache-after-epoch",
        type=float,
        help="Only reuse existing chunk files whose modified time is at or after this epoch timestamp.",
    )
    parser.add_argument("--merge-group-size", type=int, default=3)
    parser.add_argument("--merge-strategy", choices=["codex", "assemble"], default="codex")
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

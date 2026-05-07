# -*- coding: utf-8 -*-
import argparse
from contextlib import contextmanager
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

from video_manifest import load_manifest, select_videos


API_BASE = "http://127.0.0.1:8080/api/v1"


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


def find_transcription_task(filename: str) -> dict | None:
    tasks_payload = get_json(f"{API_BASE}/audio/transcription-tasks", timeout=30)
    tasks = tasks_payload.get("data", {}).get("tasks", [])
    matches = [
        task
        for task in tasks
        if task.get("filename") == filename and task.get("status") in {"running", "finished"}
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda task: task.get("created_at") or 0)[-1]


def wait_for_transcription_task(task_id: str, video_slug: str, poll_interval: int) -> list[dict]:
    while True:
        task_payload = get_json(f"{API_BASE}/audio/transcription-tasks/{task_id}", timeout=30)
        task_data = task_payload["data"]
        print(
            json.dumps(
                {"stage": "asr", "slug": video_slug, "status": task_data["status"]},
                ensure_ascii=False,
            ),
            flush=True,
        )
        if task_data["status"] == "finished":
            return task_data["result"]
        if task_data["status"] == "failed":
            raise RuntimeError(task_data.get("error") or "ASR failed")
        time.sleep(poll_interval)


@contextmanager
def asr_lock(root: Path, video_slug: str, poll_interval: int):
    lock_dir = root / "output" / ".asr_gpu.lock"
    while True:
        try:
            lock_dir.mkdir(parents=True)
            (lock_dir / "owner.txt").write_text(video_slug, encoding="utf-8")
            print(
                json.dumps({"stage": "asr-lock", "slug": video_slug, "status": "acquired"}, ensure_ascii=False),
                flush=True,
            )
            break
        except FileExistsError:
            owner_path = lock_dir / "owner.txt"
            owner = owner_path.read_text(encoding="utf-8").strip() if owner_path.exists() else "unknown"
            print(
                json.dumps(
                    {"stage": "asr-lock", "slug": video_slug, "status": "waiting", "owner": owner},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            time.sleep(poll_interval)
    try:
        yield
    finally:
        try:
            (lock_dir / "owner.txt").unlink(missing_ok=True)
            lock_dir.rmdir()
        except OSError:
            pass
        print(
            json.dumps({"stage": "asr-lock", "slug": video_slug, "status": "released"}, ensure_ascii=False),
            flush=True,
        )


def fmt_time(ms: int) -> str:
    total = int(ms // 1000)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def srt_time(ms: int) -> str:
    total_ms = int(ms)
    h = total_ms // 3600000
    total_ms %= 3600000
    m = total_ms // 60000
    total_ms %= 60000
    s = total_ms // 1000
    ms = total_ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_transcripts(out_dir: Path, segments: list[dict]):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "transcript.json").write_text(
        json.dumps(segments, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = []
    for index, seg in enumerate(segments, 1):
        lines.extend(
            [
                str(index),
                f"{srt_time(seg['start_time'])} --> {srt_time(seg['end_time'])}",
                seg["text"],
                "",
            ]
        )
    (out_dir / "transcript.srt").write_text("\n".join(lines), encoding="utf-8")


def format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def density_targets(segments: list[dict]) -> dict:
    duration_seconds = max(1, int((segments[-1]["end_time"] - segments[0]["start_time"]) / 1000))
    duration_minutes = duration_seconds / 60
    if duration_minutes <= 30:
        screenshots = "6-10"
        chapters = "5-8"
        note_chars = "8000-12000"
    elif duration_minutes <= 60:
        screenshots = "10-16"
        chapters = "8-12"
        note_chars = "14000-22000"
    elif duration_minutes <= 120:
        screenshots = "16-26"
        chapters = "12-20"
        note_chars = "28000-45000"
    else:
        screenshots = "24-36"
        chapters = "18-28"
        note_chars = "42000-65000"
    return {
        "duration_seconds": duration_seconds,
        "duration_text": format_duration(duration_seconds),
        "screenshots": screenshots,
        "chapters": chapters,
        "note_chars": note_chars,
    }


def build_prompt(video: dict, segments: list[dict]) -> str:
    targets = density_targets(segments)
    source = video.get("url") or video.get("source_url") or video["slug"]
    lines = []
    for seg in segments:
        start_s = seg["start_time"] // 1000
        end_s = seg["end_time"] // 1000
        lines.append(
            f"[{fmt_time(seg['start_time'])}-{fmt_time(seg['end_time'])} seconds:{start_s}-{end_s}] {seg['text']}"
        )
    transcript = "\n".join(lines)
    return f"""你是一位 Unreal Engine / 游戏技术课程的高密度知识整理专家。

视频标题：{video['title']}
来源：{source}
视频时长：约 {targets['duration_text']}
任务：根据下面带时间戳的转写稿，生成中文 Markdown 深度学习笔记。目标是让读者不看原视频，也能像阅读课程讲义一样理解主要技术内容、关键细节和实践方法。

硬性要求：
1. 只输出 Markdown 正文，不要解释执行过程。
2. 默认输出中文；英文字幕需要翻译成自然中文。Unreal/Lyra/GAS/Common UI/Animation/Rendering 等专业术语保留英文，并在首次出现时补充中文解释。
3. 内容完整优先于简短。不要只写结论，必须保留重要概念、系统关系、实现步骤、配置项、类名、函数名、蓝图节点、调试方法、示例、注意事项、适用场景和讲者强调的经验。
4. 可以删除寒暄、重复口癖、直播互动闲聊和无技术含量内容，但不要删掉技术推导、操作流程和上下文原因。
5. 标题层级只使用 `#`、`##`、`###`，不允许跳级；只使用一个 `#` 主标题。
6. 每个 `##` 章节标题后必须带时间范围，例如 `## 核心机制 [00:00-04:30]`。每个 `###` 小节也尽量带时间范围。
7. 时间范围必须基于字幕时间信息，格式为 `[mm:ss-mm:ss]` 或 `[hh:mm:ss-hh:mm:ss]`，00 小时时隐藏小时。
8. 章节数量建议 {targets['chapters']} 个。主体必须采用“讲义式陈述”：每个 `###` 小节先用 2-4 个自然段解释清楚，每段 2-4 句，段落中要写明是什么、为什么、怎么运作、工程取舍和实际例子。
9. 目标笔记长度约 {targets['note_chars']} 个中文字符。不要把 30 分钟以上内容压缩成几个泛泛结论。
10. 对关键概念尽量补充“为什么重要 / 适用场景 / 常见坑 / 和其他系统的关系”。
11. 插入 {targets['screenshots']} 个截图标记。截图标记必须单独一行，且只能是 `#image[整数秒]`，例如 `#image[120]`。
12. `#image[]` 中只能写阿拉伯数字，不能写中文、说明文字、冒号或单位。
13. 秒数必须来自转写稿附近，选择适合看 PPT、架构图、编辑器操作、代码、蓝图、效果对比或演示画面的时刻。
14. 不要虚构视频中没有的信息。ASR 可能有误，请结合 Unreal Engine 技术术语合理纠错，但不能编造不存在的 API 或流程。
15. 不要把主体写成连续项目符号清单。列表只能用于流程步骤、参数/组件对比、术语表、实践清单、复习问题和少量核心结论；普通概念解释必须写成完整陈述句。
16. 不要在每个小节机械套用“背景与问题 / 核心机制 / 实现步骤 / 注意事项”的固定列表。需要这些内容时，把它们自然融入段落。
17. 允许保留高密度，但密度要来自具体机制、因果关系、设计动机、工程代价和例子，而不是把短句堆成条目。

建议输出结构：
# 主标题
## 核心结论 [时间]
此处可以用 6-10 条项目符号快速概览，但不要替代后文讲义式解释。
## 主题章节 [时间]
### 子主题 [时间]
先写自然段解释，再在必要时使用短列表整理步骤、对比或检查项。
## 易错点与调试建议
## 术语表
## 实践清单
## 复习问题

转写稿：
{transcript}
"""


def run_codex(out_dir: Path, timeout_seconds: int):
    prompt_path = out_dir / "codex_prompt.md"
    output_path = out_dir / "notes_raw.md"
    codex_cmd = (
        shutil.which("codex.cmd")
        or shutil.which("codex.exe")
        or shutil.which("codex")
        or "codex"
    )
    cmd = [
        codex_cmd,
        "exec",
        "-m",
        "gpt-5.5",
        "-c",
        'model_reasoning_effort="xhigh"',
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--output-last-message",
        str(output_path),
        "-",
    ]
    with prompt_path.open("rb") as stdin:
        subprocess.run(cmd, stdin=stdin, check=True, timeout=timeout_seconds)


def get_ffmpeg(root: Path) -> str:
    return subprocess.check_output(
        [
            str(root / "backend" / ".venv" / "Scripts" / "python.exe"),
            "-c",
            "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())",
        ],
        text=True,
        encoding="utf-8",
    ).strip()


def fallback_marker_times(segments: list[dict], count: int) -> list[int]:
    start = segments[0]["start_time"] // 1000
    end = segments[-1]["end_time"] // 1000
    if count <= 1:
        return [int((start + end) / 2)]
    span = max(1, end - start)
    return [int(start + span * (i + 1) / (count + 1)) for i in range(count)]


def screenshot_alt_text(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        timestamp = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        timestamp = f"{minutes:02d}:{secs:02d}"
    return f"视频截图 {timestamp}"


def finalize_notes(root: Path, out_dir: Path, video_filename: str, segments: list[dict]):
    raw = (out_dir / "notes_raw.md").read_text(encoding="utf-8")
    markers = re.findall(r"^#image\[[^\]]+\]$", raw, flags=re.MULTILINE)
    numeric_times = []
    invalid_markers = []
    for marker in markers:
        match = re.match(r"^#image\[(\d+)\]$", marker)
        if match:
            numeric_times.append(int(match.group(1)))
        else:
            invalid_markers.append(marker)
    if invalid_markers:
        numeric_times = fallback_marker_times(segments, len(markers))
    if not markers:
        numeric_times = fallback_marker_times(segments, 7)
        markers = [f"@@AUTO_IMAGE_{idx}@@" for idx in range(len(numeric_times))]
        insertion_points = list(re.finditer(r"^## .+$", raw, flags=re.MULTILINE))
        result = raw
        offset = 0
        for marker, header_match in zip(markers, insertion_points[1:]):
            pos = header_match.end() + offset
            insert = f"\n\n{marker}\n"
            result = result[:pos] + insert + result[pos:]
            offset += len(insert)
        raw = result

    screenshots_dir = out_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = get_ffmpeg(root)
    video_path = root / "backend" / "local_storage" / "media" / video_filename

    result = raw
    for marker, seconds in zip(markers, numeric_times):
        image_name = f"{seconds:06d}.jpg"
        image_path = screenshots_dir / image_name
        if not image_path.exists():
            cmd = [
                ffmpeg,
                "-y",
                "-ss",
                str(seconds),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(image_path),
            ]
            completed = subprocess.run(cmd, capture_output=True, check=False)
            if completed.returncode != 0 or not image_path.exists():
                details = (completed.stderr or completed.stdout).decode(
                    "utf-8", errors="replace"
                )
                raise RuntimeError(f"ffmpeg screenshot failed at {seconds}s: {details}")
        alt = screenshot_alt_text(seconds)
        result = result.replace(marker, f"![{alt}](screenshots/{image_name})", 1)

    (out_dir / "notes.md").write_text(result, encoding="utf-8")
    return numeric_times


def render_html(out_dir: Path):
    from markdown_it import MarkdownIt

    body = MarkdownIt("commonmark", {"html": True}).enable("table").render(
        (out_dir / "notes.md").read_text(encoding="utf-8")
    )
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>视频知识笔记</title>
  <style>
    body {{ margin: 0; background: #f6f7f9; color: #222; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif; line-height: 1.75; }}
    main {{ max-width: min(1440px, calc(100vw - 32px)); margin: 0 auto; padding: 40px 22px 80px; background: #fff; }}
    h1, h2, h3 {{ line-height: 1.35; }}
    h1 {{ font-size: 2rem; border-bottom: 1px solid #e5e7eb; padding-bottom: 16px; }}
    h2 {{ margin-top: 36px; border-left: 4px solid #111827; padding-left: 12px; }}
    img {{ max-width: 100%; height: auto; display: block; margin: 14px auto 24px; border-radius: 8px; box-shadow: 0 8px 28px rgba(15, 23, 42, .14); }}
    code {{ background: #f1f5f9; padding: 0.12em 0.35em; border-radius: 4px; }}
    pre {{ background: #0f172a; color: #e5e7eb; padding: 16px; border-radius: 8px; overflow: auto; }}
    pre code {{ background: transparent; padding: 0; }}
    table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px 10px; vertical-align: top; }}
    th {{ background: #f3f4f6; }}
  </style>
</head>
<body><main>
{body}
</main></body>
</html>
"""
    (out_dir / "notes.html").write_text(html, encoding="utf-8")


def process_video(root: Path, video: dict, args) -> dict:
    out_dir = root / "output" / video["slug"]
    out_dir.mkdir(parents=True, exist_ok=True)
    status = {
        "slug": video["slug"],
        "source_id": video.get("source_id"),
        "title": video["title"],
        "out_dir": str(out_dir),
    }

    media = post_json(
        f"{API_BASE}/files/media-from-url",
        {"url": video["url"]},
        timeout=args.media_timeout,
    )
    if not media.get("success"):
        raise RuntimeError(media)
    media_data = media["data"]
    status["media"] = media_data
    print(
        json.dumps(
            {
                "stage": "media",
                "slug": video["slug"],
                "cache_hit": media_data.get("cache_hit"),
                "cache_source": media_data.get("cache_source"),
                "duration": media_data.get("duration"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    transcript_path = out_dir / "transcript.json"
    if transcript_path.exists() and not args.force_asr:
        segments = json.loads(transcript_path.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {"stage": "asr-cache", "slug": video["slug"], "segments": len(segments)},
                ensure_ascii=False,
            ),
            flush=True,
        )
    else:
        existing_task = None if args.force_asr else find_transcription_task(media_data["audio_filename"])
        if existing_task:
            task_id = existing_task["task_id"]
            print(
                json.dumps(
                    {
                        "stage": "asr-existing",
                        "slug": video["slug"],
                        "task_id": task_id,
                        "status": existing_task["status"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        else:
            with asr_lock(root, video["slug"], args.poll_interval):
                task = post_json(
                    f"{API_BASE}/audio/transcription-tasks",
                    {"filename": media_data["audio_filename"]},
                    timeout=30,
                )
                task_id = task["data"]["task_id"]
                status["task_id"] = task_id
                segments = wait_for_transcription_task(task_id, video["slug"], args.poll_interval)
                print(
                    json.dumps({"stage": "asr-save", "slug": video["slug"]}, ensure_ascii=False),
                    flush=True,
                )
                write_transcripts(out_dir, segments)
                segments = json.loads(transcript_path.read_text(encoding="utf-8"))
                existing_task = {"task_id": task_id}
        status["task_id"] = task_id
        if existing_task and existing_task.get("task_id") == task_id and not transcript_path.exists():
            segments = wait_for_transcription_task(task_id, video["slug"], args.poll_interval)
            print(
                json.dumps({"stage": "asr-save", "slug": video["slug"]}, ensure_ascii=False),
                flush=True,
            )

    write_transcripts(out_dir, segments)
    prompt = build_prompt(video, segments)
    (out_dir / "codex_prompt.md").write_text(prompt, encoding="utf-8")
    status["segments"] = len(segments)
    print(
        json.dumps(
            {"stage": "prompt", "slug": video["slug"], "segments": len(segments), "chars": len(prompt)},
            ensure_ascii=False,
        ),
        flush=True,
    )

    if args.skip_codex:
        status["skipped_codex"] = True
        (out_dir / "status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {"stage": "skip-codex", "slug": video["slug"], "out_dir": str(out_dir)},
                ensure_ascii=False,
            ),
            flush=True,
        )
        return status

    if not (out_dir / "notes_raw.md").exists() or args.force_codex:
        run_codex(out_dir, args.codex_timeout)
    else:
        print(
            json.dumps({"stage": "codex-cache", "slug": video["slug"]}, ensure_ascii=False),
            flush=True,
        )
    if args.force_codex:
        screenshots_dir = out_dir / "screenshots"
        if screenshots_dir.exists():
            for image_path in screenshots_dir.glob("*.jpg"):
                image_path.unlink()
    times = finalize_notes(root, out_dir, media_data["video_filename"], segments)
    render_html(out_dir)
    status["screenshots"] = times
    (out_dir / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"stage": "done", "slug": video["slug"], "screenshots": len(times), "out_dir": str(out_dir)},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return status


def main():
    global API_BASE
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path, help="JSON/JSONL video manifest with slug, title, url")
    parser.add_argument("--only", nargs="*", help="Only process these slugs")
    parser.add_argument("--start-at", help="Start at this slug")
    parser.add_argument("--poll-interval", type=int, default=30)
    parser.add_argument("--media-timeout", type=int, default=600)
    parser.add_argument("--codex-timeout", type=int, default=3600)
    parser.add_argument("--api-base", default=API_BASE, help="Backend API base URL, for example http://127.0.0.1:8080/api/v1")
    parser.add_argument("--force-asr", action="store_true")
    parser.add_argument("--force-codex", action="store_true")
    parser.add_argument("--skip-codex", action="store_true", help="Only download media and write transcripts/status.")
    args = parser.parse_args()
    API_BASE = args.api_base.rstrip("/")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    root = Path(__file__).resolve().parents[1]
    videos = select_videos(load_manifest(args.manifest), args.only, args.start_at)

    all_status = []
    for video in videos:
        try:
            all_status.append(process_video(root, video, args))
        except Exception as exc:
            failure = {"slug": video["slug"], "title": video["title"], "error": str(exc)}
            all_status.append(failure)
            print(json.dumps({"stage": "failed", **failure}, ensure_ascii=False), flush=True)

    batch_path = root / "output" / "batch_status.json"
    batch_path.write_text(json.dumps(all_status, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [item for item in all_status if "error" in item]
    if failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen


API_BASE = "http://127.0.0.1:8080/api/v1"


VIDEOS = [
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
]


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


def build_prompt(video: dict, segments: list[dict]) -> str:
    lines = []
    for seg in segments:
        start_s = seg["start_time"] // 1000
        end_s = seg["end_time"] // 1000
        lines.append(
            f"[{fmt_time(seg['start_time'])}-{fmt_time(seg['end_time'])} seconds:{start_s}-{end_s}] {seg['text']}"
        )
    transcript = "\n".join(lines)
    return f"""你是一个严谨的 Unreal Engine 技术学习笔记整理助手。

视频标题：{video['title']}
来源：Bilibili {video['slug']}
任务：根据下面带时间戳的转写稿，生成中文 Markdown 知识笔记。

硬性要求：
1. 输出中文 Markdown 正文，不要解释执行过程。
2. 按主题组织，不要逐字翻译；保留关键概念、定义、系统结构、实践步骤、代码/蓝图工作流、调试方法、注意事项和结论。
3. 每个主要章节标题后必须带时间范围，例如 `## 核心机制 [00:00-04:30]`。
4. Unreal/Lyra/AbilitySystem/Animation/UI/Rendering 相关术语可保留英文，并补充中文解释。
5. 插入 6-9 个截图标记。截图标记必须单独一行，且只能是 `#image[整数秒]`，例如 `#image[120]`。
6. `#image[]` 中只能写阿拉伯数字，不能写中文、说明文字、冒号或单位。
7. 秒数必须来自转写稿附近，选择适合看 PPT、架构图、编辑器操作、代码、蓝图或演示画面的时刻。
8. 不要虚构没有出现的细节。ASR 可能有误，请结合 Unreal Engine 技术术语合理纠错。

建议结构：
# 主标题
## 核心结论 [时间]
## 主题章节 [时间]
### 子主题 [时间]
- 要点
## 术语表
## 实践建议
## 总结

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
                "-vf",
                "scale=min(1280\\,iw):-2",
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
        alt = marker.removeprefix("#image[").removesuffix("]")
        if marker.startswith("@@AUTO_IMAGE_"):
            alt = f"{seconds}s"
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
    main {{ max-width: 980px; margin: 0 auto; padding: 40px 22px 80px; background: #fff; }}
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
    status = {"slug": video["slug"], "title": video["title"], "out_dir": str(out_dir)}

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
        task = post_json(
            f"{API_BASE}/audio/transcription-tasks",
            {"filename": media_data["audio_filename"]},
            timeout=30,
        )
        task_id = task["data"]["task_id"]
        status["task_id"] = task_id
        while True:
            time.sleep(args.poll_interval)
            task_payload = get_json(f"{API_BASE}/audio/transcription-tasks/{task_id}", timeout=30)
            task_data = task_payload["data"]
            print(
                json.dumps(
                    {"stage": "asr", "slug": video["slug"], "status": task_data["status"]},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if task_data["status"] == "finished":
                segments = task_data["result"]
                break
            if task_data["status"] == "failed":
                raise RuntimeError(task_data.get("error") or "ASR failed")
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

    if not (out_dir / "notes_raw.md").exists() or args.force_codex:
        run_codex(out_dir, args.codex_timeout)
    else:
        print(
            json.dumps({"stage": "codex-cache", "slug": video["slug"]}, ensure_ascii=False),
            flush=True,
        )
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="Only process these BV slugs")
    parser.add_argument("--start-at", help="Start at this BV slug")
    parser.add_argument("--poll-interval", type=int, default=30)
    parser.add_argument("--media-timeout", type=int, default=600)
    parser.add_argument("--codex-timeout", type=int, default=900)
    parser.add_argument("--force-asr", action="store_true")
    parser.add_argument("--force-codex", action="store_true")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    root = Path(__file__).resolve().parents[1]
    videos = VIDEOS
    if args.only:
        allowed = set(args.only)
        videos = [video for video in videos if video["slug"] in allowed]
    if args.start_at:
        slugs = [video["slug"] for video in videos]
        videos = videos[slugs.index(args.start_at) :]

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

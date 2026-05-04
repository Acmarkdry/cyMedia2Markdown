# -*- coding: UTF-8 -*-

from fastapi import APIRouter
import json
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

import env
from core.response import success_response, APIResponse
from core.exceptions import BusinessException, ExternalServiceException
from models import ChatRequest, TranscriptSegment, VideoNotesRequest

router = APIRouter(prefix="/llm", tags=["LLM"])

CODEX_TEXT_GENERATION_INSTRUCTION = """你正在作为 AI-Media2Doc 的文本生成后端。
只根据下面传入的消息生成回复。
不要读取或修改本地文件，不要运行命令，不要解释你的执行过程。
如果用户要求 Markdown，则只输出 Markdown 正文。"""


def build_prompt(request: ChatRequest) -> str:
    """将前端传来的 chat messages 转为 Codex CLI 的单次 prompt。"""
    messages = [
        f"<message role=\"{message.role}\">\n{message.content}\n</message>"
        for message in request.messages
    ]
    prompt_parts = [CODEX_TEXT_GENERATION_INSTRUCTION, *messages]
    if request.max_tokens:
        prompt_parts.append(f"请尽量将输出控制在约 {request.max_tokens} tokens 以内。")
    return "\n\n".join(prompt_parts)


def make_chat_response(content: str):
    """保持前端依赖的 OpenAI-like choices 响应结构。"""
    return {
        "id": f"codex-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": env.CODEX_CLI_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": None,
    }


def format_time_ms(ms: int) -> str:
    total = max(0, int(ms // 1000))
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def normalize_segment(segment: TranscriptSegment | dict, index: int) -> dict:
    if isinstance(segment, TranscriptSegment):
        data = segment.model_dump() if hasattr(segment, "model_dump") else segment.dict()
    else:
        data = dict(segment)
    return {
        "id": data.get("id", index),
        "start_time": int(data["start_time"]),
        "end_time": int(data["end_time"]),
        "text": str(data.get("text") or "").strip(),
    }


def prepare_segments(segments: list[TranscriptSegment | dict]) -> list[dict]:
    prepared = []
    for index, segment in enumerate(segments):
        normalized = normalize_segment(segment, index)
        if not normalized["text"]:
            continue
        normalized["end_time"] = max(normalized["end_time"], normalized["start_time"] + 1000)
        prepared.append(normalized)
    prepared.sort(key=lambda item: (item["start_time"], item["end_time"]))
    for index, segment in enumerate(prepared):
        segment["id"] = index
    return prepared


def transcript_text_to_segments(text: str) -> list[dict]:
    segments = []
    for index, line in enumerate(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        match = re.match(
            r"^\[(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–]\s*(\d{1,2}:\d{2}(?::\d{2})?).*?\]\s*(.+)$",
            line,
        )
        if not match:
            segments.append(
                {
                    "id": index,
                    "start_time": index * 5000,
                    "end_time": (index + 1) * 5000,
                    "text": line,
                }
            )
            continue
        start_ms = parse_prompt_time(match.group(1))
        end_ms = parse_prompt_time(match.group(2))
        segments.append(
            {
                "id": index,
                "start_time": start_ms,
                "end_time": max(end_ms, start_ms + 1000),
                "text": match.group(3).strip(),
            }
        )
    return prepare_segments(segments)


def parse_prompt_time(value: str) -> int:
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    else:
        hours, minutes, seconds = parts
    return (hours * 3600 + minutes * 60 + seconds) * 1000


def notes_density_targets(segments: list[dict]) -> dict:
    if not segments:
        return {"duration_seconds": 0, "screenshots_min": 3, "screenshots_target": "3-6", "chapters": "3-6", "min_chars": 3000}
    start_time = min(segment["start_time"] for segment in segments)
    end_time = max(segment["end_time"] for segment in segments)
    duration_seconds = max(1, int((end_time - start_time) / 1000))
    duration_minutes = duration_seconds / 60
    if duration_minutes <= 30:
        return {"duration_seconds": duration_seconds, "screenshots_min": 6, "screenshots_target": "6-10", "chapters": "5-8", "min_chars": 8000}
    if duration_minutes <= 60:
        return {"duration_seconds": duration_seconds, "screenshots_min": 10, "screenshots_target": "10-16", "chapters": "8-12", "min_chars": 14000}
    if duration_minutes <= 120:
        return {"duration_seconds": duration_seconds, "screenshots_min": 16, "screenshots_target": "16-26", "chapters": "12-20", "min_chars": 28000}
    return {"duration_seconds": duration_seconds, "screenshots_min": 24, "screenshots_target": "24-36", "chapters": "18-28", "min_chars": 42000}


def format_transcript_segments(segments: list[dict]) -> str:
    lines = []
    for segment in segments:
        start_s = segment["start_time"] // 1000
        end_s = segment["end_time"] // 1000
        lines.append(
            f"[{format_time_ms(segment['start_time'])}-{format_time_ms(segment['end_time'])} seconds:{start_s}-{end_s}] {segment['text']}"
        )
    return "\n".join(lines)


def split_segments(segments: list[dict], chunk_minutes: int) -> list[list[dict]]:
    if not segments:
        return []
    segments = sorted(segments, key=lambda item: (item["start_time"], item["end_time"]))
    chunk_ms = max(5, chunk_minutes) * 60 * 1000
    chunks = []
    current = []
    chunk_start = segments[0]["start_time"]
    for segment in segments:
        if current and segment["start_time"] - chunk_start >= chunk_ms:
            chunks.append(current)
            current = []
            chunk_start = segment["start_time"]
        current.append(segment)
    if current:
        chunks.append(current)
    return chunks


def build_video_notes_prompt(
    *,
    title: str,
    source_url: str | None,
    segments: list[dict],
    remarks: str | None,
    part_label: str | None = None,
    max_tokens: int | None = None,
) -> str:
    targets = notes_density_targets(segments)
    duration_text = format_time_ms(targets["duration_seconds"] * 1000)
    part_line = f"当前分块：{part_label}\n" if part_label else ""
    remarks_line = f"\n用户补充要求：\n{remarks.strip()}\n" if remarks and remarks.strip() else ""
    token_budget_line = (
        f"输出预算：前端设置的最大输出约 {max_tokens} tokens。请在这个预算内尽量保留高价值技术细节；如果预算与完整度冲突，优先保留具体机制、步骤、类名、配置和坑点，压缩寒暄与重复表达。\n"
        if max_tokens
        else ""
    )
    return f"""你是一位 Unreal Engine / 游戏技术课程的高密度知识整理专家。

视频标题：{title}
来源：{source_url or "本地视频"}
{part_line}视频或分块时长：约 {duration_text}
任务：根据下面带时间戳的转写稿，生成中文 Markdown 深度学习笔记。目标是让读者不看原视频，也能复习主要技术内容、关键细节和实践方法。

硬性要求：
1. 只输出 Markdown 正文，不要解释执行过程。
2. 默认输出中文；英文字幕需要翻译成自然中文。Unreal/Lyra/GAS/Common UI/Animation/Rendering 等专业术语保留英文，并在首次出现时补充中文解释。
3. 内容完整优先于简短。不要只写结论，必须保留重要概念、系统关系、实现步骤、配置项、类名、函数名、蓝图节点、调试方法、示例、注意事项、适用场景和讲者强调的经验。
4. 可以删除寒暄、重复口癖、直播互动闲聊和无技术含量内容，但不要删掉技术推导、操作流程和上下文原因。
5. 标题层级只使用 `#`、`##`、`###`，不允许跳级；只使用一个 `#` 主标题。
6. 每个 `##` 章节标题后必须带时间范围，例如 `## 核心机制 [00:00-04:30]`。每个 `###` 小节也尽量带时间范围。
7. 时间范围必须基于字幕时间信息，格式为 `[mm:ss-mm:ss]` 或 `[hh:mm:ss-hh:mm:ss]`，00 小时时隐藏小时。
8. 章节数量建议 {targets["chapters"]} 个。每个主要章节至少包含 4-8 条高信息量要点；涉及流程、配置、代码、蓝图或系统结构时，必须拆成步骤。
9. 输出不要过度压缩。当前目标正文至少约 {targets["min_chars"]} 个中文字符。
{token_budget_line}10. 对关键概念尽量补充“为什么重要 / 适用场景 / 常见坑 / 和其他系统的关系”。
11. 插入 {targets["screenshots_target"]} 个截图标记。截图标记必须单独一行，且只能是 `#image[整数秒]`。
12. 秒数必须来自转写稿附近，选择适合看 PPT、架构图、编辑器操作、代码、蓝图、效果对比或演示画面的时刻。
13. 不要虚构视频中没有的信息。ASR 可能有误，请结合 Unreal Engine 技术术语合理纠错，但不能编造不存在的 API 或流程。
{remarks_line}
建议输出结构：
# 主标题
## 核心结论 [时间]
## 主题章节 [时间]
### 子主题 [时间]
## 易错点与调试建议
## 术语表
## 实践清单
## 复习问题

转写稿：
{format_transcript_segments(segments)}
"""


def build_merge_prompt(
    title: str,
    source_url: str | None,
    chunk_notes: list[str],
    targets: dict,
    remarks: str | None,
    max_tokens: int | None = None,
) -> str:
    notes = "\n\n".join(
        f"<chunk_note index=\"{index + 1}\">\n{note}\n</chunk_note>"
        for index, note in enumerate(chunk_notes)
    )
    remarks_line = f"\n用户补充要求：\n{remarks.strip()}\n" if remarks and remarks.strip() else ""
    token_budget_line = (
        f"前端设置的最大输出约 {max_tokens} tokens。请在预算内优先保留技术细节，合并重复表达。\n"
        if max_tokens
        else ""
    )
    return f"""你是一位技术资料总编辑。下面是同一个视频按时间分块生成的高密度学习笔记。

视频标题：{title}
来源：{source_url or "本地视频"}

任务：把分块笔记合并为一份完整 Markdown 学习笔记。

硬性要求：
1. 只输出 Markdown 正文。
2. 合并重复内容，但不要删减重要技术细节、步骤、配置、类名、函数名、蓝图节点、注意事项和实践建议。
3. 保留并整理所有有价值的 `#image[整数秒]` 标记，最终至少保留 {targets["screenshots_min"]} 个截图标记。
4. 保持全局时间线顺序，标题时间范围必须仍然对应原视频。
5. 只使用 `#`、`##`、`###` 三层标题。
6. 最终正文至少约 {targets["min_chars"]} 个中文字符；如果分块笔记内容丰富，不要为了简短而压缩。
{token_budget_line}
{remarks_line}
分块笔记：
{notes}
"""


def assess_markdown_quality(markdown: str, targets: dict) -> dict:
    image_markers = re.findall(r"^#image\[\d+\]$", markdown, flags=re.MULTILINE)
    h2_count = len(re.findall(r"^## ", markdown, flags=re.MULTILINE))
    h3_count = len(re.findall(r"^### ", markdown, flags=re.MULTILINE))
    char_count = len(markdown)
    problems = []
    if char_count < targets["min_chars"]:
        problems.append(f"正文偏短: {char_count} < {targets['min_chars']}")
    if len(image_markers) < targets["screenshots_min"]:
        problems.append(f"截图偏少: {len(image_markers)} < {targets['screenshots_min']}")
    if h2_count < 3:
        problems.append(f"章节偏少: {h2_count}")
    if h3_count < max(4, h2_count):
        problems.append(f"小节偏少: h3={h3_count}, h2={h2_count}")
    return {
        "passed": not problems,
        "problems": problems,
        "chars": char_count,
        "image_markers": len(image_markers),
        "h2": h2_count,
        "h3": h3_count,
    }


def build_retry_prompt(original_prompt: str, previous_markdown: str, quality: dict) -> str:
    return f"""{original_prompt}

上一版输出未达到质量要求：
{json.dumps(quality, ensure_ascii=False, indent=2)}

上一版输出：
<previous_markdown>
{previous_markdown}
</previous_markdown>

请重新生成一版更完整的 Markdown：
- 显著增加技术细节、步骤、配置项、类名、函数名、注意事项和实践建议。
- 增加截图标记数量，截图标记仍必须单独一行 `#image[整数秒]`。
- 不要只扩写套话，必须围绕转写稿中的具体内容展开。
"""


def run_codex_cli(prompt: str, timeout: Optional[int] = None) -> str:
    """通过本机 Codex CLI 调用已登录的 Codex/ChatGPT 能力。"""
    timeout_seconds = timeout or 120
    with tempfile.TemporaryDirectory(prefix="ai-media2doc-codex-") as temp_dir:
        output_path = Path(temp_dir) / "codex_last_message.md"
        codex_cmd = (
            env.CODEX_CLI_PATH
            if env.CODEX_CLI_PATH and env.CODEX_CLI_PATH != "codex"
            else (
                shutil.which("codex.cmd")
                or shutil.which("codex.exe")
                or shutil.which("codex")
                or "codex"
            )
        )
        cmd = [
            codex_cmd,
            "exec",
            "-m",
            env.CODEX_CLI_MODEL,
            "-c",
            f'model_reasoning_effort="{env.CODEX_CLI_REASONING_EFFORT}"',
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--output-last-message",
            str(output_path),
            "-",
        ]

        try:
            result = subprocess.run(
                cmd,
                input=prompt.encode("utf-8"),
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except (FileNotFoundError, PermissionError) as exc:
            raise ExternalServiceException(
                "Codex CLI",
                f"Codex CLI not found or not executable: {codex_cmd}. Please install Codex CLI and run `codex login`.",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ExternalServiceException(
                "Codex CLI",
                f"Codex CLI timed out after {timeout_seconds} seconds. Increase timeout in settings.",
            ) from exc

        if result.returncode != 0:
            details = (result.stderr or result.stdout or b"").decode(
                "utf-8", errors="replace"
            ).strip()
            raise ExternalServiceException(
                "Codex CLI",
                f"codex exec failed with exit code {result.returncode}",
                details=details,
            )

        if not output_path.exists():
            details = (result.stderr or result.stdout or b"").decode(
                "utf-8", errors="replace"
            ).strip()
            raise ExternalServiceException(
                "Codex CLI",
                "codex exec completed but did not write --output-last-message",
                details=details,
            )

        return output_path.read_text(encoding="utf-8").strip()


@router.post("/completions", response_model=APIResponse)
async def default_chat(request: ChatRequest):
    """默认聊天接口：使用 Codex CLI，而不是 OpenAI API。"""
    content = run_codex_cli(build_prompt(request), request.timeout)
    return success_response(
        data=make_chat_response(content),
        message="Chat completed successfully",
    )


@router.post("/markdown-generation", response_model=APIResponse)
async def generate_markdown_text(request: ChatRequest):
    """生成 Markdown 文本：使用 Codex CLI，而不是 OpenAI API。"""
    prompt = build_prompt(request)
    content = run_codex_cli(prompt, request.timeout)
    return success_response(
        data=make_chat_response(content),
        message="Chat completed successfully",
    )


@router.post("/video-notes", response_model=APIResponse)
async def generate_video_notes(request: VideoNotesRequest):
    """根据带时间戳的 transcript 生成高密度视频学习笔记。

    后端负责长视频分块、Codex 调用、合并和基础质检；前端只需要处理截图标记。
    """
    title = request.title or "视频学习笔记"
    source_url = request.source_url
    timeout = request.timeout or 3600
    chunk_minutes = request.chunk_minutes or 15

    if request.transcript_segments:
        segments = prepare_segments(request.transcript_segments)
    elif request.transcript_text:
        segments = transcript_text_to_segments(request.transcript_text)
    else:
        raise BusinessException("transcript_segments or transcript_text is required")

    if not segments:
        raise BusinessException("Transcript is empty")

    targets = notes_density_targets(segments)
    use_chunking = bool(request.enable_chunking) and (
        targets["duration_seconds"] >= 45 * 60 or len(format_transcript_segments(segments)) > 90000
    )
    chunk_notes = []
    prompt_used = ""

    if use_chunking:
        chunks = split_segments(segments, chunk_minutes)
        for index, chunk in enumerate(chunks):
            part_label = (
                f"{index + 1}/{len(chunks)} "
                f"[{format_time_ms(chunk[0]['start_time'])}-{format_time_ms(chunk[-1]['end_time'])}]"
            )
            prompt = build_video_notes_prompt(
                title=title,
                source_url=source_url,
                segments=chunk,
                remarks=request.remarks,
                part_label=part_label,
                max_tokens=request.max_tokens,
            )
            chunk_notes.append(run_codex_cli(prompt, timeout))
        prompt_used = build_merge_prompt(
            title,
            source_url,
            chunk_notes,
            targets,
            request.remarks,
            max_tokens=request.max_tokens,
        )
        content = run_codex_cli(prompt_used, timeout)
    else:
        prompt_used = build_video_notes_prompt(
            title=title,
            source_url=source_url,
            segments=segments,
            remarks=request.remarks,
            max_tokens=request.max_tokens,
        )
        content = run_codex_cli(prompt_used, timeout)

    quality = assess_markdown_quality(content, targets)
    retried = False
    if request.quality_retry and not quality["passed"]:
        retry_prompt = build_retry_prompt(prompt_used, content, quality)
        retry_content = run_codex_cli(retry_prompt, timeout)
        retry_quality = assess_markdown_quality(retry_content, targets)
        if retry_quality["passed"] or retry_quality["chars"] > quality["chars"]:
            content = retry_content
            quality = retry_quality
            retried = True

    data = make_chat_response(content)
    data["quality"] = quality
    data["chunked"] = use_chunking
    data["chunk_count"] = len(chunk_notes) if use_chunking else 1
    data["retried"] = retried
    return success_response(
        data=data,
        message="Video notes generated successfully",
    )

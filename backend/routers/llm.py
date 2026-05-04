# -*- coding: UTF-8 -*-

from fastapi import APIRouter
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

import env
from core.response import success_response, APIResponse
from core.exceptions import ExternalServiceException
from models import ChatRequest

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


def run_codex_cli(prompt: str, timeout: Optional[int] = None) -> str:
    """通过本机 Codex CLI 调用已登录的 Codex/ChatGPT 能力。"""
    timeout_seconds = timeout or 120
    with tempfile.TemporaryDirectory(prefix="ai-media2doc-codex-") as temp_dir:
        output_path = Path(temp_dir) / "codex_last_message.md"
        cmd = [
            env.CODEX_CLI_PATH,
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
        except FileNotFoundError as exc:
            raise ExternalServiceException(
                "Codex CLI",
                f"Codex CLI not found: {env.CODEX_CLI_PATH}. Please install Codex CLI and run `codex login`.",
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

# -*- coding: UTF-8 -*-

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from fastapi import APIRouter

import env
from config.log import get_logger
from core.response import success_response, APIResponse
from core.exceptions import BusinessException, ExternalServiceException
from models import (
    ArticleExtractRequest,
    ArticleExtractResponse,
    ArticleWashingRequest,
    ArticleWashingResponse,
    ArticleSource,
    ArticleMetadata,
    LocalCodeProject,
    ReadCodeRequest,
    ReadCodeResponse,
    CodeFile,
)
from routers.llm import run_opencode_cli
from utils.article_extractor import extract_article
from utils.local_code_reader import read_code_projects

router = APIRouter(prefix="/washing", tags=["Washing"])
logger = get_logger(__name__)

ARTICLE_WASHING_INSTRUCTION = """你正在作为 AI-Media2Doc 的「赛博洗稿」知识整理后端。
你是一位高密度知识整理专家，任务是根据多篇原文和用户提示，生成一份综合性知识笔记。
只输出 Markdown 正文，不要解释你的执行过程。"""


# ══════════════════════════════════════════════════════════════════════
#  Prompt builders
# ══════════════════════════════════════════════════════════════════════

STYLE_GUIDE_MAP = {
    "deep": "深度学习风格：保留技术细节、因果关系、设计动机、工程实践。避免表面罗列，注重深度理解。",
    "concise": "精简风格：提取核心要点，去除重复和冗余，保留关键信息。",
    "comprehensive": "全面风格：不遗漏任何细节，保持完整性，适合作为参考资料。",
}


def _build_key_points_prompt(markdown: str) -> str:
    """Build a short prompt to extract 3-5 key technical points from an article."""
    truncated = markdown[:3000]
    return f"分析以下文章的3-5个核心技术要点，用中文列出：\n\n{truncated}"


def _build_stage1_prompt(context_prompt: str, key_points_text: str) -> str:
    """Build the Stage 1 domain understanding prompt."""
    return f"""你是一位技术领域知识整理专家。
用户提供了以下背景说明和文章要点，请对相关领域做一个结构化的知识梳理。

背景说明：{context_prompt}

各篇文章要点：
{key_points_text}

请输出一个结构化的领域知识脉络，包含：
1. 核心概念和术语
2. 关键架构和设计模式
3. 主要技术流程
4. 与其他系统的关系
5. 常见工程实践

只输出Markdown，不要解释过程。"""


def _build_stage2_prompt(
    domain_summary: str,
    all_articles_markdown: str,
    code_context: str,
    refinement_prompt: str,
    style: str,
    max_tokens: Optional[int],
) -> str:
    """Build the Stage 2 deep refinement prompt."""
    style_guide = STYLE_GUIDE_MAP.get(style, STYLE_GUIDE_MAP["deep"])

    token_budget = ""
    if max_tokens:
        token_budget = (
            f"\n输出预算：前端设置的最大输出约 {max_tokens} tokens。"
            f"请在这个预算内尽量保留高价值技术细节；如果预算与完整度冲突，"
            f"优先保留具体机制、步骤、类名、配置和坑点，压缩寒暄与重复表达。"
        )

    code_section = ""
    if code_context.strip():
        code_section = f"""
实际源码参考：
{code_context}
"""

    return f"""你是一位深度技术知识整理专家。现在需要在领域知识脉络的基础上，结合多篇原文和实际源码，生成一篇综合性深度技术笔记。

领域知识脉络：
{domain_summary}

各篇文章原文：
{all_articles_markdown}
{code_section}
用户深化要求：
{refinement_prompt}

输出风格：{style_guide}{token_budget}

硬性要求：
1. 只输出Markdown正文
2. 默认中文，专业术语首次出现补充英文
3. 内容完整优先：保留重要概念、系统关系、实现步骤、配置项、类名、函数名
4. 删除寒暄重复，不删技术推导和上下文原因
5. 标题层级只使用 # ## ###，不跳级
6. 每个###小节先用自然段解释(2-4句)
7. 关键概念补充\"为什么重要/适用场景/常见坑\"
8. 不虚构原文中没有的信息
9. 合并重复内容为统一主题小节
10. 源码引用标注项目+文件路径

建议输出结构：
# 主标题
## 核心结论
## 领域概览
## 核心技术深入
### 子主题1
### 子主题2
## 源码实现分析 (如有源码)
### 关键类/函数
### 设计模式
## 实践清单
## 术语表
## 复习问题"""


def _merge_articles_markdown(articles: List[ArticleExtractResponse]) -> str:
    """Merge multiple articles' markdown into a single formatted string."""
    parts = []
    for idx, article in enumerate(articles, 1):
        title = article.title or "(无标题)"
        parts.append(
            f"### 原文 {idx}: {title}\n来源: {article.url}\n\n{article.markdown_content}"
        )
    return "\n\n---\n\n".join(parts)


def _merge_code_files(code_files: List[dict]) -> str:
    """Merge code files into a single formatted string."""
    if not code_files:
        return ""
    parts = []
    for f in code_files:
        label = f.get("project_label", "")
        path = f.get("relative_path", "")
        language = f.get("language", "")
        content = f.get("content", "")
        parts.append(
            f"### [{label}] {path} ({language})\n```{language}\n{content}\n```"
        )
    return "\n\n".join(parts)


# ══════════════════════════════════════════════════════════════════════
#  Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/extract", response_model=APIResponse)
async def extract_single(request: ArticleExtractRequest):
    """提取单篇文章为 Markdown，使用 trafilatura（带 HTML 回退）。"""
    timeout = request.timeout if request.timeout and request.timeout > 0 else 30
    logger.info("Extracting article from %s (timeout=%ds)", request.url, timeout)

    result = extract_article(request.url, timeout=timeout)

    metadata_raw = result.get("metadata") or {}
    metadata = ArticleMetadata(
        author=metadata_raw.get("author"),
        date=metadata_raw.get("date"),
        description=metadata_raw.get("description"),
        sitename=metadata_raw.get("sitename"),
    ) if any(metadata_raw.values()) else None

    response_data = ArticleExtractResponse(
        url=request.url,
        title=result.get("title"),
        markdown_content=result.get("markdown_content", ""),
        html_content=result.get("html_content"),
        extraction_method=result.get("extraction_method", "unknown"),
        metadata=metadata,
    )

    if not response_data.markdown_content:
        raise BusinessException(
            f"Failed to extract content from {request.url}",
            error_code="EXTRACTION_FAILED",
        )

    return success_response(
        data=response_data.model_dump(),
        message=f"Article extracted successfully via {response_data.extraction_method}",
    )


@router.post("/read-code", response_model=APIResponse)
async def read_code(request: ReadCodeRequest):
    """读取本地代码项目中的源文件。"""
    if not request.projects:
        raise BusinessException("At least one project is required")

    logger.info("Reading code from %d projects", len(request.projects))

    max_files = request.max_files_per_project if request.max_files_per_project and request.max_files_per_project > 0 else 10

    projects_dicts = [p.model_dump() for p in request.projects]
    result = read_code_projects(projects_dicts, max_files_per_project=max_files)

    code_files = [
        CodeFile(
            project_label=f.get("project_label", ""),
            relative_path=f.get("relative_path", ""),
            content=f.get("content", ""),
            language=f.get("language", ""),
        )
        for f in result["files"]
    ]

    response_data = ReadCodeResponse(
        files=code_files,
        errors=result.get("errors"),
    )

    return success_response(
        data=response_data.model_dump(),
        message=f"Code reading completed: {len(code_files)} files from {len(request.projects)} projects",
    )


@router.post("/wash", response_model=APIResponse)
async def wash_articles(request: ArticleWashingRequest):
    """赛博洗稿 v2：两阶段 AI 知识深化流水线。

    Stage 1 – 领域理解：
      提取所有文章要点，结合 context_prompt 生成领域知识脉络。

    Stage 2 – 深度精炼：
      结合领域脉络、原文全文、源码（如有）和 refinement_prompt 生成最终笔记。
    """
    if not request.articles:
        raise BusinessException("At least one article URL is required")

    logger.info(
        "Washing v2: %d articles, %d code projects (context=%.50s, refinement=%.50s, style=%s)",
        len(request.articles),
        len(request.code_projects) if request.code_projects else 0,
        request.context_prompt,
        request.refinement_prompt,
        request.style,
    )

    # ── Step 0: Determine timeouts ──
    extract_timeout = getattr(env, "WASHING_REQUEST_TIMEOUT", 30)
    wash_timeout = request.timeout if request.timeout and request.timeout > 0 else 600

    # ── Step 1: Extract all articles ──
    extracted: List[ArticleExtractResponse] = []
    extract_errors: List[dict] = []

    for article_ref in request.articles:
        result = extract_article(article_ref.url, timeout=extract_timeout)

        metadata_raw = result.get("metadata") or {}
        metadata = (
            ArticleMetadata(
                author=metadata_raw.get("author"),
                date=metadata_raw.get("date"),
                description=metadata_raw.get("description"),
                sitename=metadata_raw.get("sitename"),
            )
            if any(metadata_raw.values())
            else None
        )

        response_data = ArticleExtractResponse(
            url=article_ref.url,
            title=result.get("title") or article_ref.title,
            markdown_content=result.get("markdown_content", ""),
            html_content=result.get("html_content"),
            extraction_method=result.get("extraction_method", "unknown"),
            metadata=metadata,
        )
        if response_data.markdown_content:
            extracted.append(response_data)
        else:
            extract_errors.append(
                {"url": article_ref.url, "error": "Failed to extract content"}
            )

    if not extracted:
        raise BusinessException(
            "All article extractions failed",
            error_code="ALL_EXTRACTIONS_FAILED",
            details={"errors": extract_errors},
        )

    if extract_errors:
        logger.warning(
            "%d articles failed extraction, proceeding with %d succeeded",
            len(extract_errors),
            len(extracted),
        )

    # ── Step 2: Read code projects (if provided) ──
    code_files_data: List[dict] = []
    code_files_objects: List[CodeFile] = []
    if request.code_projects:
        projects_dicts = [p.model_dump() for p in request.code_projects]
        logger.info("Reading %d code projects", len(projects_dicts))
        code_result = read_code_projects(projects_dicts, max_files_per_project=10)
        code_files_data = code_result["files"]
        if code_result.get("errors"):
            for err in code_result["errors"]:
                logger.warning("Code reading error: %s", err)
        code_files_objects = [
            CodeFile(
                project_label=f.get("project_label", ""),
                relative_path=f.get("relative_path", ""),
                content=f.get("content", ""),
                language=f.get("language", ""),
            )
            for f in code_files_data
        ]
        logger.info("Read %d code files from %d projects", len(code_files_data), len(projects_dicts))

    # ── Step 3: Generate key_points for each article ──
    key_points_parts: List[str] = []
    for idx, article in enumerate(extracted, 1):
        if not article.markdown_content.strip():
            key_points_parts.append(f"文章 {idx}: {article.title or article.url}\n(无内容)")
            continue
        try:
            kp_prompt = _build_key_points_prompt(article.markdown_content)
            kp_output = run_opencode_cli(kp_prompt, timeout=60)
            article.key_points = kp_output
            key_points_parts.append(f"文章 {idx}: {article.title or article.url}\n{kp_output}")
            logger.info("Generated key points for article %d (%s)", idx, article.title or article.url)
        except ExternalServiceException:
            logger.warning("Key point extraction failed for article %d, using truncated markdown", idx)
            truncated = article.markdown_content[:500]
            key_points_parts.append(f"文章 {idx}: {article.title or article.url}\n(提取失败，使用原文片段: {truncated})")
        except Exception as exc:
            logger.warning("Unexpected error during key point extraction for article %d: %s", idx, exc)
            truncated = article.markdown_content[:500]
            key_points_parts.append(f"文章 {idx}: {article.title or article.url}\n(提取异常: {truncated})")

    article_key_points = "\n\n".join(key_points_parts)

    # ── Step 4: Stage 1 – Domain Understanding ──
    stage1_prompt = _build_stage1_prompt(
        context_prompt=request.context_prompt,
        key_points_text=article_key_points,
    )
    logger.info("Stage 1: Generating domain summary...")
    try:
        domain_summary = run_opencode_cli(stage1_prompt, timeout=wash_timeout)
    except ExternalServiceException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error during Stage 1")
        raise ExternalServiceException(
            "OpenCode CLI",
            f"Stage 1 domain understanding failed: {exc}",
        ) from exc

    # ── Step 5: Stage 2 – Deep Refinement ──
    all_articles_markdown = _merge_articles_markdown(extracted)
    code_context = _merge_code_files(code_files_data)

    stage2_prompt = _build_stage2_prompt(
        domain_summary=domain_summary,
        all_articles_markdown=all_articles_markdown,
        code_context=code_context,
        refinement_prompt=request.refinement_prompt,
        style=request.style or "deep",
        max_tokens=request.max_tokens,
    )
    logger.info("Stage 2: Generating refined output...")
    try:
        refined_output = run_opencode_cli(stage2_prompt, timeout=wash_timeout)
    except ExternalServiceException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error during Stage 2")
        raise ExternalServiceException(
            "OpenCode CLI",
            f"Stage 2 deep refinement failed: {exc}",
        ) from exc

    # ── Step 6: Build response ──
    response_data = ArticleWashingResponse(
        extracted_articles=extracted,
        code_files=code_files_objects if code_files_objects else None,
        domain_summary=domain_summary,
        refined_output=refined_output,
        stage1_prompt=stage1_prompt,
        stage2_prompt=stage2_prompt,
    )

    return success_response(
        data=response_data.model_dump(),
        message=f"Article washing completed: {len(extracted)} articles refined in 2 stages",
    )

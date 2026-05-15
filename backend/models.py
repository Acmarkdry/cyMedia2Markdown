# -*- coding: UTF-8 -*-

from pydantic import BaseModel
from typing import List, Optional, Any, Dict


class MessageModel(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[MessageModel]
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int]
    timeout: Optional[int]


class FileNameRequest(BaseModel):
    filename: str


class TranscriptSegment(BaseModel):
    start_time: int
    end_time: int
    text: str
    id: Optional[int] = None


class MediaUrlRequest(BaseModel):
    url: str


class VideoScreenshotRequest(BaseModel):
    filename: str
    time_seconds: int


class VideoNotesRequest(BaseModel):
    title: Optional[str] = None
    source_url: Optional[str] = None
    transcript_segments: Optional[List[TranscriptSegment]] = None
    transcript_text: Optional[str] = None
    remarks: Optional[str] = None
    style: Optional[str] = "deep"
    chunk_minutes: Optional[int] = 15
    enable_chunking: Optional[bool] = True
    quality_retry: Optional[bool] = True
    timeout: Optional[int] = None
    max_tokens: Optional[int] = None


class EnvResponse(BaseModel):
    code: int = 200
    success: bool = True
    message: str = "operation successful"
    data: Optional[Any] = None


# ──────────────────────────────────────────────────────────────────────
#  赛博洗稿 (Cyber Content Refinement)  Models – v2
# ──────────────────────────────────────────────────────────────────────


class LocalCodeProject(BaseModel):
    """A local code project to read source files from."""

    path: str
    label: str
    file_patterns: Optional[List[str]] = None


class ArticleSource(BaseModel):
    """Reference to an article by URL."""

    url: str
    title: Optional[str] = None


class ArticleExtractRequest(BaseModel):
    """Request to extract a single article."""

    url: str
    timeout: Optional[int] = 30


class ArticleMetadata(BaseModel):
    """Metadata extracted from an article."""

    author: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    sitename: Optional[str] = None


class ArticleExtractResponse(BaseModel):
    """Response from article extraction."""

    url: str
    title: Optional[str] = None
    markdown_content: str
    html_content: Optional[str] = None
    extraction_method: str
    metadata: Optional[ArticleMetadata] = None
    key_points: Optional[str] = None  # populated during washing stage


class ReadCodeRequest(BaseModel):
    """Request to read local source code from one or more projects."""

    projects: List[LocalCodeProject]
    max_files_per_project: Optional[int] = 10


class CodeFile(BaseModel):
    """A single source code file."""

    project_label: str
    relative_path: str
    content: str
    language: str


class ReadCodeResponse(BaseModel):
    """Response from reading local code projects."""

    files: List[CodeFile]
    errors: Optional[List[dict]] = None


class ArticleWashingRequest(BaseModel):
    """Request to wash/refine multiple articles with two-stage LLM pipeline."""

    articles: List[ArticleSource]
    code_projects: Optional[List[LocalCodeProject]] = None
    context_prompt: str  # Stage 1: describe domain
    refinement_prompt: str  # Stage 2: deepen instructions
    style: Optional[str] = "deep"
    timeout: Optional[int] = None
    max_tokens: Optional[int] = None


class ArticleWashingResponse(BaseModel):
    """Response from the two-stage article washing pipeline."""

    extracted_articles: List[ArticleExtractResponse]
    code_files: Optional[List[CodeFile]] = None
    domain_summary: str  # Stage 1 LLM output
    refined_output: str  # Stage 2 LLM final output
    stage1_prompt: Optional[str] = None
    stage2_prompt: Optional[str] = None

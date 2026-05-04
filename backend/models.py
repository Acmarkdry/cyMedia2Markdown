# -*- coding: UTF-8 -*-

from pydantic import BaseModel
from typing import List, Optional, Any


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

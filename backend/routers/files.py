# -*- coding: UTF-8 -*-
from fastapi import APIRouter, Request
from pathlib import Path
from urllib.parse import quote

from config.log import get_logger
from core.exceptions import BusinessException
from core.response import success_response, APIResponse
from models import FileNameRequest
import env

router = APIRouter(prefix="/files", tags=["storage"])
logger = get_logger(__name__)


def get_upload_dir() -> Path:
    upload_dir = Path(env.LOCAL_UPLOAD_DIR)
    if not upload_dir.is_absolute():
        upload_dir = Path(__file__).resolve().parents[1] / upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def safe_filename(filename: str) -> str:
    name = Path(filename).name
    if not name or name in {".", ".."}:
        raise BusinessException("Invalid upload filename")
    return name


@router.post("/upload-urls", response_model=APIResponse)
async def create_upload_url(request: FileNameRequest, http_request: Request):
    """创建本地文件上传 URL。

    RESTful路径: POST /api/v1/files/upload-urls
    """
    filename = safe_filename(request.filename)
    base_url = str(http_request.base_url).rstrip("/")
    upload_url = f"{base_url}/api/v1/files/uploads/{quote(filename)}"

    logger.info(f"Created local upload URL for file: {filename}")
    return success_response(
        data={"upload_url": upload_url}, message="Upload URL created successfully"
    )


@router.put("/uploads/{filename}", response_model=APIResponse)
async def upload_local_file(filename: str, request: Request):
    """上传文件到本机后端目录。"""
    filename = safe_filename(filename)
    body = await request.body()
    if not body:
        raise BusinessException("Uploaded file is empty")

    target_path = get_upload_dir() / filename
    target_path.write_bytes(body)

    logger.info(f"Uploaded local file: {target_path}")
    return success_response(
        data={"filename": filename}, message="File uploaded successfully"
    )

# -*- coding: UTF-8 -*-
from fastapi import APIRouter, Request
import base64
import hashlib
import subprocess
import uuid
from pathlib import Path
from urllib.parse import quote

from config.log import get_logger
from core.exceptions import BusinessException
from core.response import success_response, APIResponse
from models import FileNameRequest, MediaUrlRequest, VideoScreenshotRequest
import env

router = APIRouter(prefix="/files", tags=["storage"])
logger = get_logger(__name__)


def get_upload_dir() -> Path:
    return resolve_storage_dir(env.LOCAL_UPLOAD_DIR)


def get_media_dir() -> Path:
    return resolve_storage_dir(env.LOCAL_MEDIA_DIR)


def get_screenshot_dir() -> Path:
    return resolve_storage_dir(env.LOCAL_SCREENSHOT_DIR)


def resolve_storage_dir(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(filename: str) -> str:
    name = Path(filename).name
    if not name or name in {".", ".."}:
        raise BusinessException("Invalid upload filename")
    return name


def validate_media_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise BusinessException("请输入 http 或 https 开头的视频链接")
    return url


def get_ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise BusinessException(
            "imageio-ffmpeg is not installed. Run `pip install -r requirements.txt` in backend."
        ) from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def extract_audio_from_video(video_path: Path, audio_path: Path):
    cmd = [
        get_ffmpeg_exe(),
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        details = (result.stderr or result.stdout or b"").decode(
            "utf-8", errors="replace"
        )
        raise BusinessException(
            "Failed to extract audio from downloaded video", details=details
        )


def download_video_from_url(url: str):
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise BusinessException(
            "yt-dlp is not installed. Run `pip install -r requirements.txt` in backend."
        ) from exc

    url = validate_media_url(url)
    media_id = uuid.uuid4().hex
    media_dir = get_media_dir()
    outtmpl = str(media_dir / f"{media_id}.%(ext)s")
    ffmpeg_exe = get_ffmpeg_exe()

    ydl_opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ffmpeg_location": ffmpeg_exe,
    }
    if env.YTDLP_COOKIES_FILE:
        ydl_opts["cookiefile"] = env.YTDLP_COOKIES_FILE

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:
        raise BusinessException(f"视频链接下载失败: {exc}") from exc

    video_path = media_dir / f"{media_id}.mp4"
    if not video_path.exists():
        candidates = sorted(media_dir.glob(f"{media_id}.*"))
        video_candidates = [
            path for path in candidates if path.suffix.lower() in {".mp4", ".mkv", ".webm"}
        ]
        if not video_candidates:
            raise BusinessException("视频下载完成但未找到本地视频文件")
        video_path = video_candidates[0]

    audio_filename = f"{media_id}.wav"
    audio_path = get_upload_dir() / audio_filename
    extract_audio_from_video(video_path, audio_path)

    title = info.get("title") or "URL 视频"
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
    return {
        "media_id": media_id,
        "url_hash": url_hash,
        "title": title,
        "source_url": url,
        "audio_filename": audio_filename,
        "video_filename": video_path.name,
        "duration": info.get("duration"),
    }


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


@router.post("/media-from-url", response_model=APIResponse)
async def create_media_from_url(request: MediaUrlRequest):
    """下载 URL 视频到本机，并抽取音频供本地 ASR 使用。"""
    logger.info("Downloading media from URL")
    media = download_video_from_url(request.url)
    return success_response(data=media, message="Media downloaded successfully")


@router.post("/video-screenshots", response_model=APIResponse)
async def create_video_screenshot(request: VideoScreenshotRequest):
    """从本地视频文件按秒截帧，返回 base64 data URL。"""
    filename = safe_filename(request.filename)
    time_seconds = int(request.time_seconds)
    if time_seconds < 0:
        raise BusinessException("Screenshot time must be non-negative")

    video_path = get_media_dir() / filename
    if not video_path.exists():
        raise BusinessException(f"Video file not found: {filename}")

    screenshot_path = get_screenshot_dir() / f"{video_path.stem}_{time_seconds:06d}.jpg"
    if not screenshot_path.exists():
        cmd = [
            get_ffmpeg_exe(),
            "-y",
            "-ss",
            str(time_seconds),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            "scale=min(1280\\,iw):-2",
            "-q:v",
            "2",
            str(screenshot_path),
        ]
        result = subprocess.run(cmd, capture_output=True, check=False)
        if result.returncode != 0 or not screenshot_path.exists():
            details = (result.stderr or result.stdout or b"").decode(
                "utf-8", errors="replace"
            )
            raise BusinessException(f"截图失败: {details}")

    image_data = base64.b64encode(screenshot_path.read_bytes()).decode("ascii")
    return success_response(
        data={
            "time_seconds": time_seconds,
            "filename": screenshot_path.name,
            "data_url": f"data:image/jpeg;base64,{image_data}",
        },
        message="Screenshot created successfully",
    )

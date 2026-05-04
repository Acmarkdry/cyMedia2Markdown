# -*- coding: UTF-8 -*-
from fastapi import APIRouter, Request
import base64
import hashlib
import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import quote

from config.log import get_logger
from core.exceptions import BusinessException
from core.response import success_response, APIResponse
from models import FileNameRequest, MediaUrlRequest, VideoScreenshotRequest
import env

router = APIRouter(prefix="/files", tags=["storage"])
logger = get_logger(__name__)

VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".avi"}
URL_CACHE_FILENAME = "_url_cache.json"
_URL_CACHE_LOCK = threading.Lock()


def get_upload_dir() -> Path:
    return resolve_storage_dir(env.LOCAL_UPLOAD_DIR)


def get_media_dir() -> Path:
    return resolve_storage_dir(env.LOCAL_MEDIA_DIR)


def get_screenshot_dir() -> Path:
    return resolve_storage_dir(env.LOCAL_SCREENSHOT_DIR)


def get_url_cache_path() -> Path:
    return get_media_dir() / URL_CACHE_FILENAME


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


def make_url_hash(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def read_url_cache() -> dict:
    cache_path = get_url_cache_path()
    if not cache_path.exists():
        return {"entries": {}, "aliases": {}}

    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read URL media cache; ignoring stale cache file")
        return {"entries": {}, "aliases": {}}

    if not isinstance(data, dict):
        return {"entries": {}, "aliases": {}}
    data.setdefault("entries", {})
    data.setdefault("aliases", {})
    return data


def write_url_cache(cache: dict):
    cache_path = get_url_cache_path()
    temp_path = cache_path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(cache_path)


def cache_aliases_for_info(url_hash: str, info: dict | None = None) -> list[str]:
    aliases = [f"url:{url_hash}"]
    if not info:
        return aliases

    extractor = info.get("extractor_key") or info.get("extractor")
    media_id = info.get("id")
    if extractor and media_id:
        aliases.append(f"source:{extractor}:{media_id}")

    webpage_url = info.get("webpage_url") or info.get("original_url")
    if webpage_url:
        aliases.append(f"url:{make_url_hash(webpage_url)}")

    return list(dict.fromkeys(aliases))


def get_cached_entry(cache: dict, aliases: list[str]) -> dict | None:
    entries = cache.get("entries", {})
    alias_map = cache.get("aliases", {})
    for alias in aliases:
        entry_id = alias_map.get(alias)
        if entry_id and entry_id in entries:
            return entries[entry_id]
        if alias.startswith("url:"):
            url_hash = alias.removeprefix("url:")
            if url_hash in entries:
                return entries[url_hash]
    return None


def save_cached_entry(entry: dict, aliases: list[str]):
    with _URL_CACHE_LOCK:
        cache = read_url_cache()
        entry_id = entry["url_hash"]
        cache["entries"][entry_id] = entry
        for alias in aliases:
            cache["aliases"][alias] = entry_id
        write_url_cache(cache)


def ensure_cached_entry_ready(entry: dict) -> bool:
    video_filename = entry.get("video_filename")
    audio_filename = entry.get("audio_filename")
    if not video_filename or not audio_filename:
        return False

    video_path = get_media_dir() / safe_filename(video_filename)
    if not video_path.exists():
        return False

    audio_path = get_upload_dir() / safe_filename(audio_filename)
    if not audio_path.exists():
        extract_audio_from_video(video_path, audio_path)
    return True


def response_from_entry(entry: dict, cache_hit: bool, cache_source: str) -> dict:
    return {
        "media_id": entry["media_id"],
        "url_hash": entry["url_hash"],
        "title": entry.get("title") or "URL 视频",
        "source_url": entry.get("source_url"),
        "audio_filename": entry["audio_filename"],
        "video_filename": entry["video_filename"],
        "duration": entry.get("duration"),
        "cache_hit": cache_hit,
        "cache_source": cache_source,
    }


def get_ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise BusinessException(
            "imageio-ffmpeg is not installed. Run `pip install -r requirements.txt` in backend."
        ) from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def normalize_match_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\W+", "", text, flags=re.UNICODE).lower()


def parse_duration_text(text: str) -> float | None:
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def probe_video_duration(video_path: Path) -> float | None:
    cmd = [get_ffmpeg_exe(), "-hide_banner", "-i", str(video_path)]
    result = subprocess.run(cmd, capture_output=True, check=False)
    output = (result.stderr or b"").decode("utf-8", errors="replace")
    output += (result.stdout or b"").decode("utf-8", errors="replace")
    return parse_duration_text(output)


def resolve_archive_dir(path_value: str) -> Path | None:
    path_value = path_value.strip()
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    if path.exists() and path.is_dir():
        return path
    logger.warning("Configured local video archive directory does not exist: %s", path)
    return None


def get_archive_dirs() -> list[Path]:
    dirs = [get_media_dir()]
    for raw_dir in re.split(r"[;,]", env.LOCAL_VIDEO_ARCHIVE_DIRS or ""):
        path = resolve_archive_dir(raw_dir)
        if path:
            dirs.append(path)

    unique_dirs = []
    seen = set()
    for path in dirs:
        resolved = str(path.resolve()).lower()
        if resolved not in seen:
            seen.add(resolved)
            unique_dirs.append(path)
    return unique_dirs


def iter_archive_videos():
    for archive_dir in get_archive_dirs():
        try:
            children = list(archive_dir.iterdir())
        except OSError:
            logger.exception("Failed to list local video archive directory: %s", archive_dir)
            continue
        for path in children:
            if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES:
                yield path


def title_or_id_matches(path: Path, info: dict) -> bool:
    stem = path.stem.lower()
    source_id = str(info.get("id") or "").lower()
    if source_id and source_id in stem:
        return True

    title_key = normalize_match_text(info.get("title"))
    stem_key = normalize_match_text(path.stem)
    if len(title_key) >= 8 and title_key in stem_key:
        return True
    return len(stem_key) >= 8 and stem_key in title_key


def find_local_archive_video(info: dict, url_hash: str) -> tuple[Path, str] | None:
    deterministic_matches = [
        path for path in iter_archive_videos() if path.stem.lower() == url_hash.lower()
    ]
    if deterministic_matches:
        return deterministic_matches[0], "archive-url-hash"

    metadata_matches = [path for path in iter_archive_videos() if title_or_id_matches(path, info)]
    if metadata_matches:
        return metadata_matches[0], "archive-metadata"

    duration = info.get("duration")
    if not duration:
        return None

    duration_matches = []
    for path in iter_archive_videos():
        probed_duration = probe_video_duration(path)
        if probed_duration is not None and abs(probed_duration - float(duration)) <= 2:
            duration_matches.append(path)

    if len(duration_matches) == 1:
        return duration_matches[0], "archive-duration"
    if len(duration_matches) > 1:
        logger.info(
            "Found multiple local archive videos with matching duration; skip ambiguous reuse duration=%s count=%s",
            duration,
            len(duration_matches),
        )
    return None


def materialize_archive_video(source_path: Path, url_hash: str) -> Path:
    media_dir = get_media_dir()
    if source_path.parent.resolve() == media_dir.resolve():
        return source_path

    target_path = media_dir / f"{url_hash}{source_path.suffix.lower()}"
    if not target_path.exists():
        shutil.copy2(source_path, target_path)
    return target_path


def build_cache_entry(
    *,
    url_hash: str,
    media_id: str,
    url: str,
    title: str,
    video_path: Path,
    audio_filename: str,
    duration,
) -> dict:
    return {
        "media_id": media_id,
        "url_hash": url_hash,
        "title": title,
        "source_url": url,
        "audio_filename": audio_filename,
        "video_filename": video_path.name,
        "duration": duration,
        "created_at": time.time(),
        "updated_at": time.time(),
    }


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
    url_hash = make_url_hash(url)
    url_aliases = cache_aliases_for_info(url_hash)
    with _URL_CACHE_LOCK:
        cached_entry = get_cached_entry(read_url_cache(), url_aliases)
    if cached_entry and ensure_cached_entry_ready(cached_entry):
        logger.info("Reusing URL media cache url_hash=%s", url_hash)
        return response_from_entry(cached_entry, cache_hit=True, cache_source="url-cache")

    media_id = url_hash
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
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise BusinessException(f"视频链接解析失败: {exc}") from exc

    title = info.get("title") or "URL 视频"
    aliases = cache_aliases_for_info(url_hash, info)

    with _URL_CACHE_LOCK:
        cached_entry = get_cached_entry(read_url_cache(), aliases)
    if cached_entry and ensure_cached_entry_ready(cached_entry):
        logger.info(
            "Reusing URL media cache by source metadata url_hash=%s title=%s",
            url_hash,
            title,
        )
        return response_from_entry(cached_entry, cache_hit=True, cache_source="source-cache")

    local_archive = find_local_archive_video(info, url_hash)
    if local_archive:
        archive_path, archive_source = local_archive
        video_path = materialize_archive_video(archive_path, url_hash)
        audio_filename = f"{media_id}.wav"
        audio_path = get_upload_dir() / audio_filename
        if not audio_path.exists():
            extract_audio_from_video(video_path, audio_path)

        entry = build_cache_entry(
            url_hash=url_hash,
            media_id=media_id,
            url=url,
            title=title,
            video_path=video_path,
            audio_filename=audio_filename,
            duration=info.get("duration"),
        )
        save_cached_entry(entry, aliases)
        logger.info(
            "Reusing local archive video title=%s video=%s audio=%s source=%s",
            title,
            video_path.name,
            audio_filename,
            archive_source,
        )
        return response_from_entry(entry, cache_hit=True, cache_source=archive_source)

    deterministic_candidates = sorted(media_dir.glob(f"{media_id}.*"))
    deterministic_videos = [
        path for path in deterministic_candidates if path.suffix.lower() in VIDEO_SUFFIXES
    ]
    if deterministic_videos:
        video_path = deterministic_videos[0]
        audio_filename = f"{media_id}.wav"
        audio_path = get_upload_dir() / audio_filename
        if not audio_path.exists():
            extract_audio_from_video(video_path, audio_path)
        entry = build_cache_entry(
            url_hash=url_hash,
            media_id=media_id,
            url=url,
            title=title,
            video_path=video_path,
            audio_filename=audio_filename,
            duration=info.get("duration"),
        )
        save_cached_entry(entry, aliases)
        logger.info("Recovered deterministic URL media file video=%s", video_path.name)
        return response_from_entry(entry, cache_hit=True, cache_source="deterministic-file")

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:
        raise BusinessException(f"视频链接下载失败: {exc}") from exc

    video_path = media_dir / f"{media_id}.mp4"
    if not video_path.exists():
        candidates = sorted(media_dir.glob(f"{media_id}.*"))
        video_candidates = [
            path for path in candidates if path.suffix.lower() in VIDEO_SUFFIXES
        ]
        if not video_candidates:
            raise BusinessException("视频下载完成但未找到本地视频文件")
        video_path = video_candidates[0]

    audio_filename = f"{media_id}.wav"
    audio_path = get_upload_dir() / audio_filename
    extract_audio_from_video(video_path, audio_path)

    title = info.get("title") or title
    entry = build_cache_entry(
        url_hash=url_hash,
        media_id=media_id,
        url=url,
        title=title,
        video_path=video_path,
        audio_filename=audio_filename,
        duration=info.get("duration"),
    )
    save_cached_entry(entry, cache_aliases_for_info(url_hash, info))
    logger.info(
        "Downloaded URL media title=%s video=%s audio=%s duration=%s",
        title,
        video_path.name,
        audio_filename,
        info.get("duration"),
    )
    return response_from_entry(entry, cache_hit=False, cache_source="download")


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
    logger.info(
        "Created video screenshot video=%s time=%ss image=%s",
        filename,
        time_seconds,
        screenshot_path.name,
    )
    return success_response(
        data={
            "time_seconds": time_seconds,
            "filename": screenshot_path.name,
            "data_url": f"data:image/jpeg;base64,{image_data}",
        },
        message="Screenshot created successfully",
    )

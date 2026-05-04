# -*- coding: UTF-8 -*-
from fastapi import APIRouter, BackgroundTasks
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import threading
import uuid

from constants import AsrTaskStatus
from models import FileNameRequest
from core.exceptions import BusinessException
from core.response import success_response, APIResponse
from config.log import get_logger
import env

router = APIRouter(prefix="/audio", tags=["Audio"])
logger = get_logger(__name__)

_TASKS: Dict[str, Dict[str, Any]] = {}
_TASK_LOCK = threading.Lock()
_MODEL_LOCK = threading.Lock()
_WHISPER_MODEL = None
_WHISPER_MODEL_KEY: Optional[Tuple[str, str, str]] = None


def get_upload_dir() -> Path:
    upload_dir = Path(env.LOCAL_UPLOAD_DIR)
    if not upload_dir.is_absolute():
        upload_dir = Path(__file__).resolve().parents[1] / upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def safe_filename(filename: str) -> str:
    name = Path(filename).name
    if not name or name in {".", ".."}:
        raise BusinessException("Invalid audio filename")
    return name


def get_audio_path(filename: str) -> Path:
    path = get_upload_dir() / safe_filename(filename)
    if not path.exists():
        raise BusinessException(f"Uploaded audio file not found: {filename}")
    return path


def update_task(task_id: str, **fields):
    with _TASK_LOCK:
        if task_id in _TASKS:
            _TASKS[task_id].update(fields)


def get_faster_whisper_model():
    global _WHISPER_MODEL, _WHISPER_MODEL_KEY

    model_name = env.FASTER_WHISPER_MODEL
    device = env.FASTER_WHISPER_DEVICE
    compute_type = env.FASTER_WHISPER_COMPUTE_TYPE
    model_key = (model_name, device, compute_type)

    with _MODEL_LOCK:
        if _WHISPER_MODEL is not None and _WHISPER_MODEL_KEY == model_key:
            return _WHISPER_MODEL

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise BusinessException(
                "faster-whisper is not installed. Run `pip install -r requirements.txt` in backend."
            ) from exc

        kwargs = {}
        if device and device != "auto":
            kwargs["device"] = device
        if compute_type and compute_type != "auto":
            kwargs["compute_type"] = compute_type

        logger.info(
            "Loading faster-whisper model",
            extra={
                "model": model_name,
                "device": device,
                "compute_type": compute_type,
            },
        )
        _WHISPER_MODEL = WhisperModel(model_name, **kwargs)
        _WHISPER_MODEL_KEY = model_key
        return _WHISPER_MODEL


def transcribe_with_faster_whisper(audio_path: Path):
    if env.ASR_PROVIDER != "faster-whisper":
        raise BusinessException(f"Unsupported ASR_PROVIDER: {env.ASR_PROVIDER}")

    model = get_faster_whisper_model()
    language = None if env.ASR_LANGUAGE == "auto" else env.ASR_LANGUAGE
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=True,
    )

    result = []
    for index, segment in enumerate(segments):
        text = segment.text.strip()
        if not text:
            continue
        result.append(
            {
                "start_time": int(round(segment.start * 1000)),
                "end_time": int(round(segment.end * 1000)),
                "text": text,
                "id": index,
            }
        )

    logger.info(
        "Local transcription completed",
        extra={
            "audio_path": str(audio_path),
            "language": getattr(info, "language", None),
            "duration": getattr(info, "duration", None),
            "segments": len(result),
        },
    )
    return result


def run_transcription_task(task_id: str, audio_path: Path):
    update_task(task_id, status=AsrTaskStatus.RUNNING.value)
    try:
        result = transcribe_with_faster_whisper(audio_path)
        update_task(
            task_id,
            status=AsrTaskStatus.FINISHED.value,
            result=result,
            error=None,
        )
    except Exception as exc:
        logger.exception("Local transcription task failed")
        update_task(
            task_id,
            status=AsrTaskStatus.FAILED.value,
            result=None,
            error=str(exc),
        )


@router.post("/transcription-tasks", response_model=APIResponse)
async def create_transcription_task(
    request: FileNameRequest, background_tasks: BackgroundTasks
):
    """创建本地音频转写任务。

    RESTful路径: POST /api/v1/audio/transcription-tasks
    """
    logger.info(f"Creating local transcription task for file: {request.filename}")
    audio_path = get_audio_path(request.filename)
    task_id = uuid.uuid4().hex

    with _TASK_LOCK:
        _TASKS[task_id] = {
            "status": AsrTaskStatus.RUNNING.value,
            "result": None,
            "error": None,
            "filename": safe_filename(request.filename),
        }

    background_tasks.add_task(run_transcription_task, task_id, audio_path)

    return success_response(
        data={"task_id": task_id}, message="Transcription task created successfully"
    )


@router.get("/transcription-tasks/{task_id}", response_model=APIResponse)
async def get_transcription_task(task_id: str):
    """获取本地音频转写任务状态。

    RESTful路径: GET /api/v1/audio/transcription-tasks/{task_id}
    """
    with _TASK_LOCK:
        task = _TASKS.get(task_id)

    if not task:
        raise BusinessException(f"Transcription task not found: {task_id}")

    return success_response(
        data={
            "status": task["status"],
            "result": task["result"],
            "error": task.get("error"),
        },
        message="Transcription task status retrieved",
    )

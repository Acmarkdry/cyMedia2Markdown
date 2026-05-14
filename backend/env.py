# -*- coding: UTF-8 -*-

import os

WEB_ACCESS_PASSWORD = os.getenv("WEB_ACCESS_PASSWORD", None)
OPENCODE_CLI_PATH = os.getenv("OPENCODE_CLI_PATH", "opencode")
OPENCODE_CLI_MODEL = os.getenv("OPENCODE_CLI_MODEL", "gpt-5.5")
OPENCODE_CLI_REASONING_EFFORT = os.getenv("OPENCODE_CLI_REASONING_EFFORT", "xhigh")
LOCAL_UPLOAD_DIR = os.getenv("LOCAL_UPLOAD_DIR", "local_storage/uploads")
LOCAL_MEDIA_DIR = os.getenv("LOCAL_MEDIA_DIR", "local_storage/media")
LOCAL_SCREENSHOT_DIR = os.getenv("LOCAL_SCREENSHOT_DIR", "local_storage/screenshots")
LOG_DIR = os.getenv("LOG_DIR", "local_storage/logs")
M2M_QUEUE_ROOT = os.getenv("M2M_QUEUE_ROOT", "")
LOCAL_VIDEO_ARCHIVE_DIRS = os.getenv("LOCAL_VIDEO_ARCHIVE_DIRS", "")
YTDLP_COOKIES_FILE = os.getenv("YTDLP_COOKIES_FILE", None)
ASR_PROVIDER = os.getenv("ASR_PROVIDER", "faster-whisper")
ASR_LANGUAGE = os.getenv("ASR_LANGUAGE", "auto")
FASTER_WHISPER_MODEL = os.getenv("FASTER_WHISPER_MODEL", "large-v3")
FASTER_WHISPER_DEVICE = os.getenv("FASTER_WHISPER_DEVICE", "cuda")
FASTER_WHISPER_COMPUTE_TYPE = os.getenv("FASTER_WHISPER_COMPUTE_TYPE", "float16")

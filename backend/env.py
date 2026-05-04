# -*- coding: UTF-8 -*-

import os

WEB_ACCESS_PASSWORD = os.getenv("WEB_ACCESS_PASSWORD", None)
CODEX_CLI_PATH = os.getenv("CODEX_CLI_PATH", "codex")
CODEX_CLI_MODEL = os.getenv("CODEX_CLI_MODEL", "gpt-5.5")
CODEX_CLI_REASONING_EFFORT = os.getenv("CODEX_CLI_REASONING_EFFORT", "xhigh")
LOCAL_UPLOAD_DIR = os.getenv("LOCAL_UPLOAD_DIR", "local_storage/uploads")
ASR_PROVIDER = os.getenv("ASR_PROVIDER", "faster-whisper")
ASR_LANGUAGE = os.getenv("ASR_LANGUAGE", "auto")
FASTER_WHISPER_MODEL = os.getenv("FASTER_WHISPER_MODEL", "small")
FASTER_WHISPER_DEVICE = os.getenv("FASTER_WHISPER_DEVICE", "auto")
FASTER_WHISPER_COMPUTE_TYPE = os.getenv("FASTER_WHISPER_COMPUTE_TYPE", "auto")

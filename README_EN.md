# cyMedia2Markdown

cyMedia2Markdown is a local-first audio/video to Markdown workspace. It is a fork and adaptation of
[hanshuaikang/AI-Media2Doc](https://github.com/hanshuaikang/AI-Media2Doc), keeping the web frontend/backend workflow while moving the main processing path to the local machine: local transcription, local Codex CLI generation, local media caching and local screenshots.

[中文文档](./README.md)

## Overview

The project is designed for turning lectures, technical talks, meeting recordings and local media into structured notes. The typical flow is:

1. Upload an audio/video file, or submit a publicly accessible video URL.
2. The backend extracts audio and transcribes it locally with `faster-whisper`.
3. The backend calls local `codex exec` to generate Markdown, summaries, Q&A content or screenshot markers.
4. For URL videos, screenshots are captured locally from generated timestamps and inserted into Markdown.
5. The frontend lets you review, ask follow-up questions and export Markdown, subtitles or mind maps.

## Features

- Local-first ASR with `faster-whisper`.
- LLM generation through local Codex CLI credentials.
- Public URL video handling through `yt-dlp`.
- Local media, audio and screenshot cache.
- Timestamp-based screenshot insertion with `#image[seconds]` markers.
- Vue 3 frontend for upload, transcription, generation, chat, preview and export.
- Docker files and local development scripts are retained.

## Repository Layout

```text
backend/                 FastAPI backend for local ASR, media processing and Codex CLI calls
frontend/                Vue 3 + Vite frontend
docs/                    README images, sponsor materials and upstream display assets
tools/                   Batch processing helper scripts
variables_template.env   Environment variable template
docker-compose.yaml      Container startup example
NOTICE.md                Copyright, acknowledgements and content compliance notes
LICENSE                  MIT License
```

## Quick Start

### Backend

Requirements:

- Python 3.10+
- Codex CLI installed and logged in
- ffmpeg runtime provided by `imageio-ffmpeg`
- Compatible GPU/driver environment when using CUDA transcription

```bash
cd backend
pip install -r requirements.txt
python app.py
```

The backend listens on `http://localhost:8080` by default.

See [backend/README.md](./backend/README.md) for more configuration details.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend is served by Vite and talks to the local backend by default.

See [frontend/README.md](./frontend/README.md) for more details.

## Common Environment Variables

See [variables_template.env](./variables_template.env). Common settings include:

```bash
CODEX_CLI_PATH=codex
CODEX_CLI_MODEL=gpt-5.5
CODEX_CLI_REASONING_EFFORT=xhigh
ASR_PROVIDER=faster-whisper
ASR_LANGUAGE=auto
FASTER_WHISPER_MODEL=large-v3
FASTER_WHISPER_DEVICE=cuda
FASTER_WHISPER_COMPUTE_TYPE=float16
LOCAL_UPLOAD_DIR=local_storage/uploads
LOCAL_MEDIA_DIR=local_storage/media
LOCAL_SCREENSHOT_DIR=local_storage/screenshots
YTDLP_COOKIES_FILE=
WEB_ACCESS_PASSWORD=
```

For CPU-only machines, use a smaller model such as `small` or `base` and set:

```bash
FASTER_WHISPER_DEVICE=cpu
FASTER_WHISPER_COMPUTE_TYPE=int8
```

## Batch Helper

[tools/batch_video_notes.py](./tools/batch_video_notes.py) calls the backend URL media endpoint, transcription task API, note generation and HTML rendering flow for a fixed list of videos. Use it only for media you are allowed to analyze, quote or summarize.

Generated files are written to `output/`, which is intentionally ignored because it may contain transcripts, screenshots, notes and HTML derived from third-party media.

## Copyright And Compliance

This repository is distributed under the [MIT License](./LICENSE). It is based on an upstream MIT-licensed project:

- Upstream: [hanshuaikang/AI-Media2Doc](https://github.com/hanshuaikang/AI-Media2Doc)
- Original copyright belongs to the upstream author and contributors.
- New or modified work in this fork belongs to the corresponding contributors and is distributed under the same MIT License.

Only process media that you own, have permission to use, or may legally analyze and quote. A public URL does not automatically grant redistribution rights for transcripts, screenshots or generated notes.

See [NOTICE.md](./NOTICE.md) for details.

## Acknowledgements

Thanks to the upstream AI-Media2Doc author and contributors for the original implementation, documentation, screenshots and open-source foundation.

Thanks also to the projects and tools this repository depends on:

- [AI-Media2Doc](https://github.com/hanshuaikang/AI-Media2Doc)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg)
- [Vue](https://vuejs.org/)
- [Element Plus](https://element-plus.org/)
- [ffmpeg.wasm](https://github.com/ffmpegwasm/ffmpeg.wasm)
- [simple-mind-map](https://github.com/wanglin2/mind-map)

Upstream community mentions, sponsors and contributor materials remain under `docs/` to preserve the original project context and acknowledgements.

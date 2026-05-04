# 后端本地运行

当前后端已改成本地优先：

- 大模型生成：调用本机 `codex exec`，复用 Codex CLI 登录态，不需要 OpenAI/方舟 API Key。
- 音频转写：前端抽出的音频上传到本机后端目录，再由 `faster-whisper` 本地转写，不需要火山 AUC、TOS/S3。
- B站/公开视频链接：后端通过 `yt-dlp` 下载视频，抽取音频用于转写，并用本地 ffmpeg 按 `#image[]` 时间点截帧。

## 1. 前置要求

- Python 3.10+。
- 已安装并登录 Codex CLI：

```bash
codex --version
codex login
```

## 2. 安装依赖

```bash
pip install -r requirements.txt
```

首次运行 `faster-whisper` 会下载模型文件。默认按 4070 Ti 这类本地显卡配置为 `large-v3 + cuda + float16`，优先保证转写质量。

## 3. 可选环境变量

```bash
export CODEX_CLI_PATH=codex
export CODEX_CLI_MODEL=gpt-5.5
export CODEX_CLI_REASONING_EFFORT=xhigh
export LOCAL_UPLOAD_DIR=local_storage/uploads
export LOCAL_MEDIA_DIR=local_storage/media
export LOCAL_SCREENSHOT_DIR=local_storage/screenshots
export LOG_DIR=local_storage/logs
export LOCAL_VIDEO_ARCHIVE_DIRS=
export YTDLP_COOKIES_FILE=
export ASR_PROVIDER=faster-whisper
export ASR_LANGUAGE=auto
export FASTER_WHISPER_MODEL=large-v3
export FASTER_WHISPER_DEVICE=cuda
export FASTER_WHISPER_COMPUTE_TYPE=float16
export WEB_ACCESS_PASSWORD=
```

Windows PowerShell 示例：

```powershell
$env:FASTER_WHISPER_MODEL="large-v3"
$env:FASTER_WHISPER_DEVICE="cuda"
$env:FASTER_WHISPER_COMPUTE_TYPE="float16"
python app.py
```

## 4. 启动服务

```bash
python app.py
```

后端默认监听 `http://localhost:8080`，前端默认也会请求这个地址。

## 5. 说明

- `LOCAL_UPLOAD_DIR` 是本地音频上传目录，相对路径会解析到 `backend/` 目录下。
- `LOCAL_MEDIA_DIR` 是 URL 视频下载目录，`LOCAL_SCREENSHOT_DIR` 是 URL 视频截帧缓存目录。
- URL 视频会写入 `_url_cache.json`，同一个链接再次处理会复用本地视频和音频。
- `LOCAL_VIDEO_ARCHIVE_DIRS` 可配置额外本地视频存档目录，多个目录用英文分号分隔；URL 模式会尝试按视频 ID、标题和唯一时长匹配已有视频，匹配后只抽音频和截图，不重复下载。
- `LOG_DIR` 是后端日志目录，默认会写入 `backend.log`，方便排查失败原因。
- 如果 B站视频需要登录态，导出浏览器 cookies.txt 后把路径填到 `YTDLP_COOKIES_FILE`。
- CPU 转写建议改用 `FASTER_WHISPER_MODEL=small` 或 `base`，并设置：

```bash
export FASTER_WHISPER_DEVICE=cpu
export FASTER_WHISPER_COMPUTE_TYPE=int8
```

- 如果 Codex CLI 调用超时，可在前端“生成设置”里调大超时时间。

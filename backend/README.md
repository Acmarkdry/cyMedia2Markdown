# 后端运行说明

后端是 FastAPI 服务，负责媒体下载、音频抽取、本地 ASR、Codex CLI 调用、截图、HTML 渲染和分布式队列状态 API。

## 环境

Python 固定为 `3.12.x`。依赖由根目录脚本安装，不在 `backend/` 下单独维护旧虚拟环境。

GPU/ASR 环境：

```powershell
..\tools\setup_runtime.ps1 -Role gpu
```

CPU/看板环境：

```powershell
..\tools\setup_runtime.ps1 -Role cpu
```

## 启动

需要本地 ASR、URL 下载或 GPU prepare worker 时使用 GPU 环境：

```powershell
..\.venv-gpu\Scripts\python.exe app.py
```

只用于前端队列看板或轻量 API 检查时可以使用 CPU 环境：

```powershell
..\.venv-cpu\Scripts\python.exe app.py
```

服务默认监听 `http://localhost:8080`。

## 关键环境变量

完整模板见 [../variables_template.env](../variables_template.env)。

```powershell
$env:CODEX_CLI_PATH="codex"
$env:CODEX_CLI_MODEL="gpt-5.5"
$env:CODEX_CLI_REASONING_EFFORT="xhigh"
$env:LOCAL_UPLOAD_DIR="local_storage/uploads"
$env:LOCAL_MEDIA_DIR="local_storage/media"
$env:LOCAL_SCREENSHOT_DIR="local_storage/screenshots"
$env:LOG_DIR="local_storage/logs"
$env:M2M_QUEUE_ROOT="D:\StudyReference\m2m_queue\_queue"
$env:YTDLP_COOKIES_FILE=""
$env:ASR_PROVIDER="faster-whisper"
$env:FASTER_WHISPER_MODEL="large-v3"
$env:FASTER_WHISPER_DEVICE="cuda"
$env:FASTER_WHISPER_COMPUTE_TYPE="float16"
```

CPU 转写仅适合轻量任务，建议使用 `small` 或 `base`，并设置：

```powershell
$env:FASTER_WHISPER_DEVICE="cpu"
$env:FASTER_WHISPER_COMPUTE_TYPE="int8"
```

## API 责任

- `/health`：后端健康检查。
- `/api/v1/files/*`：上传、URL 媒体下载、音频抽取、截图。
- `/api/v1/audio/*`：本地 ASR 任务。
- `/api/v1/llm/*`：Codex CLI 生成、视频笔记 prompt、质量检查。
- `/api/v1/queue/status`：分布式队列看板数据和运行契约。

## 日志

常见日志位置：

```text
backend/local_storage/logs/backend.log
output/parallel_<视频标题>_<timestamp>.log
output/parallel_summary_<timestamp>.json
```

排查顺序：

1. URL 下载失败先看 `routers.files` 日志，需要登录态的视频配置 `YTDLP_COOKIES_FILE`。
2. ASR 失败先看 `routers.audio` 日志、GPU 显存和 `FASTER_WHISPER_*` 配置。
3. Codex 生成失败先看对应 `parallel_*.log`，确认是否已有可复用 chunk。
4. 图片异常先看 `notes_raw.md` 是否含非法 `#image[01:20]` 或带说明文字的截图标记。

## 测试

后端相关测试和验收标准统一维护在 [../docs/testing.md](../docs/testing.md)。最小检查：

```powershell
..\.venv-cpu\Scripts\python.exe -m py_compile app.py routers\queue.py
..\.venv-cpu\Scripts\python.exe ..\tools\m2m_doctor.py --role cpu --queue-root D:\StudyReference\m2m_queue\_queue
```

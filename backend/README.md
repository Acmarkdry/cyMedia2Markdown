# 后端本地运行

当前后端已改成本地优先：

- 大模型生成：调用本机 `codex exec`，复用 Codex CLI 登录态，不需要 OpenAI/方舟 API Key。
- 音频转写：前端抽出的音频上传到本机后端目录，再由 `faster-whisper` 本地转写，不需要火山 AUC、TOS/S3。

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

首次运行 `faster-whisper` 会下载模型文件。默认模型是 `small`，本机性能足够时可以改成 `medium` 或 `large-v3`。

## 3. 可选环境变量

```bash
export CODEX_CLI_PATH=codex
export CODEX_CLI_MODEL=gpt-5.5
export CODEX_CLI_REASONING_EFFORT=xhigh
export LOCAL_UPLOAD_DIR=local_storage/uploads
export ASR_PROVIDER=faster-whisper
export ASR_LANGUAGE=auto
export FASTER_WHISPER_MODEL=small
export FASTER_WHISPER_DEVICE=auto
export FASTER_WHISPER_COMPUTE_TYPE=auto
export WEB_ACCESS_PASSWORD=
```

Windows PowerShell 示例：

```powershell
$env:FASTER_WHISPER_MODEL="small"
$env:FASTER_WHISPER_DEVICE="auto"
python app.py
```

## 4. 启动服务

```bash
python app.py
```

后端默认监听 `http://localhost:8080`，前端默认也会请求这个地址。

## 5. 说明

- `LOCAL_UPLOAD_DIR` 是本地音频上传目录，相对路径会解析到 `backend/` 目录下。
- CPU 转写建议使用 `FASTER_WHISPER_MODEL=small` 或 `base`。
- CUDA 环境可尝试：

```bash
export FASTER_WHISPER_DEVICE=cuda
export FASTER_WHISPER_COMPUTE_TYPE=float16
```

- 如果 Codex CLI 调用超时，可在前端“生成设置”里调大超时时间。

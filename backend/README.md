# 后端本地运行

当前后端已改成本地优先：

- 大模型生成：调用本机 `codex exec`，复用 Codex CLI 登录态，不需要 OpenAI/方舟 API Key。
- 音频转写：前端抽出的音频上传到本机后端目录，再由 `faster-whisper` 本地转写，不需要火山 AUC、TOS/S3。
- B站/公开视频链接：后端通过 `yt-dlp` 下载视频，抽取音频用于转写，并用本地 ffmpeg 按 `#image[]` 时间点截帧。
- 学习笔记生成：默认使用讲义式高密度 prompt，输出自然段解释、时间范围标题和可复查的截图引用。

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

## 6. 视频笔记生成策略

后端 `/api/v1/llm/video-notes` 会把转写段落整理成 Codex prompt，并调用本机 `codex exec`。默认配置偏向质量：

- 模型：`gpt-5.5`。
- 推理强度：`xhigh`。
- 笔记语言：默认中文，Unreal/Lyra/GAS/Common UI 等技术术语保留英文并补充中文解释。
- 笔记风格：讲义式自然段优先，避免把主体写成连续项目符号清单。
- 截图标记：必须是单独一行 `#image[整数秒]`，方括号里只能写阿拉伯数字。

当视频超过约 45 分钟或转写文本过长时，后端会先分块生成局部笔记，再做分组合并和最终合并。重生成脚本还提供 `--merge-strategy assemble`，用于在大合并 prompt 网络不稳定或耗时过长时，本地按时间段拼接各分块笔记。assemble 会把每个分块重复出现的“核心结论 / 术语表 / 实践清单 / 复习问题”等模板栏目抽取到文末全局汇总，避免每个 chunk 重复一遍。

质量检查会评估：

```text
chars              正文字数
image_markers      有效 #image[] 数量
h2 / h3            章节和小节数量
prose_paragraphs   讲义式自然段数量
list_ratio         列表行占比
repeated_template_headings 重复模板小节
```

若质量不足且未关闭 retry，后端会追加一次修复 prompt，要求补足技术细节、截图和自然段表达。批量重生成结果会写入 `output/<视频标题>/backend_video_notes_quality.json`。

## 7. 日志与排查

常见日志位置：

```text
backend/local_storage/logs/backend.log
output/parallel_<视频标题>_<timestamp>.log
output/parallel_summary_<timestamp>.json
```

`tools/batch_video_notes.py` 默认把阶段信息写到标准输出；长时间批处理时建议自行重定向到 `output/batch_<source_id>_<timestamp>.log` 和 `.err.log`，便于中途查看。

排查建议：

- URL 下载失败：先看 `backend.log` 中 `routers.files` 相关行；需要登录态的视频可配置 `YTDLP_COOKIES_FILE`。
- ASR 卡住或失败：检查 `routers.audio` 日志、GPU 显存和 `FASTER_WHISPER_*` 配置。
- Codex 生成慢或断流：`batch_*.err.log` 中可能出现 stream reconnect 或 HTTP fallback；只要进程仍在并最终写出 `notes_raw.md`，通常不需要手动干预。
- 图片异常：检查 `notes_raw.md` 中是否存在非法 `#image[01:20]` 或带中文说明的标记；正常输出会在 `notes.md` 中变成 `![视频截图 mm:ss](screenshots/000123.jpg)`。

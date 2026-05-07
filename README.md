# cyMedia2Markdown

cyMedia2Markdown 是一个本地优先的音视频转 Markdown 工具。它基于上游项目
[hanshuaikang/AI-Media2Doc](https://github.com/hanshuaikang/AI-Media2Doc) 二次开发，
保留 Web 前后端体验，并把主要处理链路调整为本机完成：本地转写、本地大模型调用、本地媒体缓存和本地截图。

## 项目概览

本项目面向需要把公开课程、技术演讲、会议录屏或本地音视频整理成结构化笔记的场景。典型流程是：

1. 上传音频/视频，或输入公开可访问的视频链接。
2. 后端抽取音频并通过 `faster-whisper` 在本机转写。
3. 调用本机 `codex exec` 生成 Markdown、总结、问答内容或截图标记。
4. 对 URL 视频按生成内容中的时间点本地截帧，并插入到 Markdown。
5. 在前端查看、继续追问、导出 Markdown/字幕/思维导图等结果。

## 当前特性

- 本地优先：不依赖云端 ASR，默认使用 `faster-whisper`。
- Codex CLI 生成：复用本机 Codex CLI 登录态调用大模型。
- URL 视频处理：通过 `yt-dlp` 下载公开视频并抽音频。
- 本地缓存：同一 URL 可复用已下载媒体、音频和截图。
- 智能截图：根据 Markdown 中的 `#image[秒数]` 标记截取视频画面。
- 讲义式笔记：默认 prompt 偏向自然段、高密度技术讲义，避免把主体写成机械条目。
- 长视频重生成：支持分块、分组合并、本地 assemble 收尾、质量检查和断点复用。
- 局域网分布式处理：支持 GPU 机器负责 ASR、常开 Mini PC 负责 Codex CLI 生成，通过 SMB 共享队列协同。
- 标题目录：批处理默认使用视频标题作为 `output/` 目录名，并保留 BV 号作为 `source_id`。
- 前端工作台：支持上传、转写、内容生成、AI 对话、结果查看和导出。
- Docker 与本地运行：保留前后端 Dockerfile，并提供本地后端运行脚本。

## 目录结构

```text
backend/                 FastAPI 后端，本地 ASR、媒体处理、Codex CLI 调用
frontend/                Vue 3 + Vite 前端
docs/                    README 截图、赞助与展示素材
tools/                   批量处理辅助脚本
variables_template.env   环境变量模板
docker-compose.yaml      容器化启动示例
NOTICE.md                版权、鸣谢和内容合规说明
LICENSE                  MIT License
```

## 快速开始

### 后端

前置要求：

- Python 3.10+
- 已安装并登录 Codex CLI
- 本机可用的 ffmpeg 运行环境由 `imageio-ffmpeg` 提供
- 如使用 CUDA 转写，需要匹配本机显卡和驱动环境

```bash
cd backend
pip install -r requirements.txt
python app.py
```

后端默认监听 `http://localhost:8080`。

更多配置见 [backend/README.md](./backend/README.md)。

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认由 Vite 启动，并请求本机后端服务。

更多配置见 [frontend/README.md](./frontend/README.md)。

## 常用环境变量

可参考 [variables_template.env](./variables_template.env)。常用项包括：

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

CPU 环境建议把模型调小，例如 `small` 或 `base`，并设置：

```bash
FASTER_WHISPER_DEVICE=cpu
FASTER_WHISPER_COMPUTE_TYPE=int8
```

## 批量处理脚本

批处理工具统一放在 [tools/](./tools/) 下，脚本本身不再写死具体视频链接或本地路径。批量视频清单用 JSON/JSONL manifest 提供，格式参考 [tools/video_manifest.sample.json](./tools/video_manifest.sample.json)：

```json
{
  "videos": [
    {
      "title": "课程或演讲标题",
      "url": "https://www.bilibili.com/video/BVxxxxxxxxxx/"
    }
  ]
}
```

默认会用视频标题生成 `output/<视频标题>/` 目录名，便于本地索引。B 站链接的 BV 号会保存在 `source_id` 中，用于追踪来源或通过 `--only BVxxxxxxxxxx` 过滤；如果需要手动指定目录名，可以在 manifest 中写 `slug` 或 `output_name`。建议把自己的清单放到 `output/` 或其他本地目录，不要把包含个人整理任务的 manifest 提交到仓库。

### URL 到完整笔记

[tools/batch_video_notes.py](./tools/batch_video_notes.py) 适合从 URL 开始完整处理：下载/复用媒体、抽音频、本地 ASR、Codex CLI 生成笔记、截帧并渲染 HTML。后端需要先在 `http://127.0.0.1:8080` 启动。

```powershell
tools\batch_video_notes.cmd --manifest output\my_videos.json
tools\batch_video_notes.cmd --manifest output\my_videos.json --only BVxxxxxxxxxx
tools\batch_video_notes.cmd --manifest output\my_videos.json --start-at "课程或演讲标题"
```

这个脚本默认顺序执行。ASR 会使用 GPU 锁避免多个转写任务抢同一张显卡；已经存在的 `transcript.json`、`notes_raw.md` 会被复用，除非传入 `--force-asr` 或 `--force-codex`。

如果要先批量准备媒体和转写，再交给并行分块重生成器处理，可以加 `--skip-codex`。这会只写出 `status.json`、`transcript.json`、`transcript.srt` 和 `codex_prompt.md`，不生成笔记和截图。

完整流程会在 `output/<视频标题>/` 下生成：

```text
status.json
transcript.json
transcript.srt
codex_prompt.md
notes_raw.md
notes.md
notes.html
screenshots/
```

`notes_raw.md` 是 Codex 原始 Markdown，截图仍是 `#image[整数秒]` 标记；`notes.md` 会把标记替换成 `![视频截图 mm:ss](screenshots/000123.jpg)` 这类引用，避免纯数字 alt 被部分 Markdown 渲染器误识别为图片尺寸。

### 复用已下载视频重生成

如果 `output/<slug>/status.json`、`transcript.json` 和本地媒体缓存已经存在，可以跳过下载和 ASR，直接重生成高密度笔记：

```powershell
backend\.venv\Scripts\python.exe tools\regenerate_video_notes_backend.py --manifest output\my_videos.json --only BVxxxxxxxxxx
```

这个入口走后端 `/api/v1/llm/video-notes`，适合验证 Web 后端真实工作流。

重生成会写入 `backend_video_notes_quality.json`，记录字数、截图数、标题数、讲义式段落数、列表占比、是否触发重试等信息。质量检查失败时默认会追加一次 retry prompt，要求 Codex 补足细节、截图和自然段表达。

### 并行重生成笔记

[tools/launch_parallel_regeneration.py](./tools/launch_parallel_regeneration.py) 会直接调用 [tools/regenerate_video_notes_direct.py](./tools/regenerate_video_notes_direct.py)，绕过 HTTP，适合已有转写和本地视频缓存后并行跑多个 Codex CLI 任务。

```powershell
tools\parallel_regenerate.cmd --all-output --jobs 3
tools\parallel_regenerate.cmd --manifest output\my_videos.json --jobs 3
tools\parallel_regenerate.cmd --slug "课程或演讲标题" --jobs 2
tools\parallel_regenerate.cmd --slug BVxxxxxxxxxx --jobs 2 --merge-strategy assemble
```

`--slug` 可以传输出目录名、视频标题或 `source_id`，B 站视频通常直接传 BV 号即可。并行脚本会解析到对应的中文标题目录，避免在命令行里硬写长中文路径。

常用参数：

```text
--jobs 3                 并行 Codex CLI 数量，建议先从 2-3 开始
--chunk-minutes 12       长视频分块分钟数
--llm-timeout 3600       单个 Codex 调用超时时间
--force-chunks           忽略 direct_chunks 缓存，重新生成分块笔记
--cache-after-epoch N    只复用修改时间晚于该 epoch 的 chunk/质量缓存
--merge-group-size 3     Codex 分组合并时每组包含几个分块
--merge-strategy codex   默认策略，分块后继续用 Codex 合并
--merge-strategy assemble 本地按时间段拼接分块笔记，适合大合并 prompt 卡住时保留密度
--no-quality-retry       关闭质量检查失败后的重试
--no-clear-screenshots   保留已有截图
--dry-run                只打印将要执行的任务，不启动 Codex
--shutdown               全部任务完成后 3 分钟自动关机
```

每个子任务日志写入 `output/parallel_<视频标题>_<timestamp>.log`，汇总写入 `output/parallel_summary_<timestamp>.json`。对于 60 分钟以上或转写过长的视频，建议优先使用分块；如果最终合并反复卡住，可以改用 `--merge-strategy assemble`，它不会再发起最后的大合并请求，而是保留各分块讲义内容并按全局时间线组织。assemble 会把每个分块重复出现的“核心结论 / 术语表 / 实践清单 / 复习问题”等模板栏目抽取到文末全局汇总，避免每个 chunk 重复一遍。

### 局域网分布式处理

如果有一台常开的 Mini PC 和一台带 NVIDIA 显卡但可能休眠的 Windows 主机，可以使用分布式队列模式：

- GPU 主机运行 prepare worker，负责下载/复用媒体、抽音频和本地 ASR。
- Mini PC 运行 Codex worker，负责并发调用 Codex CLI、截图、渲染 HTML 和质量检查。
- 两台机器通过 SMB 共享目录交换任务状态和产物，不共享 Codex 登录态，也不要求 GPU 主机常开。

典型命令：

```powershell
tools\distributed_enqueue.cmd --queue-root \\MINIPC\m2m_queue --manifest output\course.json
tools\distributed_prepare_worker.cmd --queue-root \\MINIPC\m2m_queue --project-root D:\StudyResource\Media2Markdown\AI-Media2Doc
tools\distributed_codex_worker.cmd --queue-root \\MINIPC\m2m_queue --project-root D:\StudyResource\Media2Markdown\AI-Media2Doc --jobs 3 --merge-strategy assemble --no-clear-screenshots
tools\distributed_status.cmd --queue-root \\MINIPC\m2m_queue
```

分布式 worker 会维护任务状态、运行租约、心跳、重试记录和日志。GPU 主机睡眠或 Codex CLI 中断后，可以通过 `requeue` 重试失败阶段。完整说明见 [Windows 局域网分布式处理指南](./docs/distributed_windows.md)。

### 笔记风格与截图约束

当前默认 prompt 的目标是“讲义式高密度技术复习资料”：

- 主体使用自然段解释机制、因果关系、工程取舍和例子。
- 列表只用于流程、对比、术语表、实践清单、复习问题和少量核心结论。
- `#image[]` 中只能写阿拉伯数字，例如 `#image[120]`，不能写 `01:20`、中文说明或单位。
- `##` 标题要求带 `[mm:ss-mm:ss]` 或 `[hh:mm:ss-hh:mm:ss]` 时间范围。
- 质量检查会关注正文长度、截图数量、章节/小节数量、讲义式段落数量、列表占比和重复模板小节。

### 重建截图和 HTML

如果只改了截图引用、HTML 样式或截帧规则，不需要重跑 Codex，可以用：

```powershell
backend\.venv\Scripts\python.exe tools\rebuild_note_assets.py --refresh-screenshots
backend\.venv\Scripts\python.exe tools\rebuild_note_assets.py "课程或演讲标题"
```

脚本会读取现有 `notes_raw.md`，重新生成 `notes.md`、`notes.html` 和截图引用。`--refresh-screenshots` 会删除并重新截取 `output/<视频标题>/screenshots/`。

如果已经有一批旧的 `output/BV.../` 目录，可以把它们重命名成视频标题目录：

```powershell
backend\.venv\Scripts\python.exe tools\rename_output_dirs.py --dry-run
backend\.venv\Scripts\python.exe tools\rename_output_dirs.py
```

所有批处理结果都会写入 `output/`。该目录已被 `.gitignore` 排除，因为里面可能包含字幕、截图、笔记和其他来自第三方媒体的派生内容，不应默认提交到公开仓库。

## 版权与内容合规

本仓库采用 [MIT License](./LICENSE)。本项目基于上游 MIT 开源项目二次开发：

- 原始项目：[hanshuaikang/AI-Media2Doc](https://github.com/hanshuaikang/AI-Media2Doc)
- 原始项目版权归原作者及其贡献者所有。
- 本仓库新增或修改部分版权归对应贡献者所有，并继续按 MIT License 分发。

请只处理你拥有权利、已获授权，或依法可进行个人学习、研究、引用和整理的音视频内容。公开视频链接不等于可再分发内容；由本工具生成的转写稿、截图、笔记和 HTML 可能仍受原始音视频版权约束。

更多说明见 [NOTICE.md](./NOTICE.md)。

## 鸣谢

感谢上游项目作者和贡献者提供完整的 AI Media2Doc 基础实现与开源许可。

感谢以下项目和社区工具：

- [AI-Media2Doc](https://github.com/hanshuaikang/AI-Media2Doc)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg)
- [Vue](https://vuejs.org/)
- [Element Plus](https://element-plus.org/)
- [ffmpeg.wasm](https://github.com/ffmpegwasm/ffmpeg.wasm)
- [simple-mind-map](https://github.com/wanglin2/mind-map)

上游 README 中列出的社区传播者、赞助者和贡献者同样值得感谢；本 fork 保留 `docs/` 中相关素材，仅用于延续原项目说明和鸣谢语境。

## 相关文档

- [后端本地运行](./backend/README.md)
- [前端本地运行](./frontend/README.md)
- [Windows 局域网分布式处理指南](./docs/distributed_windows.md)
- [赞助与原项目鸣谢素材](./docs/sponsors.md)

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

[tools/batch_video_notes.py](./tools/batch_video_notes.py) 是一个本地批处理辅助脚本，用于调用后端 URL 媒体接口、转写、生成笔记并渲染 HTML。它适合处理已确认有权学习、整理或引用的公开视频。

脚本会把结果写入 `output/`。该目录已被 `.gitignore` 排除，因为里面可能包含字幕、截图、笔记和其他来自第三方媒体的派生内容，不应默认提交到公开仓库。

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
- [赞助与原项目鸣谢素材](./docs/sponsors.md)

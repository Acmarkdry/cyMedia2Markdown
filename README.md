# cyMedia2Markdown

cyMedia2Markdown 是一个本地优先的音视频转 Markdown 学习工作台。基于上游
[hanshuaikang/AI-Media2Doc](https://github.com/hanshuaikang/AI-Media2Doc) 二次开发，
把课程视频、技术演讲、会议录屏和本地媒体整理成可复习的高密度 Markdown/HTML 讲义。

同时提供**赛博洗稿**功能：两阶段 AI 流水线将多篇相关文章 URL + 本地源码工程转换为深度综合性知识笔记。

## 能力边界

- **本地 ASR**：`faster-whisper` 本机转写音频
- **OpenCode CLI**：复用本机 OpenCode 登录态，不转成 API Key
- **URL 媒体处理**：`yt-dlp` 下载公开视频并缓存
- **智能截图**：按 `#image[秒数]` 标记自动截帧
- **长视频处理**：分块、分组合并、`assemble` 收尾、断点复用
- **分布式处理**：GPU(媒体+ASR) + CPU(OpenCode) 通过队列协作
- **前端看板**：上传、生成、结果查看、队列状态
- **赛博洗稿**：多文章 URL + 本地源码 → 两阶段 AI 深度知识笔记，5 种预设 Prompt 模板

## 快速开始

```powershell
# 1. 安装环境
tools\setup_runtime.ps1 -Role cpu
tools\setup_runtime.ps1 -Role frontend

# 2. 配置环境变量
copy variables_template.env variables.env
# 编辑 variables.env，主要配置 OPENCODE_CLI_MODEL 等

# 3. 启动后端
cd backend
..\.venv-cpu\Scripts\python.exe app.py
# 监听 http://localhost:8080

# 4. 启动前端（新终端）
cd frontend
npm run dev
# 监听 http://localhost:5173
```

使用 GPU ASR 或赛博洗稿功能见下方文档链接。

## 文档索引

| 文档 | 说明 |
|------|------|
| [docs/installation.md](./docs/installation.md) | 详细安装、多角色环境配置、环境变量、自检命令 |
| [docs/workflows-video.md](./docs/workflows-video.md) | 视频处理工作流：URL→笔记、并行重生成、分布式处理 |
| [docs/workflows-washing.md](./docs/workflows-washing.md) | 赛博洗稿工作流：文章提取、两阶段 AI、Prompt 编写指南 |
| [docs/distributed_windows.md](./docs/distributed_windows.md) | 分布式处理完整规范（队列契约、Worker 参数、故障恢复） |
| [docs/testing.md](./docs/testing.md) | 测试分层、用例、验收规范 |
| [docs/output-convention.md](./docs/output-convention.md) | 输出目录结构和产物说明 |

## 运行契约速查

| 项目 | 规范 |
|------|------|
| Python | `3.12.x`（`.python-version` 写死） |
| CPU 环境 | `.venv-cpu`，OpenCode worker + 前端后端 |
| GPU 环境 | `.venv-gpu`，ASR + 媒体下载 |
| 后端端口 | `8080` |
| 前端端口 | `5173` |
| 输出目录 | `output/`（不提交） |
| 队列目录 | 项目外 `_queue/` |

## 许可证

本项目基于 [AI-Media2Doc](https://github.com/hanshuaikang/AI-Media2Doc) 二次开发。

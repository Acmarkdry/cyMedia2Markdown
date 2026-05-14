# cyMedia2Markdown

cyMedia2Markdown 是一个本地优先的音视频转 Markdown 学习工作台。它基于上游
[hanshuaikang/AI-Media2Doc](https://github.com/hanshuaikang/AI-Media2Doc) 二次开发，
当前重点是把课程视频、技术演讲、会议录屏和本地媒体整理成可复习的高密度 Markdown/HTML 讲义。

## 能力边界

- 本地 ASR：通过 `faster-whisper` 在本机转写音频。
- OpenCode CLI 生成：复用本机 OpenCode CLI 登录态，不把登录态转成 API Key。
- URL 媒体处理：通过 `yt-dlp` 下载公开视频并缓存媒体文件。
- 智能截图：按 `#image[秒数]` 标记截帧，最终写入 `notes.md` 和 `notes.html`。
- 长视频处理：支持分块、分组合并、本地 `assemble` 收尾、质量检查和断点复用。
- 分布式处理：GPU 机负责媒体准备和 ASR，CPU/Mini PC 负责 OpenCode 生成，通过独立队列目录协作。
- 前端看板：提供上传、生成、结果查看、队列状态和运行契约 review。

## 运行契约

| 项目 | 规范 |
| --- | --- |
| Python | 固定 `3.12.x`，根目录 `.python-version` 写死 `3.12` |
| CPU 环境 | `.venv-cpu`，负责 OpenCode worker、前端看板后端和轻量脚本 |
| GPU 环境 | `.venv-gpu`，负责后端 ASR、媒体下载和 prepare worker |
| 共享父目录 | 只放项目源码和队列，例如 `D:\StudyReference\m2m_queue` |
| 项目目录 | `D:\StudyReference\m2m_queue\AI-Media2Doc`，每台机器本机磁盘各放一份 |
| 队列目录 | 项目目录外的 `_queue`，例如 `D:\StudyReference\m2m_queue\_queue` |
| Worker 入口 | `tools\start_worker.ps1 -Role cpu|gpu` |
| 最终输出目录 | `AI-Media2Doc\output\`，本机最终笔记目录，不提交 |
| 后端缓存目录 | `AI-Media2Doc\backend\local_storage\`，本机媒体、上传、后端日志缓存，不提交 |
| 队列产物目录 | `_queue\artifacts\`，跨机器交换 prepare/opencode 产物，不手工编辑 |

## 目录结构

```text
D:\StudyReference\m2m_queue\
  AI-Media2Doc\                    项目源码；CPU 机和 GPU 机都应使用本机磁盘克隆
    backend\                       FastAPI 后端，媒体处理、ASR、OpenCode 调用和队列 API
      local_storage\               本机后端缓存，不提交
        media\                     URL 下载或上传后的本机媒体缓存
        uploads\                   上传临时文件
        screenshots\               后端截图缓存
        logs\                      后端服务日志
    frontend\                      Vue 3 + Vite 前端工作台
    docs\                          项目规范、分布式流程和测试用例
    skills\                        OpenCode 项目技能说明
    tools\                         批处理、分布式 worker、自检和质量检查脚本
    output\                        本机最终转写、截图、Markdown 和 HTML，不提交
    variables_template.env         环境变量模板
    docker-compose.yaml            容器化启动示例
    NOTICE.md                      版权、鸣谢和内容合规说明
  _queue\                          分布式共享队列，只放任务状态、日志和跨机产物
    jobs\                          每个视频一个任务 JSON
    artifacts\                     prepare/opencode 阶段跨机器交换产物
      <job_id>\output\<video_slug>\ 对应 output\<video_slug> 的队列副本
      <job_id>\media\<video_file>   prepare 阶段导出的媒体副本
    logs\                          worker 命令日志和任务事件日志
    work\manifests\                worker 自动拆出的单视频 manifest
```

标准目录以 `/api/v1/queue/status` 返回的 `contract.storage_contract` 为准。`_queue\artifacts` 是分布式交换副本；日常 review、编辑和归档优先看本机 `AI-Media2Doc\output`。

## 快速开始

### 安装运行环境

```powershell
tools\setup_runtime.ps1 -Role cpu
tools\setup_runtime.ps1 -Role gpu
tools\setup_runtime.ps1 -Role frontend
```

只有 CPU 机时先装 `cpu` 和 `frontend` 即可；需要本地 CUDA ASR 或 GPU worker 时再装 `gpu`。

### 启动后端

GPU/ASR 后端：

```powershell
cd backend
..\.venv-gpu\Scripts\python.exe app.py
```

只查看队列看板或跑 CPU worker 的 Mini PC 后端：

```powershell
cd backend
..\.venv-cpu\Scripts\python.exe app.py
```

后端默认监听 `http://localhost:8080`。

### 启动前端

```powershell
cd frontend
npm run dev
```

前端默认监听 `http://localhost:5173`，并请求本机后端。

### 自检

```powershell
.\.venv-cpu\Scripts\python.exe tools\m2m_doctor.py --role cpu --queue-root D:\StudyReference\m2m_queue\_queue
.\.venv-cpu\Scripts\python.exe tools\m2m_doctor.py --role frontend
```

完整本机检查：

```powershell
tools\run_quality_checks.ps1
```

单独检查或修复目录/队列路径元数据：

```powershell
.\.venv-cpu\Scripts\python.exe tools\check_storage_layout.py --queue-root D:\StudyReference\m2m_queue\_queue
.\.venv-cpu\Scripts\python.exe tools\check_storage_layout.py --queue-root D:\StudyReference\m2m_queue\_queue --fix
```

## 常用工作流

### URL 到完整笔记

后端先启动，然后执行：

```powershell
tools\batch_video_notes.cmd --manifest output\my_videos.json
tools\batch_video_notes.cmd --manifest output\my_videos.json --only BVxxxxxxxxxx
```

manifest 示例见 [tools/video_manifest.sample.json](./tools/video_manifest.sample.json)。建议把个人课程清单放在 `output/`，不要提交到仓库。

### 已有转写并行重生成

```powershell
tools\parallel_regenerate.cmd --all-output --jobs 3 --merge-strategy assemble
tools\parallel_regenerate.cmd --slug BVxxxxxxxxxx --jobs 2 --merge-strategy assemble
```

`assemble` 会本地按时间线组织分块笔记，适合长视频或最终大合并不稳定的情况。

### 分布式处理

```powershell
tools\distributed_enqueue.cmd --queue-root D:\StudyReference\m2m_queue\_queue --manifest output\course.json
tools\start_worker.ps1 -Role gpu -QueueRoot \\MINIPC\m2m_queue\_queue -ProjectRoot D:\Local\AI-Media2Doc
tools\start_worker.ps1 -Role cpu -QueueRoot D:\StudyReference\m2m_queue\_queue -Jobs 3
tools\distributed_status.cmd --queue-root D:\StudyReference\m2m_queue\_queue
```

GPU 机的 `-ProjectRoot` 必须是 GPU 本机磁盘上的项目克隆，不能是 SMB 项目路径。完整规范见 [docs/distributed_windows.md](./docs/distributed_windows.md)。

## 输出约定

每个视频的最终产物写入本机 `AI-Media2Doc\output\<视频标题>\`。分布式 CPU worker 完成后，会把同一份目录同步到 `_queue\artifacts\<job_id>\output\<视频标题>\`，供其他机器拉取或核对。

```text
status.json
transcript.json
transcript.srt
opencode_prompt.md
notes_raw.md
notes.md
notes.html
screenshots/
backend_video_notes_quality.json
```

`notes_raw.md` 保留 OpenCode 原始输出；`notes.md` 会把 `#image[整数秒]` 转为真实截图引用。质量文件记录字数、截图数量、章节数量、自然段数量、列表占比和是否通过重试。

## 文档索引

- [后端运行说明](./backend/README.md)
- [前端运行说明](./frontend/README.md)
- [Windows 分布式处理规范](./docs/distributed_windows.md)
- [测试用例与验收规范](./docs/testing.md)
- [版权与内容合规](./NOTICE.md)

## 内容合规

请只处理你拥有权利、已获授权，或依法可进行个人学习、研究、引用和整理的音视频内容。公开视频链接不等于可再分发内容；由本工具生成的转写稿、截图、笔记和 HTML 可能仍受原始音视频版权约束。

## 鸣谢

感谢上游 AI-Media2Doc 作者和贡献者提供基础实现与 MIT 开源许可。感谢 `faster-whisper`、`yt-dlp`、`imageio-ffmpeg`、Vue、Element Plus、ffmpeg.wasm 和 simple-mind-map 等项目。

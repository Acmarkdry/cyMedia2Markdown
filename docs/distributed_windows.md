# Windows 局域网分布式处理指南

本文档说明如何在两台 Windows 机器上稳定协同运行 Media2Markdown：

- Mini PC：常开，负责共享队列、Codex CLI 生成、最终产物保存。
- GPU PC：可休眠，负责下载/复用媒体、抽音频、本地 ASR 转写。
- 共享队列：一个两台机器都能读写的 SMB 目录，例如 `\\MINIPC\m2m_queue`。

分布式模式不会重写现有 ASR、截图、Codex 生成和质量检查逻辑。它只在外层增加任务队列、锁、lease、heartbeat、重试状态和跨机器产物同步。

## 适用场景

这个模式适合以下机器组合：

- 一台常开的 Mini PC，可以长期运行 Codex CLI。
- 一台带 NVIDIA 显卡的 Windows 主机，可以跑 `faster-whisper` CUDA 转写，但可能睡眠或临时关机。
- 两台机器在同一局域网内，可以访问同一个 SMB 共享目录。

如果只有一台机器，继续使用 `tools\batch_video_notes.cmd` 或 `tools\parallel_regenerate.cmd` 即可。

## 工作流

```text
manifest
  |
  v
enqueue 写入共享队列
  |
  v
GPU prepare-worker
  - 下载/复用视频
  - 抽音频
  - 本地 ASR
  - 写出 status.json / transcript.json / codex_prompt.md
  - 发布 output/<slug>/ 和 media/<video_filename>
  |
  v
Mini PC codex-worker
  - 导入准备好的 output 和 video 文件
  - 调用 Codex CLI 生成笔记
  - 截图、渲染 HTML、质量检查
  - 发布 notes.md / notes.html / screenshots / quality.json
```

## 队列目录结构

建议在 Mini PC 上创建共享目录：

```powershell
mkdir D:\m2m_queue
```

然后把它共享为：

```text
\\MINIPC\m2m_queue
```

分布式脚本会在共享目录下维护这些子目录：

```text
\\MINIPC\m2m_queue\
  jobs\                  每个视频一个 JSON 任务文件
  artifacts\             准备阶段和最终阶段的产物包
  logs\                  命令日志和队列事件日志
  work\manifests\        worker 自动生成的单视频 manifest
```

每个任务 JSON 是持久状态机：

```text
queued -> prepare_running -> prepared -> codex_running -> done
                  |                         |
                  v                         v
             prepare_failed            codex_failed
```

运行中的任务会记录：

- `owner`：当前 worker 标识。
- `lease_until`：租约过期时间。
- `last_heartbeat`：最近一次心跳时间。
- `attempts`：prepare/codex 各自尝试次数。
- `last_error`：最近一次失败原因和日志路径。

如果 GPU PC 睡眠、断电或进程退出，任务会停留在 `prepare_running`。等 `lease_until` 过期后，worker 可以重新认领并继续处理。

## 两台机器准备

两台机器都保留一份 `AI-Media2Doc` 工作目录，路径可以不同，但运行命令时要用各自机器上的真实路径传给 `--project-root`。

GPU PC 需要：

- 后端依赖已安装。
- CUDA 版 `faster-whisper` 能正常运行。
- 后端服务已启动，例如 `http://127.0.0.1:8080`。
- 能访问 `\\MINIPC\m2m_queue`。

Mini PC 需要：

- Codex CLI 已安装并登录。
- 后端 Python 依赖已安装，因为 Codex worker 会复用截图、HTML 渲染和质量检查逻辑。
- 能访问 `\\MINIPC\m2m_queue`。

## 入队任务

manifest 格式仍然使用现有批处理清单：

```json
{
  "videos": [
    {
      "source_id": "BVxxxxxxxxxx",
      "title": "课程标题",
      "url": "https://www.bilibili.com/video/BVxxxxxxxxxx/"
    }
  ]
}
```

在任意一台机器执行：

```powershell
tools\distributed_enqueue.cmd `
  --queue-root \\MINIPC\m2m_queue `
  --manifest output\course.json
```

重复执行入队命令不会覆盖已有状态，只会更新任务里的视频元数据。需要强制替换任务文件时再加 `--replace`。

## 运行 GPU 准备 worker

在 4070Ti 机器上先启动后端，然后执行：

```powershell
tools\distributed_prepare_worker.cmd `
  --queue-root \\MINIPC\m2m_queue `
  --project-root D:\StudyResource\Media2Markdown\AI-Media2Doc `
  --api-base http://127.0.0.1:8080/api/v1 `
  --media-timeout 1800
```

prepare worker 一次只处理一个视频，适合单 GPU。它会调用：

```powershell
tools\batch_video_notes.py --skip-codex
```

成功后会把这些内容发布到共享队列：

- `output/<slug>/status.json`
- `output/<slug>/transcript.json`
- `output/<slug>/transcript.srt`
- `output/<slug>/codex_prompt.md`
- `backend/local_storage/media/<video_filename>`

常用参数：

```text
--once                    只扫描并处理一轮
--max-jobs 3              本次最多处理 3 个任务
--lease-seconds 1800      单个任务租约时间
--heartbeat-interval 60   心跳刷新间隔
--force-asr               忽略已有 transcript，强制重新转写
```

## 运行 Mini PC Codex worker

在 Mini PC 上执行：

```powershell
tools\distributed_codex_worker.cmd `
  --queue-root \\MINIPC\m2m_queue `
  --project-root D:\StudyResource\Media2Markdown\AI-Media2Doc `
  --jobs 3 `
  --merge-strategy assemble `
  --no-clear-screenshots `
  --llm-timeout 3600
```

Codex worker 会先把准备好的 `output/<slug>/` 和视频文件导入 Mini PC 本地项目目录，再调用：

```powershell
tools\regenerate_video_notes_direct.py --slug <source_id>
```

它会验证这些结果：

- `notes.md` 存在。
- `notes.html` 存在。
- `backend_video_notes_quality.json` 存在。
- `quality.passed` 为 `true`。

通过后任务进入 `done`，并把最终 `output/<slug>/` 回写到共享队列的 `artifacts/` 目录。

建议先用 `--jobs 2`，稳定后再增加到 `3`。如果长视频很多，默认推荐 `--merge-strategy assemble`，它比最后再做一次大 Codex 合并更稳定。

## 查看状态

普通表格输出：

```powershell
tools\distributed_status.cmd --queue-root \\MINIPC\m2m_queue
```

JSON 输出：

```powershell
tools\distributed_status.cmd --queue-root \\MINIPC\m2m_queue --json
```

日志位置：

```text
\\MINIPC\m2m_queue\logs\
```

典型日志包括：

- `<job_id>_prepare_<timestamp>.log`
- `<job_id>_codex_<timestamp>.log`
- `<job_id>.jsonl`

## 重试任务

重试 ASR/媒体准备失败的任务：

```powershell
tools\distributed_video_notes.cmd requeue `
  --queue-root \\MINIPC\m2m_queue `
  --stage prepare `
  --job BVxxxxxxxxxx
```

重试 Codex 生成失败的任务：

```powershell
tools\distributed_video_notes.cmd requeue `
  --queue-root \\MINIPC\m2m_queue `
  --stage codex `
  --job BVxxxxxxxxxx
```

只在明确要把已完成或正在运行的任务拉回早期状态时使用 `--force`。

## 推荐默认值

GPU prepare worker：

```text
--lease-seconds 1800
--heartbeat-interval 60
--media-timeout 1800
```

Mini PC Codex worker：

```text
--jobs 2 或 3
--merge-strategy assemble
--no-clear-screenshots
--llm-timeout 3600
```

如果 Codex CLI 偶发中断，直接重试 Codex 阶段即可。`direct_chunks/` 缓存会随 `output/<slug>/` 一起同步，通常不需要从头生成。

## 故障处理

### GPU 机器睡眠

现象：任务停在 `prepare_running`。

处理：等待 `lease_until` 过期后重新启动 prepare worker。任务会重新认领。如果本地已有 `transcript.json`，现有脚本会复用缓存。

### Mini PC 缺少视频文件

现象：Codex worker 在调用 Codex 前失败，错误包含 `Missing artifact media` 或 `Cached video file is missing`。

处理：检查 `\\MINIPC\m2m_queue\artifacts\<job_id>\media\` 是否存在视频文件；重新运行 prepare worker 或手动修复共享目录权限后重试 codex 阶段。

### Codex 生成质量不通过

现象：任务进入 `codex_failed`，但命令可能 exit code 为 0。

原因：稳定模式要求 `backend_video_notes_quality.json` 中 `quality.passed` 为 `true`。

处理：查看对应 codex 日志，必要时调整 `--remarks`、`--chunk-minutes` 或 `--merge-strategy assemble` 后重试。

### 共享目录权限问题

现象：worker 无法创建 `jobs/*.lock`、无法写入 `artifacts/` 或 `logs/`。

处理：确认两台机器对 `\\MINIPC\m2m_queue` 都有读写权限。不要把队列放到 OneDrive 同步目录里，避免文件锁和延迟同步导致状态混乱。

## 端到端冒烟测试

建议先用一个短视频 manifest 验证：

```powershell
tools\distributed_enqueue.cmd --queue-root \\MINIPC\m2m_queue --manifest output\smoke.json
tools\distributed_prepare_worker.cmd --queue-root \\MINIPC\m2m_queue --project-root D:\StudyResource\Media2Markdown\AI-Media2Doc --once
tools\distributed_codex_worker.cmd --queue-root \\MINIPC\m2m_queue --project-root D:\StudyResource\Media2Markdown\AI-Media2Doc --once --jobs 1 --merge-strategy assemble
tools\distributed_status.cmd --queue-root \\MINIPC\m2m_queue
```

冒烟测试通过后，再把 prepare worker 和 codex worker 放到 Windows 任务计划程序里开机自启或登录自启。

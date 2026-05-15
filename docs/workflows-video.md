# URL 到完整笔记 — 视频处理工作流

## 概述

将一个或多个视频 URL（B站、YouTube 等）或本地视频文件，自动转换为高密度 Markdown/HTML 学习笔记。完整流水线：下载媒体 → ASR 转写 → OpenCode 生成笔记 → 质量检查。

需要后端先启动（`http://localhost:8080`）。

## 单视频处理

### 前端操作

1. 打开 `http://localhost:5173`，默认在「视频工作台」
2. 粘贴视频 URL 或拖放本地视频/音频文件
3. 选择输出风格：知识笔记 / 小红书 / 公众号 / 内容总结 / 思维导图 / 字幕文件
4. 可选：填写备注（补充要求，不影响格式规范）
5. 点击「开始生成」

处理流程：
```
初始化 FFmpeg → 提取音频 → 准备媒体 → 音频转文字 → 生成图文
```

### 命令行批量处理

先准备视频清单 manifest（示例见 `tools/video_manifest.sample.json`）：

```json
{
  "videos": [
    {
      "title": "课程或演讲标题",
      "url": "https://www.bilibili.com/video/BVxxxxxxxxxx/"
    },
    {
      "source_id": "video-002",
      "slug": "自定义输出目录名",
      "title": "第二个视频标题",
      "url": "https://example.com/path/to/video.mp4"
    }
  ]
}
```

manifest 字段说明：

| 字段 | 必填 | 说明 |
|------|------|------|
| `url` | 是 | 视频 URL（B站/YouTube/直链） |
| `title` | 否 | 视频标题，影响输出目录名 |
| `source_id` | 否 | 唯一标识，B站视频自动提取 BV 号 |
| `slug` | 否 | 输出目录名，默认用 title 生成 |

运行命令：

```powershell
# 处理整个清单
tools\batch_video_notes.cmd --manifest output\my_videos.json

# 只处理指定视频（用 source_id 筛选）
tools\batch_video_notes.cmd --manifest output\my_videos.json --only BVxxxxxxxxxx

# 自定义参数
tools\batch_video_notes.cmd --manifest output\my_videos.json --poll-interval 20 --media-timeout 1800
```

### 分步处理（调试用）

```powershell
# 第一步：只做媒体准备 + ASR，不生成笔记
tools\batch_video_notes.cmd --manifest output\my_videos.json --skip-opencode

# 检查转写结果后，并行重生成笔记
tools\parallel_regenerate.cmd --all-output --jobs 3 --merge-strategy assemble
```

## 已有转写并行重生成

当视频已转写但需要重新生成笔记时（比如换模型、换风格），不需要重新下载和 ASR：

```powershell
# 重生成 output 目录下所有视频
tools\parallel_regenerate.cmd --all-output --jobs 3 --merge-strategy assemble

# 只重生成指定视频
tools\parallel_regenerate.cmd --slug BVxxxxxxxxxx --jobs 2 --merge-strategy assemble

# 指定 LLM 超时和 token
tools\parallel_regenerate.cmd --all-output --jobs 3 --llm-timeout 1200 --max-tokens 16384
```

参数说明：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--all-output` | - | 处理 output 目录下所有已有转写的视频 |
| `--slug` | - | 只处理指定 slug 的视频 |
| `--jobs` | `1` | 并行数（每 job 一个 OpenCode 实例） |
| `--merge-strategy` | `opencode` | 合并策略：`opencode` 或 `assemble` |
| `--chunk-minutes` | `12` | 每块时长（分钟） |
| `--llm-timeout` | `3600` | LLM 超时（秒） |
| `--max-tokens` | - | 最大输出 token |

合并策略：
- `opencode`：由 OpenCode 直接合并分块笔记（适合较短视频）
- `assemble`：本地按时间线组织分块笔记再让 OpenCode 收尾（适合长视频，更稳定）

## 长视频处理策略

对于超过 30 分钟的视频，系统会自动分块处理：

1. **分块阶段**：视频按 `chunk_minutes` 分钟切分，每块独立生成笔记
2. **合并阶段**：按 `merge_strategy` 合并分块笔记
3. **质量检查**：校验截图引用、时间标记、内容完整性
4. **断点复用**：重跑时跳过已完成的分块

如果某块失败，单独重跑该块即可，不需要重跑整个视频。

## 分布式处理

多机器协同：GPU 机做媒体下载 + ASR，CPU 机做 OpenCode 生成。

### 架构

```
GPU 机器（prepare worker）          CPU 机器（opencode worker）
┌─────────────────────┐           ┌─────────────────────┐
│ 下载视频             │           │ 读取队列任务          │
│ yt-dlp 提取音频      │           │ 从 artifacts 获取转写  │
│ faster-whisper ASR  │ ──SMB──▶  │ OpenCode CLI 生成    │
│ 写入 artifacts       │           │ 结果写回 artifacts     │
└─────────────────────┘           └─────────────────────┘
         │                                   │
         └─────────── _queue/ ───────────────┘
              (SMB 共享队列目录)
```

### 操作步骤

```powershell
# 步骤 1：在任意机器上创建 manifest 并入队
tools\distributed_enqueue.cmd --queue-root D:\StudyReference\m2m_queue\_queue --manifest output\course.json

# 步骤 2：GPU 机器启动 prepare worker（下载 + ASR）
# 注意：ProjectRoot 必须是 GPU 本机磁盘路径，不能用 SMB 路径
tools\start_worker.ps1 -Role gpu -QueueRoot \\MINIPC\m2m_queue\_queue -ProjectRoot D:\Local\AI-Media2Doc

# 步骤 3：CPU 机器启动 opencode worker（笔记生成）
tools\start_worker.ps1 -Role cpu -QueueRoot D:\StudyReference\m2m_queue\_queue -Jobs 3

# 步骤 4：查看分布式任务状态
tools\distributed_status.cmd --queue-root D:\StudyReference\m2m_queue\_queue
```

### Worker 参数速查

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-Role` | 必填 | `cpu` 或 `gpu` |
| `-QueueRoot` | 环境变量或自动检测 | 队列根目录 |
| `-ProjectRoot` | 自动检测 | 项目目录（GPU 必须本机路径） |
| `-Jobs` | `2` | CPU worker 并行数 |
| `-ChunkMinutes` | `12` | 分块时长 |
| `-LlmTimeout` | `3600` | LLM 超时 |
| `-MaxTokens` | - | 最大 token |
| `-MergeStrategy` | `assemble` | 合并策略 |
| `-PollInterval` | `30` | 队列轮询间隔（秒） |
| `-MediaTimeout` | `1800` | 媒体下载超时 |
| `-LeaseSeconds` | `1800` | 任务租约时长 |
| `-MaxAttempts` | `3` | 最大重试次数 |
| `-Once` | - | 处理一个任务即退出 |
| `-DryRun` | - | 预演模式（打印命令不执行） |
| `-ForceAsr` | - | 强制重新 ASR |
| `-NoQualityRetry` | - | 跳过质量重试 |

### 故障恢复

- **任务状态**：每个任务一个 JSON 文件在 `_queue/jobs/`，状态流转：`queued → prepare_running → prepared → opencode_running → done`
- **租约机制**：worker 通过文件锁获取任务，超时未心跳自动释放
- **重试**：失败任务自动重试（默认最多 3 次），超过后标记 `failed`
- **断点续传**：已完成阶段不会重复执行
- **手动重置**：删除 `_queue/jobs/<job_id>.json` 重新入队

## 质量检查

每次生成的笔记会经过自动质量检查：

```powershell
# 校验指定视频的输出完整性
.\.venv-cpu\Scripts\python.exe tools\validate_video_outputs.py --slug BVxxxxxxxxxx

# 校验所有 output 目录
.\.venv-cpu\Scripts\python.exe tools\validate_video_outputs.py --all-output

# 重建笔记资产（如截图丢失可重新截取）
.\.venv-cpu\Scripts\python.exe tools\rebuild_note_assets.py --slug BVxxxxxxxxxx
```

检查项：
- 必需文件是否存在（notes.md, notes.html, transcript.json 等）
- 截图引用 `#image[秒数]` 是否完整
- 时间标记格式是否正确
- 内容字符数是否达标
- 质量文件 `backend_video_notes_quality.json` 指标

## 输出约定

详见 [docs/output-convention.md](./output-convention.md#视频笔记输出)。

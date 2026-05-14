# Windows 局域网分布式处理规范

本文档是分布式视频笔记流程的运行契约。目标是让 CPU 机、GPU 机和前端看板按同一套规则协作，而不是依赖临时 agent 调度。

## 核心原则

- Python 版本固定为 `3.12.x`，项目根目录 `.python-version` 写死 `3.12`。
- 项目代码目录和队列目录必须分离。队列目录只放任务状态、日志和产物，不放项目源码。
- CPU/GPU 使用同一个启动入口：`tools\start_worker.ps1 -Role cpu|gpu`。
- GPU 机的 `-ProjectRoot` 必须是 GPU 本机磁盘上的项目克隆，不能是 SMB/UNC 路径。
- CPU 机负责 OpenCode CLI 生成、截图、HTML 渲染和质量检查；GPU 机负责媒体下载/复用、抽音频和本地 ASR。
- 所有机器先跑 `tools\m2m_doctor.py` 自检，失败就修环境，不直接开 worker 碰运气。

## 标准目录

Mini PC 作为共享宿主时，建议目录如下：

```text
D:\StudyReference\m2m_queue\
  AI-Media2Doc\                    项目源码，本机运行 CPU worker 和前端
    output\                        本机最终笔记、截图、HTML 和质量报告
    backend\local_storage\         本机后端缓存
      media\                       URL 下载或上传后的本机媒体缓存
      uploads\                     上传临时文件
      screenshots\                 后端截图缓存
      logs\                        后端服务日志
  _queue\                          分布式共享队列
    jobs\                          每个视频一个任务 JSON
    artifacts\                     prepare/opencode 阶段跨机器交换产物
      <job_id>\output\<video_slug>\ output\<video_slug> 的队列副本
      <job_id>\media\<video_file>   prepare 阶段导出的媒体副本
    logs\                          worker 命令日志和事件日志
    work\manifests\                worker 自动拆出的单视频 manifest
```

父目录下不再使用单独的 `logs\`。旧流程留下的父级 `logs\` 应移动到 `_queue\logs\legacy_*` 后清空，避免后续排查时同时看两套日志。

目录职责必须固定：

| 路径 | 责任 | 是否共享 |
| --- | --- | --- |
| `AI-Media2Doc\output\` | 当前机器可直接 review 的最终学习资料 | 不作为 worker 协作入口 |
| `AI-Media2Doc\backend\local_storage\media\` | 当前机器后端可访问的媒体缓存 | 不跨机器直接引用 |
| `_queue\jobs\` | 任务状态、租约、重试次数和路径元数据 | 共享 |
| `_queue\artifacts\` | GPU prepare 和 CPU opencode 之间交换输出与媒体副本 | 共享 |
| `_queue\logs\` | worker stdout/stderr、命令日志、任务事件 JSONL | 共享 |
| `_queue\work\manifests\` | worker 临时生成的单视频 manifest | 共享 |

队列看板和后端 API 以 `/api/v1/queue/status` 的 `contract.storage_contract` 作为机器可读契约；README 和本文档必须与该字段保持一致。

SMB 只共享父目录，例如：

```text
\\MINIPC\m2m_queue
```

其他机器访问队列时使用：

```text
\\MINIPC\m2m_queue\_queue
```

不要再把 `\\MINIPC\m2m_queue\AI-Media2Doc` 当作 GPU 机的 `-ProjectRoot`。GPU 机应在自己的磁盘上放一份项目，例如：

```text
D:\Local\AI-Media2Doc
```

## 环境安装

在项目根目录执行。脚本只接受 Python `3.12`，会拒绝其他大版本/小版本。

CPU 机：

```powershell
tools\setup_runtime.ps1 -Role cpu
```

GPU 机：

```powershell
tools\setup_runtime.ps1 -Role gpu
```

前端：

```powershell
tools\setup_runtime.ps1 -Role frontend
```

一次性安装全部角色也可以：

```powershell
tools\setup_runtime.ps1 -Role all
```

生成的环境固定为：

```text
.venv-cpu\       CPU/OpenCode worker 依赖
.venv-gpu\       GPU/ASR worker 依赖
frontend\node_modules\
```

## 自检

CPU 机：

```powershell
.\.venv-cpu\Scripts\python.exe tools\m2m_doctor.py `
  --role cpu `
  --queue-root D:\StudyReference\m2m_queue\_queue
```

GPU 机：

```powershell
.\.venv-gpu\Scripts\python.exe tools\m2m_doctor.py `
  --role gpu `
  --project-root D:\Local\AI-Media2Doc `
  --queue-root \\MINIPC\m2m_queue\_queue `
  --api-base http://127.0.0.1:8080/api/v1
```

doctor 会检查：

- Python 是否为 `3.12.x`。
- `.venv-cpu` / `.venv-gpu` 是否能运行。
- `ProjectRoot` 是否存在 `backend/ frontend/ tools/`。
- `ProjectRoot` 是否错误地放进了 `QueueRoot`。
- GPU 机是否错误地用 SMB 路径作为 `ProjectRoot`。
- CPU 机是否能执行 OpenCode CLI。
- GPU 机后端健康检查是否可达。

## 启动后端

GPU 机需要先启动后端，让 prepare worker 调用本地下载、抽音频和 ASR 接口：

```powershell
cd D:\Local\AI-Media2Doc\backend
..\.venv-gpu\Scripts\python.exe app.py
```

Mini PC 如果只跑 CPU worker，不需要为了分布式队列启动后端；前端看板需要后端时再启动：

```powershell
cd D:\StudyReference\m2m_queue\AI-Media2Doc\backend
..\.venv-cpu\Scripts\python.exe app.py
```

## 入队

manifest 继续沿用现有格式：

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

入队命令：

```powershell
tools\distributed_enqueue.cmd `
  --queue-root D:\StudyReference\m2m_queue\_queue `
  --manifest output\course.json
```

重复入队不会覆盖已有状态，只会更新视频元数据。确实要替换任务文件时再加 `--replace`。

## 启动 Worker

CPU/GPU 都使用同一个入口，只通过 `-Role` 区分行为。

Mini PC 启动 CPU worker：

```powershell
tools\start_worker.ps1 `
  -Role cpu `
  -QueueRoot D:\StudyReference\m2m_queue\_queue `
  -Jobs 3 `
  -MergeStrategy assemble
```

GPU 机启动 GPU worker：

```powershell
tools\start_worker.ps1 `
  -Role gpu `
  -ProjectRoot D:\Local\AI-Media2Doc `
  -QueueRoot \\MINIPC\m2m_queue\_queue `
  -ApiBase http://127.0.0.1:8080/api/v1
```

常用参数：

```text
-Once                 只处理一轮，适合冒烟测试
-DryRun               认领后打印命令并释放任务，不真正执行
-MaxJobs 3            本次最多处理 3 个任务
-LeaseSeconds 1800    单任务租约时间
-HeartbeatInterval 60 心跳刷新间隔
-ForceAsr             GPU 角色强制重新转写
-Jobs 3               CPU 角色并发 OpenCode 任务数
-NoQualityRetry       CPU 角色关闭质量重试
```

底层 Python 命令同样统一：

```powershell
.\.venv-cpu\Scripts\python.exe tools\distributed_video_notes.py worker --role cpu --queue-root D:\StudyReference\m2m_queue\_queue
.\.venv-gpu\Scripts\python.exe tools\distributed_video_notes.py worker --role gpu --queue-root \\MINIPC\m2m_queue\_queue
```

## 状态与重试

查看状态：

```powershell
tools\distributed_status.cmd --queue-root D:\StudyReference\m2m_queue\_queue
tools\distributed_status.cmd --queue-root D:\StudyReference\m2m_queue\_queue --json
```

检查目录契约和 job 路径元数据：

```powershell
.\.venv-cpu\Scripts\python.exe tools\check_storage_layout.py `
  --queue-root D:\StudyReference\m2m_queue\_queue `
  --strict
```

如果旧流程留下了非运行任务的 artifact 路径元数据，可修复：

```powershell
.\.venv-cpu\Scripts\python.exe tools\check_storage_layout.py `
  --queue-root D:\StudyReference\m2m_queue\_queue `
  --fix
```

重试 prepare 阶段：

```powershell
tools\distributed_video_notes.cmd requeue `
  --queue-root D:\StudyReference\m2m_queue\_queue `
  --stage prepare `
  --job BVxxxxxxxxxx
```

重试 OpenCode 阶段：

```powershell
tools\distributed_video_notes.cmd requeue `
  --queue-root D:\StudyReference\m2m_queue\_queue `
  --stage opencode `
  --job BVxxxxxxxxxx
```

只在明确要把已完成或正在运行的任务拉回早期状态时使用 `--force`。

## 前端看板

后端 `/api/v1/queue/status` 会返回运行契约，包括：

- Python 规范。
- 项目根目录。
- 队列根目录。
- 最终输出目录、后端本地缓存目录和队列子目录。
- CPU/GPU 虚拟环境位置。
- 标准安装、自检和启动命令。

前端分布式看板会直接展示这些信息，方便 review 当前机器是否按规范运行。

## 冒烟测试

建议先用一个短视频验证端到端：

```powershell
tools\distributed_enqueue.cmd --queue-root D:\StudyReference\m2m_queue\_queue --manifest output\smoke.json
tools\start_worker.ps1 -Role gpu -ProjectRoot D:\Local\AI-Media2Doc -QueueRoot \\MINIPC\m2m_queue\_queue -Once
tools\start_worker.ps1 -Role cpu -QueueRoot D:\StudyReference\m2m_queue\_queue -Once -Jobs 1
tools\distributed_status.cmd --queue-root D:\StudyReference\m2m_queue\_queue
```

冒烟测试通过后，再把同一条 `tools\start_worker.ps1` 命令放到 Windows 任务计划程序里。

更完整的分布式测试矩阵见 [测试用例与验收规范](./testing.md)。

## 故障处理

任务停在 `prepare_running`：GPU 机可能睡眠或后端退出。等待 lease 过期后重新启动 `-Role gpu` worker。

任务停在 `opencode_running`：CPU 机 OpenCode CLI 可能中断。等待 lease 过期后重新启动 `-Role cpu` worker，必要时 requeue opencode 阶段。

报错 `ProjectRoot must not live inside QueueRoot`：项目源码和 `_queue` 放混了。移动 `_queue` 到项目目录外，或重新传入正确的 `-QueueRoot`。

报错 `GPU worker ProjectRoot must be a local clone`：GPU 机使用了 SMB 项目路径。改为 GPU 本机磁盘路径，只让 `-QueueRoot` 指向 SMB。

报错 `python executable must be Python 3.12.x`：删除错误虚拟环境，重新运行 `tools\setup_runtime.ps1 -Role cpu|gpu`。

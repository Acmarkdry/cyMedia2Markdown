# 测试用例与验收规范

本文档定义 cyMedia2Markdown 的测试分层、命令入口和人工验收用例。以后改动后优先更新这里，不再把测试说明分散到多个 README。

## 测试分层

| 层级 | 目标 | 运行时机 | 入口 |
| --- | --- | --- | --- |
| L0 静态与契约检查 | 确认 Python 3.12、脚本语法、基础命令入口、队列路径契约 | 每次提交前 | `tools\run_quality_checks.ps1` |
| L1 模块冒烟 | 后端导入、doctor、自检、前端构建、worker dry-run | 每次涉及代码或脚本改动 | `tools\run_quality_checks.ps1` |
| L2 分布式队列冒烟 | 验证入队、CPU/GPU worker 参数、状态流转、租约释放 | 改动分布式脚本或队列 API 后 | 本文“分布式队列用例” |
| L3 端到端视频处理 | 验证下载、ASR、Codex、截图、HTML、质量文件 | 改动媒体/ASR/Codex/截图逻辑后 | 本文“端到端视频用例” |
| L4 人工 UI 验收 | 验证前端交互、队列看板、错误展示和移动端布局 | 改动前端页面后 | 本文“前端验收用例” |

## 一键质量检查

本机提交前推荐运行：

```powershell
tools\run_quality_checks.ps1
```

如果只想跑后端和脚本检查，跳过前端构建：

```powershell
tools\run_quality_checks.ps1 -SkipFrontendBuild
```

默认检查项：

- Python 入口是否为 `3.12.x`。
- `tests/` 下的自动化 unittest 是否通过。
- `tools\m2m_doctor.py --role cpu` 是否通过。
- `tools\m2m_doctor.py --role frontend` 是否通过。
- 关键 Python 文件是否可编译。
- 分布式 worker 统一入口是否存在并可打印 help。
- `batch_video_notes.cmd`、`parallel_regenerate.cmd` 是否可打印 help。
- 队列状态命令是否能读取标准 `_queue`。
- 前端 `npm run build` 是否成功。

## 自动化覆盖现状

已自动化：

- Manifest 解析、Windows 文件名清洗、重复 slug 去重、选择器过滤。
- 队列看板数据归一化、p 序排序、lease 过期判断、运行契约命令。
- 分布式队列入队、认领、dry-run 释放、prepare/codex 完成状态、artifact 导入导出。
- Doctor 对 Python 3.12、队列目录分离、GPU SMB ProjectRoot 禁止策略的报告。
- 生成产物校验：必需文件、质量文件、未收尾 `#image[]`、纯数字图片 alt、缺失截图。

未自动化，需人工或专用机器执行：

- 真实 B 站/公开视频下载。
- 真实 GPU `faster-whisper` 转写。
- 真实 Codex CLI 长视频生成。
- 浏览器交互、队列看板视觉布局和移动端布局。

## L0 静态与契约用例

### TC-L0-001 Python 版本固定

步骤：

```powershell
Get-Content .python-version
py -3.12 --version
```

期望：

- `.python-version` 内容为 `3.12`。
- `py -3.12 --version` 输出 `Python 3.12.x`。
- 不存在新的 `backend\.venv`、`.venv-worker` 或 3.13 运行入口说明。

### TC-L0-002 依赖分层

步骤：

```powershell
Get-Content backend\requirements-cpu.txt
Get-Content backend\requirements-gpu.txt
Get-Content backend\requirements.txt
```

期望：

- CPU 依赖不包含 `faster-whisper` 和 CUDA wheel。
- GPU 依赖通过 `-r requirements-cpu.txt` 继承 CPU 依赖。
- `requirements.txt` 只作为完整后端兼容入口，引用 GPU 依赖。

### TC-L0-003 统一 worker 入口

步骤：

```powershell
cmd /c tools\distributed_video_notes.cmd worker --help
powershell -NoProfile -ExecutionPolicy Bypass -File tools\start_worker.ps1 -Role cpu -Once -DryRun -MaxJobs 1
```

期望：

- help 中存在 `--role {cpu,gpu}`。
- `start_worker.ps1` 先运行 doctor，再输出 preflight。
- dry-run 会打印将执行的命令并释放任务，不生成笔记。

## L1 模块冒烟用例

### TC-L1-001 Python 编译

步骤：

```powershell
.\.venv-cpu\Scripts\python.exe -m py_compile `
  backend\app.py `
  backend\routers\queue.py `
  tools\m2m_doctor.py `
  tools\distributed_video_notes.py `
  tools\batch_video_notes.py `
  tools\launch_parallel_regeneration.py `
  tools\regenerate_video_notes_direct.py `
  tools\rebuild_note_assets.py `
  tools\rename_output_dirs.py `
  tools\validate_video_outputs.py
```

期望：命令 exit code 为 0。

### TC-L1-002 自动化单元测试

步骤：

```powershell
.\.venv-cpu\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

期望：

- `test_video_manifest.py` 覆盖 manifest 解析和选择器。
- `test_queue_status.py` 覆盖队列看板归一化。
- `test_distributed_queue.py` 覆盖入队、认领、完成和 artifact 流转。
- `test_doctor_contract.py` 覆盖运行契约失败与成功路径。
- `test_validate_outputs.py` 覆盖生成产物质量校验。
- 命令 exit code 为 0。

### TC-L1-003 后端导入

步骤：

```powershell
.\.venv-cpu\Scripts\python.exe -c "import sys; sys.path.insert(0, 'backend'); import app; print(app.app.title)"
```

期望：输出 `AI Media2Doc API`。

### TC-L1-004 Doctor 自检

步骤：

```powershell
.\.venv-cpu\Scripts\python.exe tools\m2m_doctor.py --role cpu --queue-root D:\StudyReference\m2m_queue\_queue
.\.venv-cpu\Scripts\python.exe tools\m2m_doctor.py --role frontend
```

期望：

- 两条命令都输出 `AI-Media2Doc doctor: OK`。
- CPU 检查能识别 Codex CLI。
- Frontend 检查能识别 node/npm。

### TC-L1-005 前端构建

步骤：

```powershell
cd frontend
npm run build
```

期望：

- Vite build exit code 为 0。
- lottie `eval` 和 chunk size 警告允许存在，但不能出现编译错误。

## L2 分布式队列用例

### TC-L2-001 队列目录分离

步骤：

```powershell
.\.venv-cpu\Scripts\python.exe tools\m2m_doctor.py `
  --role cpu `
  --project-root D:\StudyReference\m2m_queue\AI-Media2Doc `
  --queue-root D:\StudyReference\m2m_queue\_queue
```

期望：doctor 通过。

反向用例：

```powershell
.\.venv-cpu\Scripts\python.exe tools\m2m_doctor.py `
  --role cpu `
  --project-root D:\StudyReference\m2m_queue\AI-Media2Doc `
  --queue-root D:\StudyReference\m2m_queue
```

期望：doctor 失败，并提示 `project_root must not be inside queue_root`。

### TC-L2-002 GPU ProjectRoot 禁止 SMB

步骤：

```powershell
.\.venv-cpu\Scripts\python.exe tools\m2m_doctor.py `
  --role gpu `
  --project-root \\MINIPC\m2m_queue\AI-Media2Doc `
  --queue-root \\MINIPC\m2m_queue\_queue
```

期望：doctor 失败，并提示 GPU `project_root` 必须是本机路径。

### TC-L2-003 队列状态读取

步骤：

```powershell
tools\distributed_status.cmd --queue-root D:\StudyReference\m2m_queue\_queue
tools\distributed_status.cmd --queue-root D:\StudyReference\m2m_queue\_queue --json
```

期望：

- 表格输出包含 `queue_root` 和 `counts`。
- JSON 输出可被 `ConvertFrom-Json` 解析。

### TC-L2-004 Worker dry-run 不破坏产物

步骤：

```powershell
tools\start_worker.ps1 -Role cpu -QueueRoot D:\StudyReference\m2m_queue\_queue -Once -DryRun -MaxJobs 1
```

期望：

- 输出 `dry_run: true`。
- 不创建新的 `notes.md`、`notes.html`。
- 被认领任务会释放回可运行状态。

## L3 端到端视频用例

这些用例会下载媒体、调用 ASR 和 Codex，耗时较长，只在改动核心链路后执行。

### TC-L3-001 单视频完整处理

准备 `output\smoke.json`：

```json
{
  "videos": [
    {
      "source_id": "smoke_video",
      "title": "冒烟测试视频",
      "url": "https://www.bilibili.com/video/BVxxxxxxxxxx/"
    }
  ]
}
```

步骤：

```powershell
tools\batch_video_notes.cmd --manifest output\smoke.json --only smoke_video
```

期望：

- `output\冒烟测试视频\status.json` 存在。
- `transcript.json`、`notes_raw.md`、`notes.md`、`notes.html` 存在。
- `backend_video_notes_quality.json` 中 `quality.passed` 为 `true`。
- `notes.md` 不再包含 `#image[`。
- Markdown 图片引用的截图文件都存在。

### TC-L3-002 准备阶段与并行生成拆分

步骤：

```powershell
tools\batch_video_notes.cmd --manifest output\smoke.json --only smoke_video --skip-codex
tools\parallel_regenerate.cmd --slug smoke_video --jobs 1 --merge-strategy assemble --no-clear-screenshots
```

期望：

- 第一条命令只生成 `transcript.json`、`transcript.srt`、`codex_prompt.md`。
- 第二条命令生成 `notes.md`、`notes.html`、质量文件和截图。
- 重复执行第二条命令会复用已有 chunk，除非显式传 `--force-chunks`。

### TC-L3-003 质量文件校验

步骤：

```powershell
.\.venv-cpu\Scripts\python.exe tools\validate_video_outputs.py --output-root output
```

期望：输出 `video output validation: OK`。

只检查某个视频：

```powershell
.\.venv-cpu\Scripts\python.exe tools\validate_video_outputs.py --output-root output --source-id BVxxxxxxxxxx
```

## L4 前端验收用例

### TC-L4-001 基础页面

步骤：

1. 启动后端。
2. 启动前端 `npm run dev`。
3. 打开 `http://localhost:5173`。

期望：

- 左侧导航可见。
- “新建任务”可打开上传/URL 输入流程。
- 设置页可执行后端连通性检查。

### TC-L4-002 队列看板

步骤：

1. 后端设置 `M2M_QUEUE_ROOT` 或使用默认 `_queue`。
2. 打开前端“队列看板”。

期望：

- 顶部显示 Python 规范、项目根目录、队列根目录、CPU/GPU 环境和统一 worker 命令。
- 汇总区显示总任务、已完成、运行中、待办、失败。
- 任务列表按 p 序或 job id 排序。
- 选中任务后右侧显示阶段、owner、heartbeat、lease、artifact 和最近事件。
- 后端不可达时显示错误提示，不出现空白页。

### TC-L4-003 响应式布局

步骤：

在桌面宽屏、约 1180px、约 720px 三个宽度查看队列看板。

期望：

- 文本不重叠。
- 命令、路径和 job id 能换行。
- 表格和详情区在窄屏下纵向排列。

## 提交前检查清单

- [ ] 根 README 只保留入口说明，细节链接到专题文档。
- [ ] 后端/前端 README 没有重复的大段快速开始内容。
- [ ] 没有引用已删除的旧图片、赞助或英文 README。
- [ ] `rg -n "backend\\.venv|\\.venv-worker|Python 3\\.10|distributed_prepare_worker|distributed_codex_worker" README.md docs backend frontend tools skills --glob "!docs/testing.md"` 无有效命中。
- [ ] `tools\run_quality_checks.ps1` 通过，或明确记录未运行原因。
- [ ] 涉及前端时 `npm run build` 通过。

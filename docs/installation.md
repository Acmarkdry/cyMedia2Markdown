# 安装与环境配置

## 安装运行环境

```powershell
# CPU 环境（OpenCode 生成 + 前端后端 + 轻量脚本）
tools\setup_runtime.ps1 -Role cpu

# GPU 环境（本地 CUDA ASR + 媒体下载）
tools\setup_runtime.ps1 -Role gpu

# 前端开发环境（Node.js + npm）
tools\setup_runtime.ps1 -Role frontend
```

只有 CPU 机时先装 `cpu` 和 `frontend` 即可；需要本地 CUDA ASR 或 GPU worker 时再装 `gpu`。

## 赛博洗稿依赖

赛博洗稿功能需要额外的 Python 包：

```powershell
..\.venv-cpu\Scripts\pip.exe install trafilatura
```

## 环境变量

复制模板并编辑：

```powershell
copy variables_template.env variables.env
```

### 必配项

| 变量 | 说明 | 示例 |
|------|------|------|
| `OPENCODE_CLI_PATH` | OpenCode CLI 路径 | `opencode` |
| `OPENCODE_CLI_MODEL` | 使用的模型 | `gpt-5.5` |
| `OPENCODE_CLI_REASONING_EFFORT` | 推理力度 | `xhigh` |

### ASR 配置（GPU 环境）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ASR_PROVIDER` | ASR 引擎 | `faster-whisper` |
| `ASR_LANGUAGE` | 语言 | `auto` |
| `FASTER_WHISPER_MODEL` | 模型 | `large-v3` |
| `FASTER_WHISPER_DEVICE` | 设备 | `cuda` |
| `FASTER_WHISPER_COMPUTE_TYPE` | 计算精度 | `float16` |

### 分布式配置

| 变量 | 说明 |
|------|------|
| `M2M_QUEUE_ROOT` | 分布式队列根目录，必须在项目目录外 |
| `LOCAL_VIDEO_ARCHIVE_DIRS` | 本地视频存档目录（分号分隔），URL 模式会复用已下载视频 |
| `YTDLP_COOKIES_FILE` | B站登录 cookies.txt 路径 |

### 安全

| 变量 | 说明 |
|------|------|
| `WEB_ACCESS_PASSWORD` | 前端访问密码（留空则无需密码） |

### 赛博洗稿

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `WASHING_USER_AGENT` | 文章提取 UA | Chrome 120 |
| `WASHING_REQUEST_TIMEOUT` | 提取超时（秒） | `30` |

## 启动后端

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

## 启动前端

```powershell
cd frontend
npm run dev
```

前端默认监听 `http://localhost:5173`，并请求本机后端。

## 自检

```powershell
# 快速自检
.\.venv-cpu\Scripts\python.exe tools\m2m_doctor.py --role cpu --queue-root D:\StudyReference\m2m_queue\_queue
.\.venv-cpu\Scripts\python.exe tools\m2m_doctor.py --role frontend

# 完整本机检查（含测试、前端构建）
tools\run_quality_checks.ps1

# 跳过前端构建
tools\run_quality_checks.ps1 -SkipFrontendBuild

# 检查/修复队列路径元数据
.\.venv-cpu\Scripts\python.exe tools\check_storage_layout.py --queue-root D:\StudyReference\m2m_queue\_queue
.\.venv-cpu\Scripts\python.exe tools\check_storage_layout.py --queue-root D:\StudyReference\m2m_queue\_queue --fix
```

## 目录结构

```text
D:\StudyReference\m2m_queue\
  AI-Media2Doc\                    项目源码
    backend\                       FastAPI 后端
      local_storage\               本机后端缓存（不提交）
    frontend\                      Vue 3 + Vite 前端
    docs\                          项目文档
    skills\                        OpenCode 项目技能
    tools\                         批处理、worker、自检脚本
    output\                        本机最终笔记（不提交）
  _queue\                          分布式共享队列
    jobs\                          每个视频一个任务 JSON
    artifacts\                     prepare/opencode 跨机交换产物
    logs\                          worker 日志和事件日志
```

标准目录以 `/api/v1/queue/status` 返回的 `contract.storage_contract` 为准。
`_queue\artifacts` 是分布式交换副本；日常 review 优先看本机 `output/`。

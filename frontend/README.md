# 前端运行说明

前端是 Vue 3 + Vite 工作台，负责上传入口、生成结果查看、设置页和分布式队列看板。

## 环境

```powershell
..\tools\setup_runtime.ps1 -Role frontend
```

脚本会在 `frontend/` 内执行 `npm install`。Node.js 建议使用 20+。

## 启动

```powershell
npm run dev
```

默认访问 `http://localhost:5173`。接口请求走 `frontend/src/config.js` 中的 `VITE_API_BASE_URL`，未配置时请求 `http://localhost:8080`。

## 构建

```powershell
npm run build
```

当前构建可能出现 lottie 依赖的 `eval` 提示和大 chunk 提示，只要 exit code 为 0 即可视为前端基础构建通过。是否做代码分包另行排期。

## 队列看板

侧边栏“队列看板”读取 `/api/v1/queue/status`，展示：

- Python 版本和 CPU/GPU 虚拟环境。
- 项目根目录、队列根目录和标准启动命令。
- 当前运行任务、待办任务、失败任务和最近事件。
- 每个任务的 prepare/codex 阶段状态、租约和心跳。

## 测试

前端测试和人工验收标准统一维护在 [../docs/testing.md](../docs/testing.md)。最小检查：

```powershell
npm run build
```

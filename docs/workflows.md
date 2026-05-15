# 常用工作流

## URL 到完整笔记

后端先启动，然后执行：

```powershell
tools\batch_video_notes.cmd --manifest output\my_videos.json
tools\batch_video_notes.cmd --manifest output\my_videos.json --only BVxxxxxxxxxx
```

manifest 示例见 [tools/video_manifest.sample.json](../tools/video_manifest.sample.json)。
建议把个人课程清单放在 `output/`，不要提交到仓库。

## 已有转写并行重生成

```powershell
tools\parallel_regenerate.cmd --all-output --jobs 3 --merge-strategy assemble
tools\parallel_regenerate.cmd --slug BVxxxxxxxxxx --jobs 2 --merge-strategy assemble
```

`assemble` 会本地按时间线组织分块笔记，适合长视频或最终大合并不稳定的情况。

## 分布式处理

```powershell
# 入队
tools\distributed_enqueue.cmd --queue-root D:\StudyReference\m2m_queue\_queue --manifest output\course.json

# GPU worker（媒体准备 + ASR）
tools\start_worker.ps1 -Role gpu -QueueRoot \\MINIPC\m2m_queue\_queue -ProjectRoot D:\Local\AI-Media2Doc

# CPU worker（OpenCode 生成）
tools\start_worker.ps1 -Role cpu -QueueRoot D:\StudyReference\m2m_queue\_queue -Jobs 3

# 查看状态
tools\distributed_status.cmd --queue-root D:\StudyReference\m2m_queue\_queue
```

GPU 机的 `-ProjectRoot` 必须是 GPU 本机磁盘上的项目克隆，不能是 SMB 项目路径。
完整规范见 [docs/distributed_windows.md](./distributed_windows.md)。

## 赛博洗稿 — 多文章融合深化

将多篇相关主题文章 URL + 可选本地源码工程，通过两阶段 AI 流水线（领域理解 → 深度精炼）转换为一篇高密度综合性知识笔记。

### 前置依赖

```powershell
..\.venv-cpu\Scripts\pip.exe install trafilatura
```

### 前端操作

顶部导航切换到「赛博洗稿」Tab，工作台提供 5 种预设 Prompt 模板：

| 预设 | 适用场景 |
|------|----------|
| 技术深度分析 | 技术文章，深度挖掘原理与实现 |
| 源码对照学习 | 有本地源码工程，理论+实现对照 |
| 知识体系构建 | 多篇综述文章，构建系统化框架 |
| 论文综述整理 | 学术论文/技术报告，整理研究综述 |
| 自定义 | 空白模板，自行编写提示词 |

选择预设后自动填充两阶段提示词（Stage 1 上下文理解 + Stage 2 深度精炼）。
支持添加本地工程路径（如 Lyra 项目、Unreal 引擎），AI 会读取源码并对照文章进行深度分析。

### 命令行

```powershell
# 准备文章清单（示例见 tools\article_manifest.sample.json）
tools\article_washing.cmd --manifest output\my_articles.json ^
  --context-prompt "这些文章是关于 UE GAS 技能系统的" ^
  --refinement-prompt "请深入解析核心概念和架构设计"

# 清单带本地工程路径
tools\article_washing.cmd --manifest output\my_articles_with_code.json ^
  --context-prompt "UE Lyra 框架分析" ^
  --refinement-prompt "结合源码分析实现细节"

# CLI 参数传入工程路径
tools\article_washing.cmd --manifest output\my_articles.json ^
  --context-prompt "..." ^
  --refinement-prompt "..." ^
  --code-projects '[{"label":"Lyra","path":"D:/LyraStarterGame"}]'

# 指定输出风格和 token 预算
tools\article_washing.cmd --manifest output\my_articles.json ^
  --context-prompt "..." ^
  --refinement-prompt "..." ^
  --style deep --max-tokens 16384 --timeout 1200
```

风格选项：`deep`（深度学习）、`concise`（精简）、`comprehensive`（全面）。

### manifest 格式

文章清单是一个 JSON 文件，支持纯数组或带 `articles` 键的对象：

```json
[
  {
    "title": "UE5 大规模开放世界性能优化实践",
    "url": "https://zhuanlan.zhihu.com/p/123456789"
  },
  {
    "title": "深入理解 GAS 游戏技能系统架构设计",
    "url": "https://www.example.com/gas-architecture-deep-dive"
  }
]
```

带本地工程路径：

```json
{
  "articles": [
    {"title": "GAS 深入分析", "url": "https://example.com/gas"}
  ],
  "code_projects": [
    {
      "label": "Lyra项目",
      "path": "D:/UnrealProjects/LyraStarterGame",
      "file_patterns": ["*.h", "*.cpp"]
    }
  ]
}
```

### 输出结构

```text
output/article_washing/<slug>/
  notes.md              # 最终精炼笔记
  domain_summary.md     # Stage 1 领域知识脉络
  sources.json          # 各篇文章提取结果和要点分析
  code_files.json       # 读取的源码文件清单
  stage1_prompt.md      # Stage 1 prompt（可复现）
  stage2_prompt.md      # Stage 2 prompt（可复现）
```

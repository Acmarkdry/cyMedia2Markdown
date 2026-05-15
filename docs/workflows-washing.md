# 赛博洗稿 — 多文章融合深化工作流

## 概述

"赛博洗稿"通过两阶段 AI 流水线，将多篇相关主题的文章 URL + 可选的本地源码工程，转化为一篇深度综合性知识笔记。

**两阶段流水线**：

```
┌─────────────────────────────────────────────────────┐
│ Stage 1: 领域理解                                    │
│ 输入: context_prompt + 各文章 LLM 要点分析             │
│ 输出: domain_summary (领域知识脉络)                    │
├─────────────────────────────────────────────────────┤
│ Stage 2: 深度精炼                                    │
│ 输入: domain_summary + 原文全文 + 源码文件 + refinement │
│ 输出: refined_output (最终综合性深度笔记)              │
└─────────────────────────────────────────────────────┘
```

**关键能力**：
- URL → Markdown 自动提取（trafilatura，含元数据：作者/日期/站点）
- 本地源码工程扫描（自动跳过构建目录，语言检测）
- 5 种预设 Prompt 模板，开箱即用
- 输出可复现（保存两阶段完整 prompt）

## 前置条件

```powershell
# 安装文章提取依赖
..\.venv-cpu\Scripts\pip.exe install trafilatura

# 启动后端
cd backend
..\.venv-cpu\Scripts\python.exe app.py
```

## 前端操作

### 入口

打开 `http://localhost:5173`，顶部导航切换到「赛博洗稿」Tab。

### 工作台布局

```
┌──────────────────┬──────────────────────────────┐
│ 文章管理          │ Prompt 配置                   │
│ [+ 添加URL]      │ [预设模板标签栏]               │
│ URL 1    [✕]     │ 上下文提示 (Stage 1)          │
│ URL 2    [✕]     │ ┌────────────────────────┐   │
│                  │ │ 自动填充或自行编辑      │   │
│ 本地工程          │ └────────────────────────┘   │
│ [+ 添加工程]     │ 深化提示 (Stage 2)            │
│ Lyra项目  [✕]    │ ┌────────────────────────┐   │
│  D:\Lyra         │ │ 自动填充或自行编辑      │   │
│                  │ └────────────────────────┘   │
│                  │ 风格: [深度学习▼]             │
│                  │ 超时: [600] Token: [16384]   │
│                  │ [开始洗稿]  [重置]            │
├──────────────────┴──────────────────────────────┤
│ 结果展示                                        │
│ [文章原文] [领域脉络] [最终笔记] [源码参考]       │
└─────────────────────────────────────────────────┘
```

### 预设 Prompt 模板

| 模板 | 适用场景 | Stage 1 侧重 | Stage 2 侧重 |
|------|----------|-------------|-------------|
| **技术深度分析** | 技术文章深度挖掘 | 核心概念、架构、流程、关系 | 原理→实现→场景→对比→实践五维度 |
| **源码对照学习** | 有本地源码工程 | 架构分层、模块职责、数据结构 | 理论vs实现对照、调用链、设计模式 |
| **知识体系构建** | 多篇综述性文章 | 领域图谱、子领域关系、演进脉络 | 系统化框架、概念关联、学习路径 |
| **论文综述整理** | 学术论文/技术报告 | 问题定义、方法分类、评估指标 | 方法对比表格、批判分析、未来方向 |
| **自定义** | 完全自由编写 | 空白 | 空白 |

点击预设标签即可切换，两个 textarea 自动填充对应的提示词。可以在预设基础上自由编辑。

### 本地工程

点击「添加工程」弹窗填写：

| 字段 | 说明 | 示例 |
|------|------|------|
| 工程名称 | 用于标注源码来源 | `Lyra项目` |
| 工程路径 | 本地绝对路径 | `D:\UnrealProjects\LyraStarterGame` |
| 文件匹配（可选） | 逗号分隔的 glob，默认 `*.h,*.cpp,*.py,*.ts,*.js` | `*.h,*.cpp` |

系统会自动：
- 跳过构建目录（Intermediate, Binaries, DerivedDataCache 等）
- 跳过依赖目录（node_modules, .git, vendor 等）
- 按文件大小排序（小文件优先，更可能是关键源码）
- 每个工程最多读取 10 个文件，每文件最多 50000 字节
- 自动检测语言（从扩展名映射）

### 结果展示

生成完成后 4 个 Tab：

| Tab | 内容 |
|-----|------|
| **文章原文** | 每篇文章的可折叠面板：标题、URL链接、作者/日期/站点元数据标签 |
| **领域脉络** | Stage 1 输出：LLM 生成的领域知识结构 |
| **最终笔记** | Stage 2 输出：完整的深度知识笔记（主力阅读 Tab） |
| **源码参考** | 读取到的源码文件清单：工程名、相对路径、语言标签 |

支持一键复制 Markdown 和下载 `.md` 文件。

## 命令行操作

### 准备文章清单

清单是一个 JSON 文件，支持两种格式：

**格式 A：纯数组**（简单场景）
```json
[
  {
    "title": "UE5 大规模开放世界性能优化实践",
    "url": "https://zhuanlan.zhihu.com/p/123456789"
  },
  {
    "title": "深入理解 GAS 游戏技能系统架构设计",
    "url": "https://www.example.com/gas-architecture"
  }
]
```

**格式 B：对象（带本地工程路径）**
```json
{
  "articles": [
    {
      "title": "Lyra 框架 GAS 集成分析",
      "url": "https://example.com/lyra-gas"
    },
    {
      "title": "UE5 Gameplay Ability System 源码剖析",
      "url": "https://example.com/gas-source"
    }
  ],
  "code_projects": [
    {
      "label": "Lyra项目",
      "path": "D:/UnrealProjects/LyraStarterGame",
      "file_patterns": ["*.h", "*.cpp"]
    },
    {
      "label": "Unreal引擎",
      "path": "D:/UE5/Engine/Source/Runtime/GameplayAbilities",
      "file_patterns": ["*.h", "*.cpp"]
    }
  ]
}
```

清单字段说明：

| 字段 | 层级 | 必填 | 说明 |
|------|------|------|------|
| `articles` | 顶层 | 是 | 文章列表 |
| `articles[].url` | 文章 | 是 | 文章 URL（http/https） |
| `articles[].title` | 文章 | 否 | 文章标题（影响 slug 和标注） |
| `code_projects` | 顶层 | 否 | 本地工程列表 |
| `code_projects[].label` | 工程 | 是 | 工程名称（用于标注） |
| `code_projects[].path` | 工程 | 是 | 本地绝对路径 |
| `code_projects[].file_patterns` | 工程 | 否 | 文件 glob 列表，默认代码文件 |

### 运行命令

```powershell
# 基础用法（清单 + 两个必填 prompt）
tools\article_washing.cmd --manifest output\my_articles.json ^
  --context-prompt "这些文章是关于 UE GAS 技能系统的" ^
  --refinement-prompt "请深入解析核心概念和架构设计"

# 指定输出风格
tools\article_washing.cmd --manifest output\my_articles.json ^
  --context-prompt "..." ^
  --refinement-prompt "..." ^
  --style deep

# 调大 token 预算（适合多篇文章深度处理）
tools\article_washing.cmd --manifest output\my_articles.json ^
  --context-prompt "..." ^
  --refinement-prompt "..." ^
  --max-tokens 32768 --timeout 1800

# 指定输出目录
tools\article_washing.cmd --manifest output\my_articles.json ^
  --context-prompt "..." ^
  --refinement-prompt "..." ^
  --output-dir output\my_washed_notes
```

### 全部参数

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--manifest` | 是 | - | 文章清单 JSON 文件路径 |
| `--context-prompt` | 是 | - | Stage 1 上下文提示 |
| `--refinement-prompt` | 是 | - | Stage 2 深化提示 |
| `--code-projects` | 否 | - | CLI 传入工程路径 JSON（覆盖清单中的） |
| `--style` | 否 | `deep` | 输出风格：`deep`/`concise`/`comprehensive` |
| `--output-dir` | 否 | `output/article_washing` | 输出目录 |
| `--timeout` | 否 | `900` | API 超时（秒） |
| `--max-tokens` | 否 | `16384` | 最大输出 token |
| `--api-base` | 否 | `http://127.0.0.1:8080/api/v1` | 后端地址 |

### 进度输出

脚本以 JSON Lines 格式输出进度，方便管道处理和日志记录：

```json
{"stage": "request", "slug": "UE5-GAS", "articles": 3, "code_projects": 1}
{"stage": "done", "slug": "UE5-GAS", "notes_chars": 28456, "sources": 3, "code_files": 8}
```

## Prompt 编写指南

### Stage 1: 上下文提示 (context_prompt)

**作用**：告诉 AI "这些文章是关于什么的"，让 AI 建立正确的领域认知框架。

**编写要点**：
- 明确领域边界（不要太大也不要太小）
- 列出你关心的维度（概念、架构、流程、关系等）
- 可以指定信息来源的权重（"重点参考 A 文章，B 和 C 作为补充"）

**示例**：

```
好的 context_prompt:
"这些文章讨论了 Unreal Engine 中 Gameplay Ability System (GAS) 的设计与实现。
请重点关注：1.GAS 的核心概念（GameplayAbility、GameplayEffect、AttributeSet）
2.技能激活和预测流程 3.网络同步机制 4.与 GameplayTags 的集成
5.Lyra 项目中对 GAS 的封装和扩展模式"

差的 context_prompt:
"UE GAS"  ← 太简略，AI 不知道你想关注什么
```

### Stage 2: 深化提示 (refinement_prompt)

**作用**：告诉 AI "怎么深挖这些内容"，定义输出的结构和深度。

**编写要点**：
- 指定输出维度和优先级
- 要求具体的技术细节（类名、函数、配置项）
- 如果有源码，要求对照分析
- 可以指定输出结构偏好

**示例**：

```
好的 refinement_prompt:
"请深入解析 GAS 的以下方面：
1. AbilitySystemComponent 的核心职责和关键方法，标注对应的源码文件和行号
2. GameplayEffect 的 Modifier 计算流程：从 Attribute 修改到最终的数值变化
3. GameplayTag 在技能激活条件、效果应用、冷却管理中的具体使用方式
4. Lyra 中 LyraAbilitySystemComponent 相比基类做了哪些扩展，为什么
5. 列出 5 个常见 GAS 使用陷阱及解决方案

要求每个技术点都包含：是什么 → 为什么这样设计 → 源码位置 → 实际例子"

差的 refinement_prompt:
"写详细一点"  ← 没有给出具体方向和标准
```

### 风格选择

| 风格 | 适用场景 | 特点 |
|------|----------|------|
| `deep`（深度学习） | 技术深入分析 | 保留细节、因果关系、设计动机、工程实践 |
| `concise`（精简） | 快速了解 | 提取核心要点，去除重复冗余 |
| `comprehensive`（全面） | 参考资料 | 不遗漏细节，保持完整性 |

## 输出结构

详见 [docs/output-convention.md](./output-convention.md#赛博洗稿输出)。

## 排错指南

### trafilatura 提取失败

```
症状: "Failed to extract content from https://..."
原因: 网站可能反爬、需要 JS 渲染、或内容在 iframe 中
解决:
  1. 检查 URL 是否可以直接在浏览器访问
  2. 尝试用浏览器打开后手动复制内容到文本框
  3. 对于需要 JS 渲染的页面，考虑后续升级到 crawl4ai
```

### OpenCode CLI 调用失败

```
症状: "External service error from OpenCode CLI"
原因: OpenCode CLI 未安装、未登录、或路径不对
解决:
  1. 检查 OPENCODE_CLI_PATH 环境变量
  2. 在终端直接运行 opencode --version 确认可用
  3. 检查超时设置是否足够（长文章可能需要 --timeout 1800）
```

### 本地工程读取不到文件

```
症状: code_files 返回空
原因: 工程路径不存在、没有匹配的文件、或路径权限不足
解决:
  1. 确认路径是绝对路径且存在
  2. 检查 file_patterns 是否匹配目标文件
  3. 确认路径不包含在排除目录列表中（如 Build, Intermediate 等）
```

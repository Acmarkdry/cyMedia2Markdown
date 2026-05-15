# 输出约定

## 视频笔记输出

每个视频的最终产物写入本机 `AI-Media2Doc\output\<视频标题>\`。
分布式 CPU worker 完成后，会把同一份目录同步到 `_queue\artifacts\<job_id>\output\<视频标题>\`，供其他机器拉取或核对。

```text
status.json                      # 处理状态
transcript.json                  # 完整转写（含时间戳）
transcript.srt                   # SRT 字幕文件
opencode_prompt.md               # 发送给 OpenCode 的 prompt
notes_raw.md                     # OpenCode 原始输出
notes.md                         # 最终精炼笔记
notes.html                       # HTML 版本
screenshots/                     # 截图文件
backend_video_notes_quality.json # 质量检查结果
```

`notes_raw.md` 保留 OpenCode 原始输出；`notes.md` 经过质量检查和收尾处理。
`backend_video_notes_quality.json` 记录生成质量指标（章节数、截图数、字符数等）。

## 赛博洗稿输出

每个批次写入 `AI-Media2Doc\output\article_washing\<slug>\`。

```text
notes.md              # Stage 2 最终精炼笔记
domain_summary.md     # Stage 1 领域知识脉络
sources.json          # 各篇文章提取结果和要点分析
code_files.json       # 读取的源码文件清单（如有）
stage1_prompt.md      # Stage 1 prompt（可复现调试）
stage2_prompt.md      # Stage 2 prompt（可复现调试）
```

`sources.json` 格式：
```json
[
  {
    "url": "https://example.com/article",
    "title": "文章标题",
    "extraction_method": "trafilatura",
    "key_points": "LLM 生成的要点分析",
    "metadata": {
      "author": "作者",
      "date": "2024-01-01",
      "sitename": "example.com"
    }
  }
]
```

## 缓存目录

### 后端缓存 (`backend/local_storage/`)

| 子目录 | 用途 |
|--------|------|
| `media/` | URL 下载或上传后的本机媒体缓存 |
| `uploads/` | 上传临时文件 |
| `screenshots/` | 后端截图缓存 |
| `logs/` | 后端服务日志 |

### 队列缓存 (`_queue/`)

| 子目录 | 用途 |
|--------|------|
| `jobs/` | 每个视频一个任务 JSON |
| `artifacts/` | prepare/opencode 跨机交换产物 |
| `logs/` | worker 命令日志和任务事件日志 |
| `work/manifests/` | worker 自动拆出的单视频 manifest |

这些目录均不提交到 Git。

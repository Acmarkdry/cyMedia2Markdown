---
name: media2markdown-video-notes
description: Use this skill when Codex needs to operate the local Media2Markdown / AI-Media2Doc workflow for converting local videos, audio files, Bilibili URLs, or Bilibili multi-part playlists into high-density Markdown/HTML study notes with transcript files and screenshots. Trigger on requests to batch-process videos, crawl/extract Bilibili course playlists, generate or regenerate video learning notes, use Codex CLI instead of OpenAI API, run local faster-whisper ASR, retry failed video note jobs, validate screenshot references, or maintain the video-to-notes backend workflow in D:\StudyReference\m2m_queue\AI-Media2Doc.
---

# Media2Markdown Video Notes

## Project Context

Use the local project at:

`D:\StudyReference\m2m_queue\AI-Media2Doc`

Prefer the role-specific project environments:

`.\.venv-cpu\Scripts\python.exe`

`.\.venv-gpu\Scripts\python.exe`

Treat this project-local skill as the canonical editable copy for repository maintenance. If a future Codex session needs automatic discovery outside this repo, sync this folder to `$CODEX_HOME\skills\media2markdown-video-notes`.

The durable workflow is:

1. Build a manifest for videos.
2. Prepare media and transcripts with `tools\batch_video_notes.cmd --skip-codex`.
3. Generate notes in parallel with `tools\parallel_regenerate.cmd`.
4. Validate `notes.md`, `notes.html`, screenshots, and quality files.
5. Commit/push only source and docs changes, not `output/`.

Do not convert Codex/ChatGPT login state into API keys. Use Codex CLI only through the local command flow already implemented by the repo.

## Manifest Rules

Create task manifests under `output/` unless the user asks for a tracked manifest. `output/` is normally ignored, so it is safe for task-specific video lists.

For Bilibili multi-part videos, use `yt-dlp` flat metadata first, then create one manifest item per page:

```json
[
  {
    "source_id": "BVxxxx_p01",
    "output_name": "课程名 p01 分集标题",
    "title": "完整标题 p01 分集标题",
    "url": "https://www.bilibili.com/video/BVxxxx?p=1"
  }
]
```

Keep folder names human-readable. Do not use only BV ids when the video title is known.

## Preparation Stage

Use preparation mode to download media, run local ASR, and write prompts without invoking Codex:

```powershell
tools\batch_video_notes.cmd `
  --manifest output\my_manifest.json `
  --poll-interval 20 `
  --media-timeout 1800 `
  --skip-codex
```

For retrying one item:

```powershell
tools\batch_video_notes.cmd `
  --manifest output\my_manifest.json `
  --only BVxxxx_p12 `
  --poll-interval 20 `
  --media-timeout 1800 `
  --skip-codex
```

ASR has a GPU lock. Let it run serially unless the user explicitly wants to risk multiple ASR workers. It is fine to run Codex note generation in parallel while ASR continues preparing later videos, as long as write targets do not overlap.

## Codex Generation Stage

For a prepared batch, prefer `assemble` merging to avoid repeated chunk boilerplate:

```powershell
tools\parallel_regenerate.cmd `
  --manifest output\my_manifest.json `
  --jobs 3 `
  --merge-strategy assemble `
  --no-clear-screenshots `
  --llm-timeout 3600
```

When only some videos are ready, launch by `source_id`:

```powershell
tools\parallel_regenerate.cmd `
  --slug BVxxxx_p01 `
  --slug BVxxxx_p02 `
  --jobs 2 `
  --merge-strategy assemble `
  --no-clear-screenshots `
  --llm-timeout 3600 `
  --log-dir output
```

Use waves for large courses:

- Keep ASR preparation in one serial process.
- Run 2-4 Codex jobs at a time depending on stability.
- If a process exits with `1073807364`, treat it as interrupted; retry the affected slug. Existing chunk files are reused automatically unless `--force-chunks` is passed.

## Monitoring

Inspect launcher and child logs under `output/`:

```powershell
Get-ChildItem output -Filter 'parallel_launcher_*.log' |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 5 Name,Length,LastWriteTime
```

Tail the relevant child log:

```powershell
Get-Content -Encoding UTF8 'output\parallel_<video>_<stamp>.log' -Tail 80
```

Expected child stages include `chunk-start`, `chunk-done`, `merge-assemble`, and `done`.

## Validation

After generation, run an independent validation over the target `source_id`s. Check all of these:

- `transcript.json` exists.
- `notes.md` exists.
- `notes.html` exists.
- `backend_video_notes_quality.json` exists and `quality.passed` is true.
- No `#image[` remains in `notes.md`.
- No Markdown image alt is purely numeric, because `![270](...)` can be interpreted as image sizing by the app.
- Every `screenshots/...jpg` reference exists.
- Screenshot count matches Markdown image references.

Use this pattern and adapt `ids`:

```powershell
@'
from pathlib import Path
import json, re
ids = {f"BVxxxx_p{i:02d}" for i in range(1, 14)}
rows, problems = [], []
for d in Path("output").iterdir():
    s = d / "status.json"
    if not s.exists():
        continue
    try:
        status = json.loads(s.read_text(encoding="utf-8"))
    except Exception:
        continue
    sid = status.get("source_id")
    if sid not in ids:
        continue
    notes = d / "notes.md"
    html = d / "notes.html"
    quality_path = d / "backend_video_notes_quality.json"
    transcript = d / "transcript.json"
    for path, label in [(transcript, "transcript"), (notes, "notes"), (html, "html"), (quality_path, "quality")]:
        if not path.exists():
            problems.append((sid, "missing", label))
    quality = {}
    if quality_path.exists():
        quality = (json.loads(quality_path.read_text(encoding="utf-8")).get("quality") or {})
        if quality.get("passed") is not True:
            problems.append((sid, "quality-failed", quality.get("problems")))
    refs = []
    if notes.exists():
        text = notes.read_text(encoding="utf-8", errors="replace")
        if "#image[" in text:
            problems.append((sid, "unfinalized-image-marker"))
        for m in re.finditer(r"!\[([^\]]*)\]\((screenshots/[^)]+)\)", text):
            alt, rel = m.group(1).strip(), m.group(2)
            refs.append(rel)
            if re.fullmatch(r"\d+", alt):
                problems.append((sid, "numeric-alt", alt))
            if not (d / rel).exists():
                problems.append((sid, "missing-screenshot", rel))
    shots = len(list((d / "screenshots").glob("*.jpg"))) if (d / "screenshots").exists() else 0
    rows.append((sid, d.name, quality.get("chars"), quality.get("image_markers"), len(refs), shots))
for row in sorted(rows):
    print(row)
print("TOTAL", len(rows), "problems", problems)
'@ | .\.venv-cpu\Scripts\python.exe -
```

## Troubleshooting

- `HTTP Error 400` during media download: retry the affected slug with `batch_video_notes.py --only ... --skip-codex`.
- Interrupted generation or exit code `1073807364`: retry the affected slug with `launch_parallel_regeneration.py`; cached chunks should resume.
- Missing screenshot files: rerun the affected slug without `--no-clear-screenshots` only if stale screenshots are suspected. Otherwise keep `--no-clear-screenshots` to avoid destroying useful outputs.
- Codex CLI/network failures: keep prompts and chunk outputs; retry only failed slugs, not the whole batch.
- Long videos: expect chunked generation. Do not replace `assemble` with final Codex merge unless the user explicitly wants a more synthesized but slower merge.

## Reporting

Report completion with:

- Number of videos processed and passed.
- Output directory root and folder naming.
- Total note characters and screenshot count.
- Any retries or failures handled.
- Git commit/push status if source files were changed.

Do not final-answer while relevant `python` or `codex.exe exec` jobs for the requested batch are still running.

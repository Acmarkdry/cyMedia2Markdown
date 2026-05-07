# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import check_storage_layout as layout  # noqa: E402


def make_layout(root: Path) -> tuple[Path, Path]:
    project = root / "AI-Media2Doc"
    queue = root / "_queue"
    for child in ["backend", "frontend", "tools"]:
        (project / child).mkdir(parents=True)
    for child in layout.QUEUE_CHILDREN:
        (queue / child).mkdir(parents=True)
    return project, queue


def write_job(queue: Path, state: str = "done") -> Path:
    job = {
        "job_id": "BVtest_p01",
        "state": state,
        "slug": "第一讲",
        "video": {"slug": "第一讲"},
        "paths": {
            "artifact_dir": str(queue.parent / "artifacts" / "BVtest_p01"),
            "artifact_output": str(queue.parent / "artifacts" / "BVtest_p01" / "output" / "第一讲"),
            "artifact_media": str(queue.parent / "artifacts" / "BVtest_p01" / "media" / "video.mp4"),
            "video_filename": "video.mp4",
        },
    }
    path = queue / "jobs" / "BVtest_p01.json"
    path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class StorageLayoutTests(unittest.TestCase):
    def test_reports_and_repairs_stale_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project, queue = make_layout(Path(temp))
            job_path = write_job(queue)

            report = layout.build_report(project, queue)
            self.assertTrue(report["ok"], report["errors"])
            self.assertEqual(len(report["stale_job_paths"]), 1)

            self.assertTrue(layout.repair_job_paths(queue, job_path, include_running=False))
            repaired = json.loads(job_path.read_text(encoding="utf-8"))
            self.assertEqual(Path(repaired["paths"]["artifact_dir"]).resolve(strict=False), (queue / "artifacts" / "BVtest_p01").resolve(strict=False))
            self.assertEqual(
                Path(repaired["paths"]["artifact_media"]).resolve(strict=False),
                (queue / "artifacts" / "BVtest_p01" / "media" / "video.mp4").resolve(strict=False),
            )

            clean = layout.build_report(project, queue)
            self.assertEqual(clean["stale_job_paths"], [])

    def test_running_jobs_are_not_repaired_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, queue = make_layout(Path(temp))
            job_path = write_job(queue, state="codex_running")

            self.assertFalse(layout.repair_job_paths(queue, job_path, include_running=False))
            stale = json.loads(job_path.read_text(encoding="utf-8"))
            self.assertIn(str(queue.parent / "artifacts"), stale["paths"]["artifact_dir"])

            self.assertTrue(layout.repair_job_paths(queue, job_path, include_running=True))
            repaired = json.loads(job_path.read_text(encoding="utf-8"))
            self.assertEqual(Path(repaired["paths"]["artifact_dir"]).resolve(strict=False), (queue / "artifacts" / "BVtest_p01").resolve(strict=False))

    def test_legacy_sibling_logs_directory_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project, queue = make_layout(Path(temp))
            (Path(temp) / "logs").mkdir()

            report = layout.build_report(project, queue)
            self.assertFalse(report["ok"])
            self.assertTrue(any(item["code"] == "legacy-share-child" for item in report["errors"]))


if __name__ == "__main__":
    unittest.main()

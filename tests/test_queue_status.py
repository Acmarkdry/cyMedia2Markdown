# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from routers import queue  # noqa: E402


class QueueStatusTests(unittest.TestCase):
    def test_sort_index_handles_bilibili_part_suffix(self) -> None:
        self.assertEqual(queue.extract_sort_index({"source_id": "BVxxxx_p09"}), 9)
        self.assertEqual(queue.extract_sort_index({"job_id": "course-p12"}), 12)
        self.assertEqual(queue.extract_sort_index({"slug": "no-part"}), 999999)

    def test_normalize_job_marks_expired_lease_and_builds_steps(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            queue_root = Path(temp)
            (queue_root / "logs").mkdir()
            (queue_root / "logs" / "job_p01.jsonl").write_text(
                json.dumps({"event": "claimed", "stage": "prepare", "time": "2026-01-01T00:00:00Z"}) + "\n",
                encoding="utf-8",
            )
            job = {
                "job_id": "job_p01",
                "state": "prepare_running",
                "source_id": "BVxxx_p01",
                "slug": "第一讲",
                "video": {"title": "第一讲", "url": "https://example.com"},
                "attempts": {"prepare": 1},
                "lease_until": time.time() - 10,
                "lease_until_iso": "2026-01-01T00:00:00Z",
                "history": [{"event": "claimed", "stage": "prepare", "owner": "gpu", "time": "t"}],
            }
            normalized = queue.normalize_job(queue_root, job)
        self.assertTrue(normalized["lease_expired"])
        self.assertEqual(normalized["sort_index"], 1)
        self.assertEqual(normalized["steps"][1]["status"], "running")
        self.assertEqual(len(normalized["recent_events"]), 1)

    def test_state_summary_has_stable_labels(self) -> None:
        summary = queue.state_summary([{"state": "queued"}, {"state": "done"}, {"state": "done"}])
        counts = {item["state"]: item["count"] for item in summary}
        self.assertEqual(counts["queued"], 1)
        self.assertEqual(counts["done"], 2)
        self.assertIn("prepare_failed", counts)

    def test_runtime_contract_exposes_unified_worker_commands(self) -> None:
        contract = queue.runtime_contract(Path(r"D:\StudyReference\m2m_queue\_queue"))
        self.assertEqual(contract["required_python"], "3.12.x")
        self.assertIn("start_worker.ps1 -Role cpu", contract["commands"]["start_cpu"])
        self.assertIn("start_worker.ps1 -Role gpu", contract["commands"]["start_gpu"])


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import distributed_video_notes as dvn  # noqa: E402


def worker_args(**overrides):
    values = {
        "max_attempts": 3,
        "ignore_max_attempts": False,
        "lease_seconds": 60,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class DistributedQueueTests(unittest.TestCase):
    def test_enqueue_claim_release_and_finish_opencode(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            queue_root = root / "queue"
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "videos": [
                            {
                                "source_id": "BVtest_p01",
                                "title": "第一讲",
                                "url": "https://example.com/video",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            dvn.enqueue(argparse.Namespace(queue_root=queue_root, manifest=manifest, replace=False))
            job_file = queue_root / "jobs" / "BVtest_p01.json"
            self.assertTrue(job_file.exists())

            prepared = dvn.claim_job(queue_root, "prepare", "gpu-worker", worker_args())
            self.assertIsNotNone(prepared)
            self.assertEqual(prepared["state"], "prepare_running")
            dvn.release_dry_run_claim(queue_root, "BVtest_p01", "prepare", "gpu-worker")
            self.assertEqual(dvn.load_job(job_file)["state"], "queued")

            prepared = dvn.claim_job(queue_root, "prepare", "gpu-worker", worker_args())
            dvn.finish_job(queue_root, "BVtest_p01", "prepare", "gpu-worker", True, queue_root / "logs" / "p.log", 0)
            self.assertEqual(dvn.load_job(job_file)["state"], "prepared")

            claimed = dvn.claim_job(queue_root, "opencode", "cpu-worker", worker_args())
            self.assertIsNotNone(claimed)
            dvn.finish_job(queue_root, "BVtest_p01", "opencode", "cpu-worker", False, queue_root / "logs" / "c.log", 1, "boom")
            failed = dvn.load_job(job_file)
            self.assertEqual(failed["state"], "opencode_failed")
            self.assertEqual(failed["last_error"]["message"], "boom")

    def test_finish_job_normalizes_legacy_artifact_path_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            queue_root = root / "_queue"
            job_dir = queue_root / "jobs"
            job_dir.mkdir(parents=True)
            job_file = job_dir / "BVtest_p01.json"
            job_file.write_text(
                json.dumps(
                    {
                        "job_id": "BVtest_p01",
                        "state": "opencode_running",
                        "owner": "cpu-worker",
                        "video": {"slug": "第一讲"},
                        "paths": {
                            "artifact_dir": str(root / "artifacts" / "BVtest_p01"),
                            "artifact_output": str(root / "artifacts" / "BVtest_p01" / "output" / "第一讲"),
                            "artifact_media": str(root / "artifacts" / "BVtest_p01" / "media" / "video.mp4"),
                            "video_filename": "video.mp4",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            dvn.finish_job(
                queue_root,
                "BVtest_p01",
                "opencode",
                "cpu-worker",
                True,
                queue_root / "logs" / "c.log",
                0,
                paths={"artifact_output": str(queue_root / "artifacts" / "BVtest_p01" / "output" / "第一讲")},
            )

            finished = dvn.load_job(job_file)
            self.assertEqual(Path(finished["paths"]["artifact_dir"]), queue_root / "artifacts" / "BVtest_p01")
            self.assertEqual(Path(finished["paths"]["artifact_media"]), queue_root / "artifacts" / "BVtest_p01" / "media" / "video.mp4")

    def test_artifact_roundtrip_and_opencode_output_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            queue_root = root / "queue"
            slug = "第一讲"
            out = project / "output" / slug
            media = project / "backend" / "local_storage" / "media"
            out.mkdir(parents=True)
            media.mkdir(parents=True)
            (media / "video.mp4").write_bytes(b"video")
            (out / "status.json").write_text(json.dumps({"media": {"video_filename": "video.mp4"}}), encoding="utf-8")
            (out / "transcript.json").write_text("{}", encoding="utf-8")
            (out / "transcript.srt").write_text("1\n", encoding="utf-8")
            (out / "opencode_prompt.md").write_text("prompt", encoding="utf-8")
            job = {"job_id": "job1", "video": {"slug": slug}}

            paths = dvn.publish_prepared_artifact(project, queue_root, job)
            self.assertTrue(Path(paths["artifact_media"]).exists())

            imported = root / "imported"
            dvn.import_prepared_artifact(imported, queue_root, job)
            self.assertTrue((imported / "output" / slug / "status.json").exists())
            self.assertTrue((imported / "backend" / "local_storage" / "media" / "video.mp4").exists())

            generated = imported / "output" / slug
            (generated / "notes.md").write_text("note", encoding="utf-8")
            (generated / "notes.html").write_text("<p>note</p>", encoding="utf-8")
            (generated / "backend_video_notes_quality.json").write_text(
                json.dumps({"quality": {"passed": True}}),
                encoding="utf-8",
            )
            ok, reason = dvn.opencode_output_ok(imported, slug)
            self.assertTrue(ok, reason)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from video_manifest import load_manifest, safe_output_name, select_videos  # noqa: E402


class VideoManifestTests(unittest.TestCase):
    def test_safe_output_name_removes_windows_path_chars(self) -> None:
        name = safe_output_name('A/B:C*D?"E<>|', "fallback")
        self.assertEqual(name, "A B C D E")

    def test_load_manifest_normalizes_and_deduplicates_slugs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "videos": [
                            {"title": "同名课程", "url": "https://www.bilibili.com/video/BVabc123/"},
                            {"title": "同名课程", "url": "https://example.com/watch?id=2", "source_id": "manual"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            videos = load_manifest(manifest)
        self.assertEqual(videos[0]["source_id"], "BVabc123")
        self.assertEqual(videos[0]["slug"], "同名课程")
        self.assertEqual(videos[1]["slug"], "同名课程-2")

    def test_jsonl_comments_and_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / "manifest.jsonl"
            manifest.write_text(
                "\n".join(
                    [
                        "# comment",
                        '{"source_id":"p01","title":"第一讲","url":"https://example.com/1"}',
                        '{"source_id":"p02","title":"第二讲","url":"https://example.com/2"}',
                    ]
                ),
                encoding="utf-8",
            )
            videos = load_manifest(manifest)
        selected = select_videos(videos, start_at="p02")
        self.assertEqual([video["source_id"] for video in selected], ["p02"])


if __name__ == "__main__":
    unittest.main()

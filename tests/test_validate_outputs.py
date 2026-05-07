# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import validate_video_outputs as validator  # noqa: E402


def write_valid_output(root: Path, slug: str = "第一讲") -> Path:
    out = root / slug
    (out / "screenshots").mkdir(parents=True)
    (out / "status.json").write_text(json.dumps({"source_id": "BVtest_p01", "slug": slug}), encoding="utf-8")
    (out / "transcript.json").write_text("{}", encoding="utf-8")
    (out / "notes.md").write_text("正文\n![视频截图 00:01](screenshots/000001.jpg)\n", encoding="utf-8")
    (out / "notes.html").write_text("<p>正文</p>", encoding="utf-8")
    (out / "backend_video_notes_quality.json").write_text(json.dumps({"quality": {"passed": True}}), encoding="utf-8")
    (out / "screenshots" / "000001.jpg").write_bytes(b"jpg")
    return out


class ValidateOutputsTests(unittest.TestCase):
    def test_valid_output_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output_root = Path(temp) / "output"
            write_valid_output(output_root)
            report = validator.build_report(output_root, set(), set())
        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(len(report["checked"]), 1)

    def test_detects_unfinalized_marker_numeric_alt_and_missing_screenshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output_root = Path(temp) / "output"
            out = write_valid_output(output_root)
            (out / "notes.md").write_text("#image[12]\n![123](screenshots/missing.jpg)\n", encoding="utf-8")
            report = validator.build_report(output_root, set(), set())
        codes = {problem["code"] for problem in report["problems"]}
        self.assertIn("unfinalized-image-marker", codes)
        self.assertIn("numeric-image-alt", codes)
        self.assertIn("missing-screenshot", codes)

    def test_can_filter_by_source_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output_root = Path(temp) / "output"
            write_valid_output(output_root, "第一讲")
            other = write_valid_output(output_root, "第二讲")
            (other / "status.json").write_text(json.dumps({"source_id": "other", "slug": "第二讲"}), encoding="utf-8")
            report = validator.build_report(output_root, set(), {"BVtest_p01"})
        self.assertEqual(len(report["checked"]), 1)
        self.assertIn("第一讲", report["checked"][0])


if __name__ == "__main__":
    unittest.main()

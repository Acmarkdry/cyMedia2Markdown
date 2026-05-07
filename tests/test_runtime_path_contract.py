# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import batch_video_notes  # noqa: E402
import launch_parallel_regeneration  # noqa: E402


class RuntimePathContractTests(unittest.TestCase):
    def test_ffmpeg_uses_explicit_environment_path_without_legacy_venv(self) -> None:
        with patch.dict(os.environ, {"M2M_FFMPEG": r"C:\tools\ffmpeg.exe"}, clear=False):
            with patch.object(batch_video_notes.subprocess, "check_output", side_effect=AssertionError("legacy subprocess used")):
                self.assertEqual(batch_video_notes.get_ffmpeg(ROOT), r"C:\tools\ffmpeg.exe")

    def test_ffmpeg_resolves_from_active_python_environment(self) -> None:
        fake_imageio = types.SimpleNamespace(get_ffmpeg_exe=lambda: r"C:\active-python\ffmpeg.exe")
        with patch.dict(os.environ, {"M2M_FFMPEG": "", "IMAGEIO_FFMPEG_EXE": ""}, clear=False):
            with patch.dict(sys.modules, {"imageio_ffmpeg": fake_imageio}):
                with patch.object(batch_video_notes.subprocess, "check_output", side_effect=AssertionError("legacy subprocess used")):
                    self.assertEqual(batch_video_notes.get_ffmpeg(ROOT), r"C:\active-python\ffmpeg.exe")

    def test_parallel_regeneration_prefers_project_local_cpu_python(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            python = project / ".venv-cpu" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")

            with patch.object(launch_parallel_regeneration, "ROOT", project):
                with patch.dict(os.environ, {"M2M_PYTHON": ""}, clear=False):
                    self.assertEqual(launch_parallel_regeneration.default_python(), python)

    def test_parallel_child_command_never_defaults_to_backend_venv(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            python = project / ".venv-cpu" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
            args = argparse.Namespace(
                python=None,
                llm_timeout=3600,
                chunk_minutes=12,
                max_tokens=None,
                remarks="",
                quality_retry=True,
                clear_screenshots=True,
                force_chunks=False,
                cache_after_epoch=None,
                merge_group_size=3,
                merge_strategy="assemble",
            )

            with patch.object(launch_parallel_regeneration, "ROOT", project):
                with patch.dict(os.environ, {"M2M_PYTHON": ""}, clear=False):
                    command = launch_parallel_regeneration.build_child_command({"selector": "p04"}, args)

        self.assertEqual(Path(command[0]), python)
        self.assertNotIn("backend", str(command[0]).lower())
        legacy_fragment = "backend" + r"\.venv"
        self.assertNotIn(legacy_fragment, str(command[0]).lower())


if __name__ == "__main__":
    unittest.main()

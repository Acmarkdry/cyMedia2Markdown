# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import m2m_doctor  # noqa: E402


def make_project(root: Path) -> Path:
    project = root / "AI-Media2Doc"
    for name in ["backend", "frontend", "tools"]:
        (project / name).mkdir(parents=True)
    python = project / ".venv-cpu" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    return project


def fake_run_ok(command: list[str], timeout: int = 12):
    if command[0].endswith("python.exe"):
        return True, "Python 3.12.10"
    if command[0] in {"node", "npm"}:
        return True, "ok"
    if "opencode" in command[0]:
        return True, "opencode-cli test"
    return True, "ok"


class DoctorContractTests(unittest.TestCase):
    def test_cpu_report_accepts_separate_queue_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = make_project(root)
            queue_root = root / "_queue"
            queue_root.mkdir()
            args = argparse.Namespace(role="cpu", project_root=project, queue_root=queue_root, api_base=m2m_doctor.DEFAULT_API_BASE)
            with patch.object(m2m_doctor, "run_ok", side_effect=fake_run_ok), patch.object(m2m_doctor.shutil, "which", return_value="opencode"):
                report = m2m_doctor.build_report(args)
        self.assertTrue(report["ok"], report["errors"])
        self.assertIn(".venv-cpu", report["python"]["selected"])

    def test_cpu_report_rejects_project_inside_queue_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            queue_root = Path(temp) / "share"
            project = make_project(queue_root)
            args = argparse.Namespace(role="cpu", project_root=project, queue_root=queue_root, api_base=m2m_doctor.DEFAULT_API_BASE)
            with patch.object(m2m_doctor, "run_ok", side_effect=fake_run_ok), patch.object(m2m_doctor.shutil, "which", return_value="opencode"):
                report = m2m_doctor.build_report(args)
        self.assertFalse(report["ok"])
        self.assertTrue(any("project_root must not be inside queue_root" in error for error in report["errors"]))

    def test_gpu_report_rejects_unc_project_root_before_health(self) -> None:
        args = argparse.Namespace(
            role="gpu",
            project_root=Path(r"\\MINIPC\m2m_queue\AI-Media2Doc"),
            queue_root=Path(r"\\MINIPC\m2m_queue\_queue"),
            api_base=m2m_doctor.DEFAULT_API_BASE,
        )
        with patch.object(m2m_doctor, "run_ok", side_effect=fake_run_ok), patch.object(m2m_doctor, "check_health", return_value=(True, "ok")):
            report = m2m_doctor.build_report(args)
        self.assertFalse(report["ok"])
        self.assertTrue(any("SMB/UNC" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()

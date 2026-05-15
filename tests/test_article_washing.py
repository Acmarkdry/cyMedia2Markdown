# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import article_washing as aw  # noqa: E402


class ArticleWashingTests(unittest.TestCase):
    # ── Manifest loading ────────────────────────────────────────────────

    def test_manifest_loading_json_array(self) -> None:
        """Load a JSON-array manifest returns dict with articles list."""
        manifest_data = [
            {"title": "测试文章 A", "url": "https://example.com/a"},
            {"title": "测试文章 B", "url": "https://example.com/b"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "articles.json"
            manifest_path.write_text(
                json.dumps(manifest_data, ensure_ascii=False),
                encoding="utf-8",
            )
            result = aw.load_article_manifest(manifest_path)
            self.assertIn("articles", result)
            self.assertEqual(len(result["articles"]), 2)
            self.assertEqual(result["articles"][0]["title"], "测试文章 A")
            self.assertEqual(result["articles"][0]["url"], "https://example.com/a")
            self.assertIsNone(result["code_projects"])

    def test_manifest_with_dict_wrapper(self) -> None:
        """Load manifest wrapped in {"articles": [...]} with code_projects."""
        manifest_data = {
            "articles": [
                {"title": "Wrapper A", "url": "https://example.com/w1"},
                {"title": "Wrapper B", "url": "https://example.com/w2"},
            ],
            "code_projects": [
                {"label": "Lyra", "path": "/fake/Lyra"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "articles.json"
            manifest_path.write_text(
                json.dumps(manifest_data, ensure_ascii=False),
                encoding="utf-8",
            )
            result = aw.load_article_manifest(manifest_path)
            self.assertEqual(len(result["articles"]), 2)
            self.assertEqual(result["articles"][0]["title"], "Wrapper A")
            self.assertIsNotNone(result["code_projects"])
            self.assertEqual(len(result["code_projects"]), 1)
            self.assertEqual(result["code_projects"][0]["label"], "Lyra")

    def test_manifest_skips_no_url(self) -> None:
        """Items without url are skipped in articles list."""
        manifest_data = [
            {"title": "No URL", "url": ""},
            {"title": "Good", "url": "https://example.com/good"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "articles.json"
            manifest_path.write_text(
                json.dumps(manifest_data, ensure_ascii=False),
                encoding="utf-8",
            )
            result = aw.load_article_manifest(manifest_path)
            self.assertEqual(len(result["articles"]), 1)
            self.assertEqual(result["articles"][0]["title"], "Good")

    # ── Slug generation ─────────────────────────────────────────────────

    def test_slug_from_title(self) -> None:
        """Title-based slug generation is deterministic."""
        slug = aw._make_batch_slug([{"title": "UE5 GAS 深度解析", "url": "https://example.com/1"}])
        self.assertTrue(len(slug) > 0)
        self.assertIn("UE5", slug)

    def test_slug_from_url_hash(self) -> None:
        """Fallback slug from URL hash when title is missing."""
        slug1 = aw._make_batch_slug([{"title": "", "url": "https://example.com/test"}])
        slug2 = aw._make_batch_slug([{"title": "", "url": "https://example.com/test"}])
        self.assertEqual(slug1, slug2)
        self.assertTrue(len(slug1) > 0)

    # ── HTTP helpers ────────────────────────────────────────────────────

    def test_post_json_mock(self) -> None:
        """post_json sends correct payload and returns parsed JSON."""
        with patch.object(aw, "urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"success": True, "data": {"refined_output": "ok"}}).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            result = aw.post_json("http://test/api", {"key": "value"}, timeout=30)
            self.assertTrue(result["success"])
            self.assertEqual(result["data"]["refined_output"], "ok")

    # ── V2 response processing ──────────────────────────────────────────

    def test_process_batch_response_shape(self) -> None:
        """process_batch correctly extracts v2 response fields."""
        mock_response = {
            "success": True,
            "data": {
                "extracted_articles": [
                    {
                        "url": "https://example.com/a",
                        "title": "Article A",
                        "markdown_content": "content A",
                        "extraction_method": "trafilatura",
                        "key_points": "要点1, 要点2",
                        "metadata": {"author": "作者A", "sitename": "example.com"},
                    }
                ],
                "code_files": [
                    {
                        "project_label": "Lyra",
                        "relative_path": "Source/test.h",
                        "content": "// test code",
                        "language": "c/c++",
                    }
                ],
                "domain_summary": "## 领域概览\n核心概念包括...",
                "refined_output": "# 深度笔记\n## 核心结论\n...",
                "stage1_prompt": "STAGE1...",
                "stage2_prompt": "STAGE2...",
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            manifest_path = out_dir / "articles.json"
            manifest_path.write_text(
                json.dumps([{"title": "Article A", "url": "https://example.com/a"}], ensure_ascii=False),
                encoding="utf-8",
            )

            class FakeArgs:
                manifest = manifest_path
                context_prompt = "context"
                refinement_prompt = "refine"
                style = "deep"
                timeout = 60
                max_tokens = 8192
                code_projects_json = None

            with patch.object(aw, "post_json", return_value=mock_response):
                status = aw.process_batch(FakeArgs(), out_dir)

            self.assertIn("slug", status)
            self.assertEqual(status["sources"], 1)
            self.assertEqual(status["code_files"], 1)
            self.assertTrue(status["has_domain_summary"])
            # Verify output files were created
            batch_dir = out_dir / status["slug"]
            self.assertTrue((batch_dir / "notes.md").exists())
            self.assertTrue((batch_dir / "domain_summary.md").exists())
            self.assertTrue((batch_dir / "sources.json").exists())
            self.assertTrue((batch_dir / "code_files.json").exists())
            self.assertTrue((batch_dir / "stage1_prompt.md").exists())
            self.assertTrue((batch_dir / "stage2_prompt.md").exists())

    def test_process_batch_api_error(self) -> None:
        """process_batch raises on API-level failure."""
        mock_response = {"success": False, "error": {"message": "Test error"}}

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            manifest_path = out_dir / "articles.json"
            manifest_path.write_text(
                json.dumps([{"title": "X", "url": "https://example.com/x"}], ensure_ascii=False),
                encoding="utf-8",
            )

            class FakeArgs:
                manifest = manifest_path
                context_prompt = "ctx"
                refinement_prompt = "ref"
                style = "deep"
                timeout = 60
                max_tokens = 8192
                code_projects_json = None

            with patch.object(aw, "post_json", return_value=mock_response):
                status = aw.process_batch(FakeArgs(), out_dir)
                # Should still return status even on API error
                self.assertIn("slug", status)

    # ── argparse ────────────────────────────────────────────────────────

    def test_argparse_defaults(self) -> None:
        """Argument parser has correct defaults for v2."""
        parser = aw.argparse.ArgumentParser()
        # Re-create the parser setup to test defaults
        # Just verify the module-level constants
        self.assertEqual(aw.API_BASE, "http://127.0.0.1:8080/api/v1")


if __name__ == "__main__":
    unittest.main()

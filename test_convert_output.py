#!/usr/bin/env python3
"""Tests for convert_output.py"""

import tempfile
import unittest
from pathlib import Path

from convert_output import find_markdown_file, build_pandoc_command


class TestFindMarkdownFile(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.doc_dir = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_finds_markdown_matching_pdf_name(self):
        """Should find markdown file that matches the original PDF name."""
        (self.doc_dir / "mybook.pdf").touch()
        (self.doc_dir / "mybook.md").write_text("# Content")

        result = find_markdown_file(self.doc_dir)
        self.assertEqual(result.name, "mybook.md")

    def test_ignores_page_markdown_files(self):
        """Should not return page_XXX.md files."""
        (self.doc_dir / "mybook.pdf").touch()
        (self.doc_dir / "mybook.md").write_text("# Content")
        md_dir = self.doc_dir / "2_markdown"
        md_dir.mkdir()
        (md_dir / "page_001.md").write_text("Page 1")

        result = find_markdown_file(self.doc_dir)
        self.assertEqual(result.name, "mybook.md")

    def test_raises_if_no_markdown(self):
        """Should raise if no concatenated markdown found."""
        (self.doc_dir / "mybook.pdf").touch()

        with self.assertRaises(FileNotFoundError):
            find_markdown_file(self.doc_dir)


class TestBuildPandocCommand(unittest.TestCase):
    def test_pdf_command(self):
        """PDF command should use tectonic for unicode support."""
        md_file = Path("/tmp/book.md")
        cmd = build_pandoc_command(md_file, "pdf")

        self.assertIn("pandoc", cmd[0])
        self.assertIn(str(md_file), cmd)
        self.assertIn("--pdf-engine=tectonic", cmd)
        self.assertTrue(any(c.endswith(".pdf") for c in cmd))

    def test_epub_command(self):
        """EPUB command should use mathml for formulas."""
        md_file = Path("/tmp/book.md")
        cmd = build_pandoc_command(md_file, "epub")

        self.assertIn("pandoc", cmd[0])
        self.assertIn(str(md_file), cmd)
        self.assertIn("--mathml", cmd)
        self.assertTrue(any(c.endswith(".epub") for c in cmd))

    def test_output_file_naming(self):
        """Output files should have _output suffix to avoid overwriting original."""
        md_file = Path("/docs/mybook.md")

        pdf_cmd = build_pandoc_command(md_file, "pdf")
        epub_cmd = build_pandoc_command(md_file, "epub")

        self.assertTrue(any("mybook_output.pdf" in c for c in pdf_cmd))
        self.assertTrue(any("mybook_output.epub" in c for c in epub_cmd))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for concatenate_md.py"""

import tempfile
import unittest
from pathlib import Path

from concatenate_md import concatenate_pages, validate_pages


class TestValidatePages(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.doc_dir = Path(self.tmpdir.name)
        self.pdf_dir = self.doc_dir / "1_original_pdf_pages"
        self.md_dir = self.doc_dir / "2_markdown"
        self.pdf_dir.mkdir(parents=True)
        self.md_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_valid_continuous_pages(self):
        """All pages present and continuous should pass."""
        for i in range(1, 4):
            (self.pdf_dir / f"page_{i:03d}.pdf").touch()
            (self.md_dir / f"page_{i:03d}.md").write_text(f"Content for page {i}")

        errors = validate_pages(self.doc_dir)
        self.assertEqual(errors, [])

    def test_missing_page_in_sequence(self):
        """Gap in page numbers should be detected."""
        for i in [1, 2, 4]:  # Missing page 3
            (self.pdf_dir / f"page_{i:03d}.pdf").touch()
            (self.md_dir / f"page_{i:03d}.md").write_text(f"Content for page {i}")

        errors = validate_pages(self.doc_dir)
        self.assertTrue(any("3" in e and "missing" in e.lower() for e in errors))

    def test_missing_markdown_file(self):
        """PDF without corresponding markdown should be detected."""
        for i in range(1, 4):
            (self.pdf_dir / f"page_{i:03d}.pdf").touch()
        # Only create markdown for pages 1 and 2
        (self.md_dir / "page_001.md").write_text("Content 1")
        (self.md_dir / "page_002.md").write_text("Content 2")

        errors = validate_pages(self.doc_dir)
        self.assertTrue(any("page_003" in e for e in errors))

    def test_empty_markdown_file(self):
        """Empty markdown file should be detected."""
        for i in range(1, 3):
            (self.pdf_dir / f"page_{i:03d}.pdf").touch()
        (self.md_dir / "page_001.md").write_text("Content 1")
        (self.md_dir / "page_002.md").write_text("")  # Empty

        errors = validate_pages(self.doc_dir)
        self.assertTrue(any("page_002" in e and "empty" in e.lower() for e in errors))

    def test_whitespace_only_markdown_file(self):
        """Whitespace-only markdown file should be detected as empty."""
        (self.pdf_dir / "page_001.pdf").touch()
        (self.md_dir / "page_001.md").write_text("   \n\t\n  ")

        errors = validate_pages(self.doc_dir)
        self.assertTrue(any("empty" in e.lower() for e in errors))

    def test_no_pdf_pages(self):
        """No PDF pages should be detected."""
        errors = validate_pages(self.doc_dir)
        self.assertTrue(any("no pdf" in e.lower() or "no page" in e.lower() for e in errors))


class TestConcatenatePages(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.doc_dir = Path(self.tmpdir.name)
        self.pdf_dir = self.doc_dir / "1_original_pdf_pages"
        self.md_dir = self.doc_dir / "2_markdown"
        self.pdf_dir.mkdir(parents=True)
        self.md_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_concatenate_skips_on_validation_error(self):
        """concatenate_pages should not create output if validation fails."""
        # Create PDF but no markdown
        (self.pdf_dir / "page_001.pdf").touch()
        (self.doc_dir / "test.pdf").touch()  # Original PDF for naming

        concatenate_pages(self.doc_dir)

        # Output should not exist
        self.assertFalse((self.doc_dir / "test.md").exists())

    def test_concatenate_works_when_valid(self):
        """concatenate_pages should create output when validation passes."""
        for i in range(1, 3):
            (self.pdf_dir / f"page_{i:03d}.pdf").touch()
            (self.md_dir / f"page_{i:03d}.md").write_text(f"Content {i}")
        (self.doc_dir / "mybook.pdf").touch()

        concatenate_pages(self.doc_dir)

        output = self.doc_dir / "mybook.md"
        self.assertTrue(output.exists())
        self.assertIn("Content 1", output.read_text())
        self.assertIn("Content 2", output.read_text())


if __name__ == "__main__":
    unittest.main()

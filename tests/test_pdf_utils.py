#!/usr/bin/env python3
"""Tests for pdf_utils.py"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pdf_conversion.pdf_utils import get_output_dir


class TestGetOutputDir(unittest.TestCase):
    def test_default_documents_dir(self):
        """Without env var, should return ./documents relative to script."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove PDFCONVERT_OUTPUT_DIR if present
            os.environ.pop("PDFCONVERT_OUTPUT_DIR", None)
            result = get_output_dir()
            self.assertEqual(result.name, "documents")

    def test_env_var_overrides_default(self):
        """PDFCONVERT_OUTPUT_DIR should override the default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PDFCONVERT_OUTPUT_DIR": tmpdir}):
                result = get_output_dir()
                self.assertEqual(result, Path(tmpdir))

    def test_env_var_expands_user(self):
        """~ in PDFCONVERT_OUTPUT_DIR should be expanded."""
        with patch.dict(os.environ, {"PDFCONVERT_OUTPUT_DIR": "~/my_docs"}):
            result = get_output_dir()
            self.assertTrue(str(result).startswith(str(Path.home())))
            self.assertTrue(str(result).endswith("my_docs"))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for pdf_utils.py"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pdf_conversion.pdf_utils import get_output_dir


class TestGetOutputDir(unittest.TestCase):
    def test_missing_env_var_raises_error(self):
        """Without env var, should raise an error."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("PDFCONVERT_OUTPUT_DIR", None)
            with self.assertRaises(SystemExit) as ctx:
                get_output_dir()
            self.assertEqual(ctx.exception.code, 1)

    def test_env_var_sets_output_dir(self):
        """PDFCONVERT_OUTPUT_DIR sets the output directory."""
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

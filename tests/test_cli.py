"""Tests for cli.py progress bar handling."""

import io
import unittest

from pdf_conversion.cli import (
    print_progress_line,
    finish_progress,
    _reset_progress_state,
)


class TestProgressLine(unittest.TestCase):
    """Test that progress bars reuse the same line."""

    def setUp(self):
        _reset_progress_state()

    def test_progress_bar_uses_carriage_return(self):
        """Progress bar lines should use \\r and no trailing newline."""
        buf = io.StringIO()

        # Simulate tqdm progress output
        print_progress_line(" 10%|█         | 1/10 [00:01<00:09]", file=buf)

        output = buf.getvalue()
        self.assertTrue(output.startswith("\r"), "Should start with carriage return")
        self.assertFalse(output.endswith("\n"), "Should not end with newline")

    def test_regular_message_gets_newline(self):
        """Non-progress messages should print normally with newline."""
        buf = io.StringIO()

        print_progress_line("Loading models...", file=buf)

        output = buf.getvalue()
        self.assertTrue(output.endswith("\n"), "Should end with newline")

    def test_message_after_progress_clears_line(self):
        """Regular message after progress should start on new line."""
        buf = io.StringIO()

        # First a progress bar
        print_progress_line(" 100%|██████████| 10/10 [00:10<00:00]", file=buf)
        # Then a regular message
        print_progress_line("Done processing", file=buf)

        output = buf.getvalue()
        # Should have newline before the "Done" message
        self.assertIn("\nDone processing\n", output)

    def test_finish_progress_adds_newline_after_progress(self):
        """finish_progress() should add newline if last output was progress."""
        buf = io.StringIO()

        print_progress_line(" 50%|█████     | 5/10 [00:05<00:05]", file=buf)
        finish_progress(file=buf)

        output = buf.getvalue()
        self.assertTrue(output.endswith("\n"), "Should end with newline after finish")

    def test_finish_progress_noop_after_regular_message(self):
        """finish_progress() should be a no-op after regular message."""
        buf = io.StringIO()

        print_progress_line("Regular message", file=buf)
        before = buf.getvalue()
        finish_progress(file=buf)
        after = buf.getvalue()

        self.assertEqual(before, after, "Should not add extra newline")

    def test_multiple_progress_updates_overwrite(self):
        """Sequential progress updates should all use carriage return."""
        buf = io.StringIO()

        print_progress_line(" 10%|█         | 1/10", file=buf)
        print_progress_line(" 50%|█████     | 5/10", file=buf)
        print_progress_line("100%|██████████| 10/10", file=buf)

        output = buf.getvalue()
        # Should have 3 carriage returns and no newlines
        self.assertEqual(output.count("\r"), 3)
        self.assertNotIn("\n", output)


if __name__ == "__main__":
    unittest.main()

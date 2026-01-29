"""Tests for claude_api module."""

import json
import unittest
from unittest.mock import patch, MagicMock

from claude_api import run, run_with_image, ClaudeResponse, ClaudeError


class TestClaudeResponse(unittest.TestCase):
    """Test ClaudeResponse dataclass."""

    def test_from_json_complete(self):
        """Parse complete JSON response."""
        data = {
            "result": "Hello, world!",
            "session_id": "abc-123",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
            },
        }
        response = ClaudeResponse.from_json(data)

        self.assertEqual(response.result, "Hello, world!")
        self.assertEqual(response.session_id, "abc-123")
        self.assertEqual(response.input_tokens, 100)
        self.assertEqual(response.output_tokens, 50)
        self.assertEqual(response.raw, data)

    def test_from_json_missing_fields(self):
        """Handle missing optional fields gracefully."""
        data = {}
        response = ClaudeResponse.from_json(data)

        self.assertEqual(response.result, "")
        self.assertEqual(response.session_id, "")
        self.assertEqual(response.input_tokens, 0)
        self.assertEqual(response.output_tokens, 0)


class TestRun(unittest.TestCase):
    """Test the run() function."""

    @patch("claude_api.subprocess.run")
    def test_basic_prompt(self, mock_run):
        """Basic prompt returns parsed response."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "result": "4",
                "session_id": "sess-1",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }),
            stderr="",
        )

        response = run("What is 2+2?")

        self.assertEqual(response.result, "4")
        self.assertEqual(response.session_id, "sess-1")

        # Check command was built correctly
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[:2], ["claude", "-p"])
        self.assertIn("--output-format", cmd)
        self.assertIn("json", cmd)

    @patch("claude_api.subprocess.run")
    def test_allowed_tools(self, mock_run):
        """allowed_tools parameter adds --allowedTools flag."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"result": "ok"}),
        )

        run("test", allowed_tools=["Read", "Bash", "Edit"])

        cmd = mock_run.call_args[0][0]
        self.assertIn("--allowedTools", cmd)
        idx = cmd.index("--allowedTools")
        self.assertEqual(cmd[idx + 1], "Read,Bash,Edit")

    @patch("claude_api.subprocess.run")
    def test_model_parameter(self, mock_run):
        """model parameter adds --model flag."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"result": "ok"}),
        )

        run("test", model="haiku")

        cmd = mock_run.call_args[0][0]
        self.assertIn("--model", cmd)
        idx = cmd.index("--model")
        self.assertEqual(cmd[idx + 1], "haiku")

    @patch("claude_api.subprocess.run")
    def test_system_prompt(self, mock_run):
        """system_prompt parameter adds --system-prompt flag."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"result": "ok"}),
        )

        run("test", system_prompt="You are a helpful assistant")

        cmd = mock_run.call_args[0][0]
        self.assertIn("--system-prompt", cmd)

    @patch("claude_api.subprocess.run")
    def test_nonzero_exit_raises(self, mock_run):
        """Non-zero exit code raises ClaudeError."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error: something went wrong",
        )

        with self.assertRaises(ClaudeError) as ctx:
            run("test")

        self.assertEqual(ctx.exception.returncode, 1)
        self.assertIn("something went wrong", ctx.exception.stderr)

    @patch("claude_api.subprocess.run")
    def test_invalid_json_raises(self, mock_run):
        """Invalid JSON output raises ClaudeError."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="not valid json",
            stderr="",
        )

        with self.assertRaises(ClaudeError) as ctx:
            run("test")

        self.assertIn("Failed to parse", str(ctx.exception))

    @patch("claude_api.subprocess.run")
    def test_timeout_raises(self, mock_run):
        """Timeout raises ClaudeError."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=30)

        with self.assertRaises(ClaudeError) as ctx:
            run("test", timeout=30)

        self.assertIn("timed out", str(ctx.exception))


class TestRunWithImage(unittest.TestCase):
    """Test the run_with_image() function."""

    @patch("claude_api.subprocess.run")
    def test_image_path_in_prompt(self, mock_run):
        """Image path is included in the prompt."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"result": "markdown content"}),
        )

        run_with_image("Convert to markdown", "/path/to/image.png")

        cmd = mock_run.call_args[0][0]
        prompt = cmd[2]  # -p is at index 1, prompt at index 2
        self.assertIn("/path/to/image.png", prompt)
        self.assertIn("Convert to markdown", prompt)

    @patch("claude_api.subprocess.run")
    def test_read_tool_allowed_by_default(self, mock_run):
        """Read tool is allowed by default for image processing."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"result": "ok"}),
        )

        run_with_image("test", "/path/to/image.png")

        cmd = mock_run.call_args[0][0]
        self.assertIn("--allowedTools", cmd)
        idx = cmd.index("--allowedTools")
        self.assertIn("Read", cmd[idx + 1])


if __name__ == "__main__":
    unittest.main()

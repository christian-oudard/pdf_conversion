"""Simple API for invoking Claude Code as a subprocess.

Example usage:
    from claude_api import run, run_with_image

    # Simple prompt
    response = run("Explain this code", allowed_tools=["Read"])
    print(response.result)

    # With an image
    response = run_with_image(
        "Convert this page to markdown with LaTeX math",
        "page_001.png",
    )
    print(response.result)
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ClaudeError(Exception):
    """Error from Claude Code subprocess."""

    def __init__(self, message: str, stderr: str = "", returncode: int = 1, raw: dict | None = None):
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode
        self.raw = raw or {}
        self.cost_usd = self.raw.get("total_cost_usd", 0)
        self.usage = self.raw.get("usage", {})


@dataclass
class ClaudeResponse:
    """Response from Claude Code."""
    result: str
    session_id: str
    input_tokens: int
    output_tokens: int
    raw: dict

    @classmethod
    def from_json(cls, data: dict) -> "ClaudeResponse":
        usage = data.get("usage", {})
        return cls(
            result=data.get("result", ""),
            session_id=data.get("session_id", ""),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            raw=data,
        )


def run(
    prompt: str,
    *,
    allowed_tools: list[str] | None = None,
    system_prompt: str | None = None,
    append_system_prompt: str | None = None,
    model: str | None = None,
    cwd: Path | str | None = None,
    max_turns: int | None = None,
    timeout: float | None = None,
) -> ClaudeResponse:
    """Run Claude Code with a prompt and return the response.

    Args:
        prompt: The prompt to send to Claude.
        allowed_tools: Tools to auto-approve (e.g., ["Read", "Bash", "Edit"]).
        system_prompt: Replace the default system prompt.
        append_system_prompt: Append to the default system prompt.
        model: Model to use (e.g., "sonnet", "opus", "haiku").
        cwd: Working directory for Claude to operate in.
        max_turns: Maximum number of agentic turns.
        timeout: Timeout in seconds for the subprocess.

    Returns:
        ClaudeResponse with result text, session_id, and token usage.

    Raises:
        ClaudeError: If Claude exits with non-zero status, times out, or
            output cannot be parsed.
    """
    cmd = ["claude", "-p", prompt, "--output-format", "json"]

    if allowed_tools:
        cmd.extend(["--allowedTools", ",".join(allowed_tools)])

    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    if append_system_prompt:
        cmd.extend(["--append-system-prompt", append_system_prompt])

    if model:
        cmd.extend(["--model", model])

    if max_turns:
        cmd.extend(["--max-turns", str(max_turns)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise ClaudeError(f"Claude timed out after {timeout}s", returncode=-1) from e

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        # Not JSON - return raw output as error
        output = (result.stderr or "") + (result.stdout or "")
        raise ClaudeError(
            f"Claude exited with status {result.returncode}",
            stderr=output,
            returncode=result.returncode,
        )

    if result.returncode != 0 or data.get("is_error"):
        error_msg = data.get("result", f"Claude exited with status {result.returncode}")
        # Parse nested API error JSON if present
        if "API Error:" in error_msg:
            try:
                json_start = error_msg.index("{")
                api_error = json.loads(error_msg[json_start:])
                err = api_error.get("error", {})
                status = error_msg.split()[2]  # "API Error: 400 {...}" -> "400"
                error_msg = f"{status} {err.get('type', 'error')}: {err.get('message', 'Unknown error')} ({api_error.get('request_id', 'no request id')})"
            except (ValueError, json.JSONDecodeError):
                pass  # Keep original message
        raise ClaudeError(
            error_msg,
            stderr=result.stderr,
            returncode=result.returncode,
            raw=data,
        )

    return ClaudeResponse.from_json(data)


def run_with_image(
    prompt: str,
    image_path: Path | str,
    *,
    allowed_tools: list[str] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    cwd: Path | str | None = None,
    timeout: float | None = None,
) -> ClaudeResponse:
    """Run Claude Code with an image file.

    The image path is included in the prompt for Claude to read.

    Args:
        prompt: The prompt describing what to do with the image.
        image_path: Path to the image file.
        allowed_tools: Tools to auto-approve.
        system_prompt: Replace the default system prompt.
        model: Model to use.
        cwd: Working directory.
        timeout: Timeout in seconds.

    Returns:
        ClaudeResponse with result text and metadata.
    """
    image_path = Path(image_path).resolve()
    full_prompt = f"Read the image at {image_path}\n\n{prompt}"

    return run(
        full_prompt,
        allowed_tools=allowed_tools or ["Read"],
        system_prompt=system_prompt,
        model=model,
        cwd=cwd,
        timeout=timeout,
    )



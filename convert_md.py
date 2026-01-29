#!/usr/bin/env python3
"""Convert a PNG page to markdown using Claude.

Pipeline:
1. Always start with marker PDF conversion
2. Plan A: marker md + png → opus full review
3. Plan B: marker md + png → opus (formulas) + opus (text) → combine
4. Plan C: marker md + png → sonnet full review
5. Plan D: marker md + png → sonnet (formulas) + sonnet (text) → combine
6. Fallback: just use marker output
"""

import argparse
import sys
from pathlib import Path

from claude_runner import run, run_with_image, ClaudeError

SYSTEM_PROMPT = """\
You are a document conversion assistant. Convert scanned book pages to markdown.

Omit print artifacts:
- Page numbers at top/bottom of page
- Running headers/footers (book title, chapter title repeated on every page)
- Chapter numbers repeated in headers

Markdown format:
- # for headers
- **text** for bold, *text* for italic
- $...$ for inline math
- $$...$$ for display math (on separate lines)

LaTeX conventions:
- \\| for norm: \\|f\\|_2
- \\bar{} for conjugate: \\bar{\\gamma}
- \\mathscr{R} for script letters
- \\varepsilon not \\epsilon

Ensure that formulas are transcribed correctly, with valid mathematical logic. Especially take care with variable names, superscript, and subscript.

For blank pages, output only: <BLANK>

No code fences, no greetings, no explanations. Output ONLY the raw markdown content.
"""

# Lazy-loaded marker converter
_marker_converter = None


def get_marker_converter():
    """Lazy-load marker converter (heavy import)."""
    global _marker_converter
    if _marker_converter is None:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        _marker_converter = PdfConverter(artifact_dict=create_model_dict())
    return _marker_converter


def convert_png_with_marker(png_path: Path) -> str:
    """Convert a PNG image to markdown using marker."""
    import io
    import contextlib

    converter = get_marker_converter()
    with contextlib.redirect_stderr(io.StringIO()):
        rendered = converter(str(png_path))
    return rendered.markdown


def _is_content_filter_error(e: ClaudeError) -> bool:
    """Check if error is due to content filtering."""
    return "content filtering" in str(e).lower()


def _review_full(image_path: Path, marker_md: str, model: str) -> str:
    """Send marker md + image to Claude for full review."""
    prompt = f"""Here is OCR output from a scanned book page. Review it against the original image and correct any errors in the text or LaTeX formulas.

OCR OUTPUT:
{marker_md}"""
    return run_with_image(
        prompt,
        image_path,
        allowed_tools=["Read"],
        system_prompt=SYSTEM_PROMPT,
        model=model,
    ).result


def _review_text(image_path: Path, marker_md: str, model: str) -> str:
    """Extract corrected text only (formulas as placeholders)."""
    prompt = f"""Here is OCR output from a scanned book page. Review the TEXT only against the original image. Skip formulas - use [FORMULA] as placeholder.

OCR OUTPUT:
{marker_md}"""
    return run_with_image(
        prompt,
        image_path,
        allowed_tools=["Read"],
        system_prompt=SYSTEM_PROMPT,
        model=model,
    ).result


def _review_formulas(image_path: Path, marker_md: str, model: str) -> str:
    """Extract corrected formulas only."""
    prompt = f"""Here is OCR output from a scanned book page. Extract only the mathematical formulas, correcting any errors against the original image. Output each formula as LaTeX.

OCR OUTPUT:
{marker_md}"""
    return run_with_image(
        prompt,
        image_path,
        allowed_tools=["Read"],
        system_prompt=SYSTEM_PROMPT,
        model=model,
    ).result


def _combine(text: str, formulas: str, model: str) -> str:
    """Combine text and formulas into final markdown."""
    prompt = f"""Combine this text (with [FORMULA] placeholders) and these formulas into final markdown:

TEXT:
{text}

FORMULAS:
{formulas}"""
    return run(
        prompt,
        system_prompt=SYSTEM_PROMPT,
        model=model,
    ).result


def convert_page(
    image_path: Path,
    output_path: Path | None = None,
) -> str:
    """Convert a PNG page to markdown.

    Pipeline:
    1. Always start with marker PDF conversion
    2. Plan A: marker md + png → opus full review
    3. Plan B: marker md + png → opus (formulas) + opus (text) → combine
    4. Plan C: marker md + png → sonnet full review
    5. Plan D: marker md + png → sonnet (formulas) + sonnet (text) → combine
    6. Fallback: just use marker output

    Args:
        image_path: Path to the PNG file.
        output_path: Optional path to write markdown.

    Returns:
        The markdown content.
    """
    image_path = Path(image_path).resolve()

    # Step 1: Always start with marker
    print("  marker...", file=sys.stderr, end=" ", flush=True)
    marker_md = convert_png_with_marker(image_path)
    print("done", file=sys.stderr)

    # Try opus full review
    print("  opus...", file=sys.stderr, end=" ", flush=True)
    try:
        markdown = _review_full(image_path, marker_md, "opus")
        print("done", file=sys.stderr)
        if output_path:
            output_path.write_text(markdown)
        return markdown
    except ClaudeError as e:
        if _is_content_filter_error(e):
            print("blocked", file=sys.stderr)
        else:
            raise

    # Try opus split (text + formulas)
    print("  opus (split)...", file=sys.stderr, end=" ", flush=True)
    try:
        text = _review_text(image_path, marker_md, "opus")
        formulas = _review_formulas(image_path, marker_md, "opus")
        markdown = _combine(text, formulas, "opus")
        print("done", file=sys.stderr)
        if output_path:
            output_path.write_text(markdown)
        return markdown
    except ClaudeError as e:
        if _is_content_filter_error(e):
            print("blocked", file=sys.stderr)
        else:
            raise

    # Try sonnet full review
    print("  sonnet...", file=sys.stderr, end=" ", flush=True)
    try:
        markdown = _review_full(image_path, marker_md, "sonnet")
        print("done", file=sys.stderr)
        if output_path:
            output_path.write_text(markdown)
        return markdown
    except ClaudeError as e:
        if _is_content_filter_error(e):
            print("blocked", file=sys.stderr)
        else:
            raise

    # Try sonnet split (text + formulas)
    print("  sonnet (split)...", file=sys.stderr, end=" ", flush=True)
    try:
        text = _review_text(image_path, marker_md, "sonnet")
        formulas = _review_formulas(image_path, marker_md, "sonnet")
        markdown = _combine(text, formulas, "sonnet")
        print("done", file=sys.stderr)
        if output_path:
            output_path.write_text(markdown)
        return markdown
    except ClaudeError as e:
        if _is_content_filter_error(e):
            print("blocked", file=sys.stderr)
        else:
            raise

    # Fallback: just use marker output
    print("  (marker only)", file=sys.stderr)
    if output_path:
        output_path.write_text(marker_md)
    return marker_md


def main():
    parser = argparse.ArgumentParser(
        description="Convert a PNG page to markdown using Claude"
    )
    parser.add_argument("image", type=Path, help="PNG file to convert")
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output markdown file (default: print to stdout)"
    )

    args = parser.parse_args()

    if not args.image.exists():
        print(f"Error: File not found: {args.image}", file=sys.stderr)
        sys.exit(1)

    try:
        result = convert_page(args.image, args.output)
        if not args.output:
            print(result)
    except ClaudeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

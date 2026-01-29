#!/usr/bin/env python3
"""Convert a PNG page to markdown using Claude."""

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

No code fences, no greetings, no explanations. Output ONLY the raw markdown content.
"""


def convert_page(
    image_path: Path,
    output_path: Path | None = None,
    model: str | None = None,
    _no_fallback: bool = False,
) -> str:
    """Convert a PNG page to markdown.

    Args:
        image_path: Path to the PNG file.
        output_path: Optional path to write markdown. If None, prints to stdout.
        model: Model to use (e.g., "haiku", "sonnet").
        _no_fallback: Internal flag to prevent infinite recursion.

    Returns:
        The markdown content.
    """
    try:
        response = run_with_image(
            "Convert this scanned book page to markdown.",
            image_path,
            allowed_tools=["Read"],
            system_prompt=SYSTEM_PROMPT,
            model=model,
        )
        markdown = response.result
    except ClaudeError as e:
        # Fallback to combine pipeline if content filter blocks
        if not _no_fallback and "content filtering" in str(e).lower():
            print("Content filter triggered, using fallback pipeline...", file=sys.stderr)
            markdown = combine_conversion(image_path)
        else:
            raise

    if output_path:
        output_path.write_text(markdown)

    return markdown


def extract_text(image_path: Path, output_path: Path | None = None, model: str | None = None) -> str:
    """Extract only text from a PNG page, skipping formulas.

    Args:
        image_path: Path to the PNG file.
        output_path: Optional path to write text.
        model: Model to use (e.g., "haiku", "sonnet").

    Returns:
        The extracted text as markdown.
    """
    response = run_with_image(
        "Extract only the text from this page, skipping all mathematical formulas. Use [FORMULA] as a placeholder where formulas appear.",
        image_path,
        allowed_tools=["Read"],
        system_prompt=SYSTEM_PROMPT,
        model=model,
    )

    text = response.result

    if output_path:
        output_path.write_text(text)

    return text


def extract_formulas(image_path: Path, output_path: Path | None = None, model: str | None = None) -> str:
    """Extract only mathematical formulas from a PNG page.

    Args:
        image_path: Path to the PNG file.
        output_path: Optional path to write formulas.
        model: Model to use (e.g., "haiku", "sonnet", "opus").

    Returns:
        The extracted formulas as LaTeX.
    """
    response = run_with_image(
        "Extract only the mathematical formulas from this page. Output each formula as LaTeX, one per line.",
        image_path,
        allowed_tools=["Read"],
        system_prompt=SYSTEM_PROMPT,
        model=model,
    )

    formulas = response.result

    if output_path:
        output_path.write_text(formulas)

    return formulas


def combine_conversion(image_path: Path, output_path: Path | None = None) -> str:
    """Convert a page using multi-model pipeline.

    1. Sonnet: full conversion
    2. Opus: text-only (optional)
    3. Opus: formulas-only (optional)
    4. Opus: combine whatever we have into final output

    Args:
        image_path: Path to the PNG file.
        output_path: Optional path to write result. If None, prints to stdout.

    Returns:
        The combined markdown.
    """
    image_path = Path(image_path).resolve()
    sources = []

    # Step 1: Sonnet full conversion (may fail)
    print("Step 1: Full conversion (sonnet)...", file=sys.stderr)
    try:
        sonnet_full = convert_page(image_path, model="sonnet", _no_fallback=True)
        sources.append(f"UNRELIABLE FULL CONVERSION:\n{sonnet_full}")
    except ClaudeError as e:
        print(f"  Failed: {e}", file=sys.stderr)

    # Step 2: Opus text-only (may fail)
    print("Step 2: Text extraction (opus)...", file=sys.stderr)
    try:
        opus_text = extract_text(image_path, model="opus")
        sources.append(f"TEXT ONLY (formulas as [FORMULA]):\n{opus_text}")
    except ClaudeError as e:
        print(f"  Failed: {e}", file=sys.stderr)

    # Step 3: Opus formulas-only (may fail)
    print("Step 3: Formula extraction (opus)...", file=sys.stderr)
    try:
        opus_formulas = extract_formulas(image_path, model="opus")
        sources.append(f"FORMULAS ONLY:\n{opus_formulas}")
    except ClaudeError as e:
        print(f"  Failed: {e}", file=sys.stderr)

    # Step 4: Opus combine
    print("Step 4: Combining (opus)...", file=sys.stderr)
    sources_text = "\n\n".join(sources)
    combine_prompt = f"""Here are multiple conversion attempts of the same scanned book page:

{sources_text}

Produce the final accurate markdown. Ensure both text and mathematical formulas are correct."""

    combined = run(
        combine_prompt,
        system_prompt=SYSTEM_PROMPT,
        model="opus",
    ).result

    if output_path:
        output_path.write_text(combined)

    return combined


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
    parser.add_argument(
        "-m", "--model",
        type=str,
        help="Model to use (e.g., haiku, sonnet)"
    )
    parser.add_argument(
        "--combine",
        action="store_true",
        help="Force multi-model pipeline (for testing)"
    )

    args = parser.parse_args()

    if not args.image.exists():
        print(f"Error: File not found: {args.image}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.combine:
            result = combine_conversion(args.image, args.output)
        else:
            result = convert_page(args.image, args.output, args.model)

        if not args.output:
            print(result)
    except ClaudeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

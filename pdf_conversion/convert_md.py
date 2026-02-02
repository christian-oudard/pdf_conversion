#!/usr/bin/env python3
"""Convert PDF pages to markdown using Modal marker + Claude review.

Pipeline:
1. Run marker on full PDF via Modal (cloud GPU)
2. Split marker output by page
3. Send batches of pages to Opus for review
"""

import re
from pathlib import Path

from .claude_runner import run


def extract_output(text: str) -> str:
    """Extract content from <output> tags, or return original if no tags."""
    match = re.search(r'<output>(.*?)</output>', text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


# Load system prompt from file
_PROMPT_FILE = Path(__file__).parent / "prompts" / "review_ocr.txt"
SYSTEM_PROMPT = _PROMPT_FILE.read_text()

# Page separator pattern used by marker
PAGE_SEPARATOR = "-" * 48
PAGE_MARKER_PATTERN = re.compile(r"\{(\d+)\}" + re.escape(PAGE_SEPARATOR))


def split_marker_by_page(marker_md: str) -> list[str]:
    """Split paginated marker output into per-page chunks.

    Returns list of markdown strings, one per page (0-indexed).
    Page separators (---...) are kept at the end of each page.
    """
    # Find all page markers and their positions
    matches = list(PAGE_MARKER_PATTERN.finditer(marker_md))
    if not matches:
        return [marker_md.strip()]

    pages = []
    for i, match in enumerate(matches):
        page_id = int(match.group(1))
        start = match.end()
        # End is either next marker or end of string
        end = matches[i + 1].start() if i + 1 < len(matches) else len(marker_md)
        content = marker_md[start:end].strip()

        # Ensure pages list is long enough
        while len(pages) <= page_id:
            pages.append("")
        pages[page_id] = content

    return pages


def remove_page_separators(markdown: str) -> str:
    """Remove page separators from final output."""
    return markdown.replace(PAGE_SEPARATOR, "").strip()


def review_batch(
    image_paths: list[Path],
    marker_mds: list[str],
    model: str = "opus",
    work_dir: Path | None = None,
) -> str:
    """Send a batch of pages to Claude for review.

    Args:
        image_paths: List of PNG files for the batch.
        marker_mds: List of marker markdown for each page.
        model: Model to use for review.
        work_dir: Directory for temp files (uses image_paths[0].parent if None).

    Returns:
        Combined markdown for all pages in the batch.
    """
    import os

    # Write OCR output and image list to files to avoid command line length limits
    combined_md = "\n\n".join(marker_mds)
    if work_dir is None:
        work_dir = image_paths[0].parent if image_paths else Path.cwd()

    # Use unique filenames for parallel safety (thread id + process id)
    batch_id = f"{os.getpid()}_{id(image_paths)}"
    ocr_file = work_dir / f"_ocr_batch_{batch_id}.md"
    ocr_file.write_text(combined_md)

    images_file = work_dir / f"_images_batch_{batch_id}.txt"
    images_file.write_text("\n".join(str(p.resolve()) for p in image_paths))

    prompt = f"""Read the task files in {work_dir}:
- {ocr_file.name}: OCR output to review
- {images_file.name}: list of {len(image_paths)} image paths to read

Compare the OCR text against the original images and fix errors:
- ADD $...$ around all math variables in prose (OCR misses these) - e.g. "process z" -> "process $z$"
- Preserve paragraph structure and line breaks
- Keep content order (don't move footnotes)

Output the CORRECTED markdown - not a summary of changes."""

    try:
        return extract_output(run(
            prompt,
            allowed_tools=["Read"],
            system_prompt=SYSTEM_PROMPT,
            model=model,
        ).result)
    finally:
        # Clean up temp files
        ocr_file.unlink(missing_ok=True)
        images_file.unlink(missing_ok=True)

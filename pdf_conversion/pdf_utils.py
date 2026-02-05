"""Shared PDF utilities."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pymupdf


def get_output_dir() -> Path:
    """Get the output directory for converted documents.

    Requires PDFCONVERT_OUTPUT_DIR environment variable to be set.
    """
    import sys

    env_dir = os.environ.get("PDFCONVERT_OUTPUT_DIR")
    if not env_dir:
        print("Error: PDFCONVERT_OUTPUT_DIR environment variable not set", file=sys.stderr)
        sys.exit(1)
    return Path(env_dir).expanduser()


def find_original_pdf(doc_folder: Path) -> Path:
    """Find the original PDF in a document folder."""
    pdfs = list(doc_folder.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDF found in {doc_folder}")
    if len(pdfs) > 1:
        for pdf in pdfs:
            if pdf.stem in doc_folder.name or doc_folder.name in pdf.stem:
                return pdf
    return pdfs[0]


def parse_page_range(range_str: str, max_pages: int) -> list[int]:
    """Parse a page range string like '1-10' or '5' into a list of page numbers."""
    if '-' in range_str:
        start, end = range_str.split('-', 1)
        start = int(start)
        end = int(end) if end else max_pages
        return list(range(start, min(end, max_pages) + 1))
    else:
        return [int(range_str)]


def has_visible_text(page) -> bool:
    """Check if page has any visible (non-OCR-overlay) text."""
    text_dict = page.get_text('dict')
    for block in text_dict['blocks']:
        if block['type'] != 0:
            continue
        for line in block.get('lines', []):
            for span in line.get('spans', []):
                font = span.get('font', '')
                if font != 'GlyphLessFont':
                    return True
    return False


def get_full_page_image(page) -> dict | None:
    """Check if page has a single full-page embedded image.

    Returns the image info dict if yes, None if no.
    Criteria: >75% coverage in each dimension, no visible text on page.
    """
    rect = page.rect
    images = page.get_image_info()

    # Skip if page has visible text (not just OCR overlay)
    if has_visible_text(page):
        return None

    # Filter out tiny images (lines, icons)
    real_images = [img for img in images if img['width'] > 100 and img['height'] > 100]
    if not real_images:
        return None

    img = max(real_images, key=lambda im: im['width'] * im['height'])

    # Use transform to get actual placed size (handles rotation)
    a, b, c, d, e, f = img['transform']
    placed_w = math.sqrt(a*a + b*b)
    placed_h = math.sqrt(c*c + d*d)

    cov_w = placed_w / rect.width
    cov_h = placed_h / rect.height

    # Require >75% coverage in each dimension
    if cov_w <= 0.75 or cov_h <= 0.75:
        return None

    return img


def extract_full_page_image(doc: pymupdf.Document, page_num: int) -> tuple[bytes, str] | None:
    """Extract the full-page image from a page as raw bytes.

    Returns (image_bytes, extension) or None if not a full-page image.
    page_num is 0-indexed.
    """
    page = doc[page_num]

    img_info = get_full_page_image(page)
    if not img_info:
        return None

    # Find the matching image by dimensions
    for img in page.get_images(full=True):
        if img[2] == img_info['width'] and img[3] == img_info['height']:
            xref = img[0]
            base_image = doc.extract_image(xref)
            return base_image["image"], base_image["ext"]

    return None

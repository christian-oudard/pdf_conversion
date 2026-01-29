#!/usr/bin/env python3
"""Split double-page spread PDFs into single pages without resampling."""

import argparse
import io
import sys
from pathlib import Path

import pymupdf
from PIL import Image

from pdf_utils import extract_full_page_image


def split_image(image_bytes: bytes) -> tuple[bytes, bytes]:
    """Split an image in half horizontally, returning left and right halves as PNG bytes."""
    img = Image.open(io.BytesIO(image_bytes))
    width, height = img.size

    mid = width // 2

    left = img.crop((0, 0, mid, height))
    right = img.crop((mid, 0, width, height))

    # Save as PNG (lossless)
    left_buf = io.BytesIO()
    right_buf = io.BytesIO()
    left.save(left_buf, format="PNG")
    right.save(right_buf, format="PNG")

    return left_buf.getvalue(), right_buf.getvalue()


def create_pdf_from_images(image_list: list[bytes], output_path: Path):
    """Create a PDF from a list of image bytes, one image per page."""
    doc = pymupdf.open()

    for image_bytes in image_list:
        # Get image dimensions
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size

        # Create page matching image size (in points, 72 dpi)
        # We'll insert at 72 dpi so page size = pixel size in points
        page = doc.new_page(width=width, height=height)

        # Insert image to fill page exactly
        rect = pymupdf.Rect(0, 0, width, height)
        page.insert_image(rect, stream=image_bytes)

    doc.save(output_path, garbage=4, deflate=True, clean=True)
    doc.close()


def split_spread_pdf(input_path: Path, output_path: Path, verbose: bool = False):
    """Split a double-page spread PDF into single pages."""
    doc = pymupdf.open(input_path)
    total_pages = len(doc)

    all_images = []

    for page_num in range(total_pages):
        if verbose:
            print(f"Processing page {page_num + 1}/{total_pages}", file=sys.stderr)

        result = extract_full_page_image(doc, page_num)
        if not result:
            raise ValueError(f"Page {page_num + 1} is not a full-page image")
        image_bytes, _ = result
        left, right = split_image(image_bytes)
        all_images.append(left)
        all_images.append(right)

    doc.close()

    if verbose:
        print(f"Creating output PDF with {len(all_images)} pages", file=sys.stderr)

    create_pdf_from_images(all_images, output_path)

    if verbose:
        print(f"Wrote: {output_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Split double-page spread PDF into single pages"
    )
    parser.add_argument("input_pdf", type=Path, help="Input PDF with double-page spreads")
    parser.add_argument("output_pdf", type=Path, help="Output PDF path")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show progress")

    args = parser.parse_args()

    if not args.input_pdf.exists():
        print(f"Error: Input file not found: {args.input_pdf}", file=sys.stderr)
        sys.exit(1)

    split_spread_pdf(args.input_pdf, args.output_pdf, args.verbose)


if __name__ == "__main__":
    main()

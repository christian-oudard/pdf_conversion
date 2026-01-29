#!/usr/bin/env python3
"""Render PDF pages to PNG for markdown conversion.

For image-based pages: extracts at original resolution, splits spreads.
For rendered pages: renders at specified DPI.
"""

import argparse
import io
import sys
from pathlib import Path

import pymupdf
from PIL import Image

from pdf_utils import find_original_pdf, parse_page_range, get_full_page_image




def extract_image_bytes(doc: pymupdf.Document, page, img_info: dict) -> bytes | None:
    """Extract the full-page image as bytes."""
    for img in page.get_images(full=True):
        if img[2] == img_info['width'] and img[3] == img_info['height']:
            xref = img[0]
            base_image = doc.extract_image(xref)
            return base_image["image"]
    return None


def split_image(image_bytes: bytes) -> tuple[bytes, bytes]:
    """Split an image in half horizontally, returning left and right halves as PNG."""
    img = Image.open(io.BytesIO(image_bytes))
    width, height = img.size
    mid = width // 2

    left = img.crop((0, 0, mid, height))
    right = img.crop((mid, 0, width, height))

    left_buf = io.BytesIO()
    right_buf = io.BytesIO()
    left.save(left_buf, format="PNG")
    right.save(right_buf, format="PNG")

    return left_buf.getvalue(), right_buf.getvalue()


def to_grayscale(image_bytes: bytes) -> bytes:
    """Convert image to grayscale."""
    img = Image.open(io.BytesIO(image_bytes))
    gray = img.convert("L")
    buf = io.BytesIO()
    gray.save(buf, format="PNG")
    return buf.getvalue()


def render_page_to_bytes(page, dpi: int = 200, grayscale: bool = False) -> bytes:
    """Render a page to PNG bytes."""
    scale = dpi / 72
    mat = pymupdf.Matrix(scale, scale)
    colorspace = pymupdf.csGRAY if grayscale else None
    pix = page.get_pixmap(matrix=mat, colorspace=colorspace)
    return pix.tobytes("png")


def process_pdf(pdf_path: Path, output_dir: Path, page_nums: list[int],
                dpi: int = 200, grayscale: bool = False,
                skip_existing: bool = False, split: bool = False) -> list[Path]:
    """Process PDF pages to PNGs, extracting or rendering as appropriate.

    Returns list of output paths. Book page numbering accounts for spreads.
    """
    doc = pymupdf.open(pdf_path)
    total_pdf_pages = len(doc)

    # First pass: count total book pages to determine filename width
    book_page_count = 0
    for pdf_page_num in page_nums:
        if pdf_page_num < 1 or pdf_page_num > total_pdf_pages:
            continue
        page = doc[pdf_page_num - 1]
        img_info = get_full_page_image(page)
        if split and img_info:
            book_page_count += 2
        else:
            book_page_count += 1

    width = max(3, len(str(book_page_count)))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = []
    book_page = 1

    for pdf_page_num in page_nums:
        if pdf_page_num < 1 or pdf_page_num > total_pdf_pages:
            print(f"Warning: Page {pdf_page_num} out of range (1-{total_pdf_pages})", file=sys.stderr)
            continue

        page = doc[pdf_page_num - 1]
        img_info = get_full_page_image(page)

        if img_info:
            # Full-page image: extract at original resolution
            image_bytes = extract_image_bytes(doc, page, img_info)
            if not image_bytes:
                print(f"Warning: Could not extract image from page {pdf_page_num}", file=sys.stderr)
                continue

            if split:
                # Double-page spread: split into two
                left_bytes, right_bytes = split_image(image_bytes)

                if grayscale:
                    left_bytes = to_grayscale(left_bytes)
                    right_bytes = to_grayscale(right_bytes)

                left_path = output_dir / f"page_{book_page:0{width}d}.png"
                right_path = output_dir / f"page_{book_page + 1:0{width}d}.png"

                if not skip_existing or not left_path.exists():
                    left_path.write_bytes(left_bytes)
                    output_paths.append(left_path)
                    print(f"PDF page {pdf_page_num} (left) -> {left_path.name}")

                if not skip_existing or not right_path.exists():
                    right_path.write_bytes(right_bytes)
                    output_paths.append(right_path)
                    print(f"PDF page {pdf_page_num} (right) -> {right_path.name}")

                book_page += 2
            else:
                # Single page image
                if grayscale:
                    image_bytes = to_grayscale(image_bytes)

                output_path = output_dir / f"page_{book_page:0{width}d}.png"

                if not skip_existing or not output_path.exists():
                    output_path.write_bytes(image_bytes)
                    output_paths.append(output_path)
                    print(f"PDF page {pdf_page_num} -> {output_path.name}")

                book_page += 1
        else:
            # Rendered page: render at DPI
            png_bytes = render_page_to_bytes(page, dpi, grayscale)
            output_path = output_dir / f"page_{book_page:0{width}d}.png"

            if not skip_existing or not output_path.exists():
                output_path.write_bytes(png_bytes)
                output_paths.append(output_path)
                print(f"PDF page {pdf_page_num} (rendered) -> {output_path.name}")

            book_page += 1

    doc.close()
    return output_paths


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF pages to PNG for markdown conversion"
    )
    parser.add_argument("doc_folder", type=Path, help="Document folder containing the PDF")
    parser.add_argument(
        "page_range",
        type=str,
        nargs="?",
        default=None,
        help="Page range: '5' for single, '1-10' for range, '5-' for page 5 to end (default: all)"
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="DPI for rendering non-image pages (default: 200)"
    )
    parser.add_argument(
        "--grayscale",
        action="store_true",
        help="Convert to grayscale"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip pages that already have PNG files"
    )
    parser.add_argument(
        "--split",
        action="store_true",
        help="Split each page into left/right halves (for double-page spreads)"
    )

    args = parser.parse_args()

    if not args.doc_folder.exists():
        print(f"Error: Folder not found: {args.doc_folder}", file=sys.stderr)
        sys.exit(1)

    pdf_path = find_original_pdf(args.doc_folder)
    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    doc.close()

    if args.page_range:
        page_nums = parse_page_range(args.page_range, total_pages)
    else:
        page_nums = list(range(1, total_pages + 1))

    png_dir = args.doc_folder / "1_original_png_pages"

    process_pdf(pdf_path, png_dir, page_nums, args.dpi, args.grayscale, args.skip_existing, args.split)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Convert PDF to markdown, PDF, or EPUB.

Usage:
    pdfconvert [md|pdf|epub] <book_dir> [--pages 1-10] [--split]

Examples:
    pdfconvert documents/mybook              # default: markdown output
    pdfconvert md documents/mybook           # explicit markdown
    pdfconvert pdf documents/mybook          # PDF output
    pdfconvert epub documents/mybook         # EPUB output
"""

import argparse
import io
import re
import sys
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image

from pdf_utils import find_original_pdf, parse_page_range, get_full_page_image
from convert_md import convert_page
from output_format import build_pandoc_command
import subprocess

TARGET_DPI = 200
MAX_EXTRACT_DPI = 300


def extract_image_bytes(doc: pymupdf.Document, page, img_info: dict) -> bytes | None:
    """Extract the full-page image as bytes."""
    for img in page.get_images(full=True):
        if img[2] == img_info['width'] and img[3] == img_info['height']:
            xref = img[0]
            base_image = doc.extract_image(xref)
            return base_image["image"]
    return None


def to_grayscale(image_bytes: bytes) -> bytes:
    """Convert image to grayscale PNG."""
    img = Image.open(io.BytesIO(image_bytes))
    gray = img.convert("L")
    buf = io.BytesIO()
    gray.save(buf, format="PNG")
    return buf.getvalue()


def downsample_image(image_bytes: bytes, target_dpi: int, current_dpi: float) -> bytes:
    """Downsample image to target DPI."""
    img = Image.open(io.BytesIO(image_bytes))
    scale = target_dpi / current_dpi
    new_size = (int(img.width * scale), int(img.height * scale))
    img = img.resize(new_size, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


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


def render_page_to_bytes(page, dpi: int = TARGET_DPI) -> bytes:
    """Render a page to grayscale PNG bytes."""
    scale = dpi / 72
    mat = pymupdf.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, colorspace=pymupdf.csGRAY)
    return pix.tobytes("png")


def calculate_dpi(img_width: int, page_width_points: float) -> float:
    """Calculate effective DPI of an embedded image."""
    page_width_inches = page_width_points / 72
    return img_width / page_width_inches


def render_pages_to_temp(
    pdf_path: Path,
    page_nums: list[int],
    temp_dir: Path,
    split: bool = False,
) -> list[Path]:
    """Render PDF pages to PNGs in temp directory.

    Always grayscale. Renders at 200 DPI, or extracts and downsamples if >300 DPI.
    """
    doc = pymupdf.open(pdf_path)
    total_pdf_pages = len(doc)

    # Calculate filename width
    if split:
        max_book_page = total_pdf_pages * 2
    else:
        max_book_page = total_pdf_pages
    width = max(3, len(str(max_book_page)))

    output_paths = []

    for pdf_page_num in page_nums:
        if pdf_page_num < 1 or pdf_page_num > total_pdf_pages:
            print(f"Warning: Page {pdf_page_num} out of range (1-{total_pdf_pages})", file=sys.stderr)
            continue

        # Calculate book page number
        if split:
            book_page = (pdf_page_num - 1) * 2 + 1
        else:
            book_page = pdf_page_num

        page = doc[pdf_page_num - 1]
        img_info = get_full_page_image(page)

        if img_info:
            # Full-page image: extract and possibly downsample
            image_bytes = extract_image_bytes(doc, page, img_info)
            if not image_bytes:
                print(f"Warning: Could not extract image from page {pdf_page_num}", file=sys.stderr)
                continue

            # Check DPI and downsample if needed
            dpi = calculate_dpi(img_info['width'], page.rect.width)
            if dpi > MAX_EXTRACT_DPI:
                print(f"Page {pdf_page_num}: {dpi:.0f} DPI -> downsampling to {TARGET_DPI}", file=sys.stderr)
                image_bytes = downsample_image(image_bytes, TARGET_DPI, dpi)

            if split:
                left_bytes, right_bytes = split_image(image_bytes)
                left_bytes = to_grayscale(left_bytes)
                right_bytes = to_grayscale(right_bytes)

                left_path = temp_dir / f"page_{book_page:0{width}d}.png"
                right_path = temp_dir / f"page_{book_page + 1:0{width}d}.png"

                left_path.write_bytes(left_bytes)
                right_path.write_bytes(right_bytes)
                output_paths.extend([left_path, right_path])
                print(f"Page {pdf_page_num} -> {left_path.name}, {right_path.name}")
            else:
                image_bytes = to_grayscale(image_bytes)
                output_path = temp_dir / f"page_{book_page:0{width}d}.png"
                output_path.write_bytes(image_bytes)
                output_paths.append(output_path)
                print(f"Page {pdf_page_num} -> {output_path.name}")
        else:
            # Rendered page
            png_bytes = render_page_to_bytes(page, TARGET_DPI)
            output_path = temp_dir / f"page_{book_page:0{width}d}.png"
            output_path.write_bytes(png_bytes)
            output_paths.append(output_path)
            print(f"Page {pdf_page_num} (rendered) -> {output_path.name}")

    doc.close()
    return output_paths


def convert_pngs_to_markdown(png_paths: list[Path], temp_dir: Path) -> list[Path]:
    """Convert PNG files to markdown using Claude."""
    md_paths = []

    for png_path in png_paths:
        md_path = temp_dir / png_path.with_suffix('.md').name
        print(f"Converting {png_path.name}...", file=sys.stderr)
        convert_page(png_path, md_path)
        md_paths.append(md_path)

    return md_paths


def concatenate_markdown(md_paths: list[Path]) -> str:
    """Concatenate markdown files into a single string."""
    def page_num(p: Path) -> int:
        match = re.search(r'page_(\d+)', p.name)
        return int(match.group(1)) if match else 0

    sorted_paths = sorted(md_paths, key=page_num)

    parts = []
    for md_path in sorted_paths:
        content = md_path.read_text().strip()
        if content:
            parts.append(content)

    return "\n\n".join(parts)


def convert_markdown_to_format(md_content: str, output_path: Path, fmt: str):
    """Convert markdown content to PDF or EPUB."""
    # Write to temp file for pandoc
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(md_content)
        temp_md = Path(f.name)

    try:
        cmd = build_pandoc_command(temp_md, fmt)
        # Override output path
        cmd[3] = str(output_path)

        print(f"Converting to {fmt}...", file=sys.stderr)
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Error converting to {fmt}:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            sys.exit(1)
    finally:
        temp_md.unlink()


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF to markdown, PDF, or EPUB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "format_or_dir",
        help="Output format (md, pdf, epub) or book directory",
    )
    parser.add_argument(
        "book_dir",
        type=Path,
        nargs="?",
        help="Book directory (if format specified)",
    )
    parser.add_argument(
        "--pages",
        type=str,
        help="Page range: '5' for single, '1-10' for range, '5-' for page 5 to end",
    )
    parser.add_argument(
        "--split",
        action="store_true",
        help="Split each page into left/right halves (for double-page spreads)",
    )

    args = parser.parse_args()

    # Parse format and book_dir
    if args.format_or_dir in ('md', 'pdf', 'epub'):
        output_format = args.format_or_dir
        if not args.book_dir:
            parser.error("book_dir required when format is specified")
        book_dir = args.book_dir
    else:
        output_format = 'md'
        book_dir = Path(args.format_or_dir)

    if not book_dir.exists():
        print(f"Error: Directory not found: {book_dir}", file=sys.stderr)
        sys.exit(1)

    # Find PDF
    pdf_path = find_original_pdf(book_dir)
    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    doc.close()

    # Parse page range
    if args.pages:
        page_nums = parse_page_range(args.pages, total_pages)
    else:
        page_nums = list(range(1, total_pages + 1))

    print(f"Processing {pdf_path.name} ({len(page_nums)} pages)")

    # Determine output filename
    output_suffix = {'md': '.md', 'pdf': '_output.pdf', 'epub': '_output.epub'}[output_format]
    output_path = book_dir / (pdf_path.stem + output_suffix)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Step 1: Render pages to PNG
        print("\n=== Rendering pages ===")
        png_paths = render_pages_to_temp(pdf_path, page_nums, temp_path, args.split)

        # Step 2: Convert PNGs to markdown
        print("\n=== Converting to markdown ===")
        md_paths = convert_pngs_to_markdown(png_paths, temp_path)

        # Step 3: Concatenate markdown
        print("\n=== Concatenating ===")
        md_content = concatenate_markdown(md_paths)

        # Step 4: Output
        if output_format == 'md':
            output_path.write_text(md_content)
            print(f"\nOutput: {output_path}")
        else:
            convert_markdown_to_format(md_content, output_path, output_format)
            print(f"\nOutput: {output_path}")


if __name__ == "__main__":
    main()

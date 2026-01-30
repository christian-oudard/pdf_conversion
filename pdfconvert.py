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
from pathlib import Path

import pymupdf
from PIL import Image

from pdf_utils import find_original_pdf, parse_page_range, get_full_page_image
from convert_md import (
    convert_pdf_with_marker,
    split_marker_by_page,
    review_batch,
    remove_page_separators,
    PAGE_SEPARATOR,
)
from claude_runner import ClaudeError
from output_format import build_pandoc_command
import subprocess

TARGET_DPI = 200
BATCH_SIZE = 100
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
    redo: bool = False,
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

        # Check if output already exists before loading page
        if split:
            left_path = temp_dir / f"page_{book_page:0{width}d}.png"
            right_path = temp_dir / f"page_{book_page + 1:0{width}d}.png"
            if not redo and left_path.exists() and right_path.exists():
                output_paths.extend([left_path, right_path])
                print(f"Page {pdf_page_num} -> {left_path.name}, {right_path.name} (exists)")
                continue
        else:
            output_path = temp_dir / f"page_{book_page:0{width}d}.png"
            if not redo and output_path.exists():
                output_paths.append(output_path)
                print(f"Page {pdf_page_num} -> {output_path.name} (exists)")
                continue

        # Load page and extract/render
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
                left_path.write_bytes(left_bytes)
                right_path.write_bytes(right_bytes)
                output_paths.extend([left_path, right_path])
                print(f"Page {pdf_page_num} -> {left_path.name}, {right_path.name}")
            else:
                image_bytes = to_grayscale(image_bytes)
                output_path.write_bytes(image_bytes)
                output_paths.append(output_path)
                print(f"Page {pdf_page_num} -> {output_path.name}")
        else:
            # Rendered page (no embedded image)
            png_bytes = render_page_to_bytes(page, TARGET_DPI)
            output_path.write_bytes(png_bytes)
            output_paths.append(output_path)
            print(f"Page {pdf_page_num} (rendered) -> {output_path.name}")

    doc.close()
    return output_paths


def convert_batch_to_markdown(
    png_paths: list[Path],
    marker_pages: list[str],
    output_dir: Path,
    batch_num: int,
) -> str:
    """Convert a batch of pages using Opus review.

    Args:
        png_paths: PNG files for this batch.
        marker_pages: Marker markdown for each page.
        output_dir: Directory to cache batch output.
        batch_num: Batch number for naming.

    Returns:
        Combined markdown for the batch.
    """
    batch_path = output_dir / f"batch_{batch_num:03d}.md"

    # Check cache
    if batch_path.exists() and batch_path.stat().st_size > 0:
        print(f"  batch {batch_num} ({len(png_paths)} pages) - cached")
        return batch_path.read_text()

    print(f"  batch {batch_num} ({len(png_paths)} pages)...", end=" ", flush=True)

    try:
        result = review_batch(png_paths, marker_pages, model="opus")
        print("done")
        batch_path.write_text(result)
        return result
    except ClaudeError as e:
        if "content filtering" in str(e).lower():
            print("blocked, using marker output")
            # Fallback to marker output for this batch
            result = "\n\n".join(marker_pages)
            batch_path.write_text(result)
            return result
        raise


def concatenate_markdown(md_paths: list[Path]) -> str:
    """Concatenate markdown files into a single string."""
    def page_num(p: Path) -> int:
        match = re.search(r'page_(\d+)', p.name)
        return int(match.group(1)) if match else 0

    sorted_paths = sorted(md_paths, key=page_num)

    parts = []
    for md_path in sorted_paths:
        content = md_path.read_text().strip()
        # Skip blank pages
        if content and content != "<BLANK>":
            parts.append(content)

    return "\n\n".join(parts)


def convert_markdown_to_format(md_path: Path, output_path: Path, fmt: str):
    """Convert markdown file to PDF or EPUB.

    For PDF: generates intermediate .tex file (kept).
    For EPUB: converts directly.
    """
    if fmt == 'pdf':
        # Markdown -> LaTeX -> PDF (keep .tex)
        tex_path = output_path.with_suffix('.tex')

        print(f"Converting to LaTeX...", file=sys.stderr)
        cmd = ["pandoc", str(md_path), "-o", str(tex_path), "--standalone"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error converting to LaTeX:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            sys.exit(1)

        print(f"Converting to PDF...", file=sys.stderr)
        cmd = ["tectonic", str(tex_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=output_path.parent)
        if result.returncode != 0:
            print(f"Error converting to PDF:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            sys.exit(1)
    else:
        # EPUB: direct conversion
        cmd = build_pandoc_command(md_path, fmt)
        cmd[3] = str(output_path)

        print(f"Converting to {fmt}...", file=sys.stderr)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error converting to {fmt}:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            sys.exit(1)


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
    parser.add_argument(
        "--redo-png",
        action="store_true",
        help="Re-render PNGs even if they exist",
    )
    parser.add_argument(
        "--redo-md",
        action="store_true",
        help="Re-convert markdown even if it exists",
    )

    args = parser.parse_args()

    # Parse format and input path
    if args.format_or_dir in ('md', 'pdf', 'epub'):
        output_format = args.format_or_dir
        if not args.book_dir:
            parser.error("input path required when format is specified")
        input_path = args.book_dir
    else:
        output_format = 'md'
        input_path = Path(args.format_or_dir)

    if not input_path.exists():
        print(f"Error: Not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Working directory is documents/ in this project
    script_dir = Path(__file__).parent
    documents_dir = script_dir / "documents"
    documents_dir.mkdir(exist_ok=True)

    # Accept either a PDF file or a directory containing one
    if input_path.is_file() and input_path.suffix.lower() == '.pdf':
        source_pdf = input_path
        book_name = source_pdf.stem
    else:
        source_pdf = find_original_pdf(input_path)
        book_name = input_path.name

    # Set up working directory
    work_dir = documents_dir / book_name
    work_dir.mkdir(exist_ok=True)

    # Copy PDF to working directory if not already there
    pdf_path = work_dir / source_pdf.name
    if not pdf_path.exists():
        import shutil
        print(f"Copying {source_pdf.name} to {work_dir}/")
        shutil.copy2(source_pdf, pdf_path)
    elif pdf_path != source_pdf.resolve():
        print(f"Using existing {pdf_path.name}")

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
    output_path = work_dir / (pdf_path.stem + output_suffix)

    # Step 1: Run marker on full PDF
    print("\n=== Running marker on PDF ===")
    marker_cache = work_dir / "marker_full.md"
    if not args.redo_md and marker_cache.exists():
        print("Using cached marker output")
        marker_md = marker_cache.read_text()
    else:
        marker_md = convert_pdf_with_marker(pdf_path)
        marker_cache.write_text(marker_md)

    # Step 2: Render pages to PNG
    print("\n=== Rendering pages ===")
    png_dir = work_dir / "png"
    png_dir.mkdir(exist_ok=True)
    png_paths = render_pages_to_temp(pdf_path, page_nums, png_dir, args.split, args.redo_png)

    # Split marker output by page
    marker_pages = split_marker_by_page(marker_md)
    print(f"Split into {len(marker_pages)} pages")

    # Map PNG paths to marker pages (handle split mode)
    if args.split:
        # In split mode, we have 2 PNGs per PDF page but marker has 1 entry per PDF page
        # We need to duplicate marker content for left/right halves
        expanded_marker = []
        for mp in marker_pages:
            expanded_marker.append(mp)  # left half
            expanded_marker.append(mp)  # right half (same content, Claude will see the image)
        marker_pages = expanded_marker

    # Ensure we have marker output for each PNG
    if len(marker_pages) < len(png_paths):
        print(f"Warning: marker has {len(marker_pages)} pages but {len(png_paths)} PNGs", file=sys.stderr)
        # Pad with empty strings
        marker_pages.extend([""] * (len(png_paths) - len(marker_pages)))

    # Step 3: Convert in batches
    print(f"\n=== Converting to markdown (batch size {BATCH_SIZE}) ===")
    batches_dir = work_dir / "batches"
    batches_dir.mkdir(exist_ok=True)

    batch_outputs = []
    for i in range(0, len(png_paths), BATCH_SIZE):
        batch_pngs = png_paths[i:i + BATCH_SIZE]
        batch_markers = marker_pages[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE

        result = convert_batch_to_markdown(batch_pngs, batch_markers, batches_dir, batch_num)
        batch_outputs.append(result)

    # Step 4: Concatenate batches and remove page separators
    print("\n=== Concatenating output ===")
    combined = "\n\n".join(batch_outputs)
    # Remove page separators and blank page markers
    md_content = remove_page_separators(combined)
    md_content = md_content.replace("<BLANK>", "").strip()
    # Clean up excessive newlines
    md_content = re.sub(r"\n{3,}", "\n\n", md_content)

    md_output_path = work_dir / (pdf_path.stem + '.md')
    md_output_path.write_text(md_content)

    # Step 5: Convert to PDF/EPUB if requested
    if output_format != 'md':
        print("\n=== Converting ===")
        convert_markdown_to_format(md_output_path, output_path, output_format)
        print(f"Output: {output_path}")
    else:
        print(f"\nOutput: {md_output_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Convert PDF to markdown, PDF, or EPUB.

Usage:
    pdfconvert [md|pdf|epub] <book_dir> [--pages 1-10] [--split] [--modal] [-j N]

Examples:
    pdfconvert documents/mybook              # default: markdown output
    pdfconvert documents/mybook --modal      # use Modal cloud GPU for marker
    pdfconvert documents/mybook -j 4         # 4 parallel Claude API calls
    pdfconvert md documents/mybook           # explicit markdown
    pdfconvert pdf documents/mybook          # PDF output
    pdfconvert epub documents/mybook         # EPUB output
"""

import argparse
import io
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pymupdf
from PIL import Image

from pdf_conversion.pdf_utils import find_original_pdf, parse_page_range, get_full_page_image
from pdf_conversion.convert_md import (
    convert_pdf_with_marker,
    split_marker_by_page,
    review_batch,
    remove_page_separators,
    PAGE_SEPARATOR,
)
from pdf_conversion.claude_runner import ClaudeError
from pdf_conversion.output_format import build_pandoc_command
import subprocess

TARGET_DPI = 200
BATCH_SIZE = 5
MAX_EXTRACT_DPI = 300


def convert_pdf_with_modal(pdf_path: Path) -> str:
    """Convert PDF to markdown using marker on Modal (cloud GPU)."""
    import modal
    from pdf_conversion.modal_marker import (
        GPU, GPU_PRICES,
        RECOGNITION_BATCH_SIZE, LAYOUT_BATCH_SIZE, DETECTION_BATCH_SIZE,
        OCR_ERROR_BATCH_SIZE, EQUATION_BATCH_SIZE, TABLE_REC_BATCH_SIZE,
    )

    pdf_bytes = pdf_path.read_bytes()

    # Call the deployed class method
    try:
        MarkerConverter = modal.Cls.from_name("marker-pdf", "MarkerConverter")
    except modal.exception.NotFoundError:
        print("Error: Modal app not deployed. Run first:", file=sys.stderr)
        print("  modal deploy modal_marker.py", file=sys.stderr)
        sys.exit(1)

    batch_info = f"rec={RECOGNITION_BATCH_SIZE}, layout={LAYOUT_BATCH_SIZE}, det={DETECTION_BATCH_SIZE}, ocr_err={OCR_ERROR_BATCH_SIZE}, eq={EQUATION_BATCH_SIZE}, table={TABLE_REC_BATCH_SIZE}"
    print(f"Running marker OCR on Modal ({GPU}, {batch_info})...", flush=True)
    start = time.time()
    converter = MarkerConverter()

    # Stream progress from Modal
    result = None
    for line in converter.convert_streaming.remote_gen(pdf_bytes):
        if line.startswith("RESULT:"):
            result = line[7:]
        else:
            print(line, flush=True)

    elapsed = time.time() - start
    cost = (elapsed / 3600) * GPU_PRICES.get(GPU, 0)
    print(f"Done in {elapsed:.1f}s (~${cost:.2f})")

    if result is None:
        raise RuntimeError("No result returned from Modal")
    return result


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

    if total_pdf_pages > 999:
        raise ValueError(f"PDF has {total_pdf_pages} pages, max supported is 999")

    output_paths = []

    # Track ranges for collapsed output
    def flush_range(status: str, start: int, end: int):
        if start == end:
            print(f"Page {start} ({status})")
        else:
            print(f"Pages {start}-{end} ({status})")

    current_status: str | None = None
    range_start = 0
    range_end = 0

    for pdf_page_num in page_nums:
        if pdf_page_num < 1 or pdf_page_num > total_pdf_pages:
            print(f"Warning: Page {pdf_page_num} out of range (1-{total_pdf_pages})", file=sys.stderr)
            continue

        # Determine output paths
        if split:
            out_paths: list[Path] = [
                temp_dir / f"page_{pdf_page_num:03d}_L.png",
                temp_dir / f"page_{pdf_page_num:03d}_R.png",
            ]
        else:
            out_paths: list[Path] = [temp_dir / f"page_{pdf_page_num:03d}.png"]

        # Check if output already exists before loading page
        if not redo and all(p.exists() for p in out_paths):
            output_paths.extend(out_paths)
            status = "exists"
            if current_status == status:
                range_end = pdf_page_num
            else:
                if current_status:
                    flush_range(current_status, range_start, range_end)
                current_status = status
                range_start = range_end = pdf_page_num
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
                out_paths[0].write_bytes(to_grayscale(left_bytes))
                out_paths[1].write_bytes(to_grayscale(right_bytes))
            else:
                out_paths[0].write_bytes(to_grayscale(image_bytes))
            output_paths.extend(out_paths)
            status = "extracted"
        else:
            # Rendered page (no embedded image)
            png_bytes = render_page_to_bytes(page, TARGET_DPI)
            if split:
                left_bytes, right_bytes = split_image(png_bytes)
                out_paths[0].write_bytes(left_bytes)
                out_paths[1].write_bytes(right_bytes)
            else:
                out_paths[0].write_bytes(png_bytes)
            output_paths.extend(out_paths)
            status = "rendered"

        # Update range tracking
        if current_status == status:
            range_end = pdf_page_num
        else:
            if current_status:
                flush_range(current_status, range_start, range_end)
            current_status = status
            range_start = range_end = pdf_page_num

    # Flush final range
    if current_status:
        flush_range(current_status, range_start, range_end)

    doc.close()
    return output_paths


def convert_batch_to_markdown(
    png_paths: list[Path],
    marker_pages: list[str],
    output_dir: Path,
    start_page: int,
    end_page: int,
    redo: bool = False,
) -> str:
    """Convert a batch of pages using Opus review.

    Args:
        png_paths: PNG files for this batch.
        marker_pages: Marker markdown for each page.
        output_dir: Directory to cache batch output.
        start_page: First page number (1-indexed).
        end_page: Last page number (1-indexed).
        redo: Force re-run even if cached.

    Returns:
        Combined markdown for the batch.
    """
    batch_path = output_dir / f"pages_{start_page:03d}-{end_page:03d}.md"

    # Check cache
    if not redo and batch_path.exists() and batch_path.stat().st_size > 0:
        # Don't print here - caller handles cache reporting
        return batch_path.read_text()

    try:
        start_time = time.time()
        result = review_batch(png_paths, marker_pages, model="opus")
        elapsed = time.time() - start_time
        print(f"  pages {start_page}-{end_page} ({elapsed:.1f}s)")
        batch_path.write_text(result)
        return result
    except ClaudeError as e:
        if "content filtering" in str(e).lower():
            print(f"  pages {start_page}-{end_page} (blocked, using marker)")
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
        "--redo-marker",
        action="store_true",
        help="Re-run marker OCR even if cached",
    )
    parser.add_argument(
        "--redo-png",
        action="store_true",
        help="Re-render PNGs even if they exist",
    )
    parser.add_argument(
        "--redo-claude",
        action="store_true",
        help="Re-run Claude review even if cached",
    )
    parser.add_argument(
        "--modal",
        action="store_true",
        help="Run marker on Modal (cloud GPU) instead of locally",
    )
    parser.add_argument(
        "-j", "--jobs",
        type=int,
        default=8,
        help="Number of parallel Claude API calls (default: 8)",
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

    file_size_mb = pdf_path.stat().st_size / 1024 / 1024
    print(f"Processing {pdf_path.name} ({len(page_nums)} pages, {file_size_mb:.1f} MB)")

    # Determine output filename
    output_suffix = {'md': '.md', 'pdf': '_output.pdf', 'epub': '_output.epub'}[output_format]
    output_path = work_dir / (pdf_path.stem + output_suffix)

    # Step 1: Run marker on full PDF
    print("\n=== Running marker on PDF ===")
    marker_cache = work_dir / "marker_full.md"
    if not args.redo_marker and marker_cache.exists():
        print("Using cached marker output")
        marker_md = marker_cache.read_text()
    elif args.modal:
        marker_md = convert_pdf_with_modal(pdf_path)
        marker_cache.write_text(marker_md)
    else:
        marker_md = convert_pdf_with_marker(pdf_path)
        marker_cache.write_text(marker_md)

    # Step 2: Render pages to PNG
    print("\n=== Rendering pages ===")
    png_dir = work_dir / "png"
    png_dir.mkdir(exist_ok=True)

    # Check for mismatch between existing PNGs and --split flag
    existing_split = list(png_dir.glob("page_*_L.png"))
    existing_nosplit = [p for p in png_dir.glob("page_*.png") if "_L" not in p.name and "_R" not in p.name]
    if not args.split and existing_split:
        print(f"Error: Found {len(existing_split)} split PNGs (page_*_L.png) but --split not specified.", file=sys.stderr)
        print("Re-run with --split or delete the png/ directory to start fresh.", file=sys.stderr)
        sys.exit(1)
    if args.split and existing_nosplit:
        print(f"Error: Found {len(existing_nosplit)} non-split PNGs but --split was specified.", file=sys.stderr)
        print("Delete the png/ directory to start fresh with split mode.", file=sys.stderr)
        sys.exit(1)

    png_paths = render_pages_to_temp(pdf_path, page_nums, png_dir, args.split, args.redo_png)

    # Split marker output by page
    marker_pages = split_marker_by_page(marker_md)
    print(f"Split marker into {len(marker_pages)} pages")

    # Validate marker page count matches PDF
    if len(marker_pages) != len(page_nums):
        print(f"Warning: marker has {len(marker_pages)} pages but PDF has {len(page_nums)} pages", file=sys.stderr)

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

    # Step 3: Review with Claude (correct OCR errors)
    # In split mode, round up to even number (complete L/R pairs)
    batch_size = BATCH_SIZE + (BATCH_SIZE % 2) if args.split else BATCH_SIZE
    parallel_info = f", {args.jobs} parallel" if args.jobs > 1 else ""
    spread_info = f" = {batch_size // 2} spreads" if args.split else ""
    print(f"\n=== Reviewing with Claude ({batch_size} pages/batch{spread_info}{parallel_info}) ===")
    pages_dir = work_dir / "pages"
    pages_dir.mkdir(exist_ok=True)

    # Scan existing cached page files to find which pages are done
    cached_ranges = []  # list of (start, end, path)
    for f in sorted(pages_dir.glob("pages_*.md")):
        # Parse pages_001-008.md -> (1, 8)
        match = re.match(r"pages_(\d+)-(\d+)\.md", f.name)
        if match and f.stat().st_size > 0:
            cached_ranges.append((int(match.group(1)), int(match.group(2)), f))

    # Build list of batches: (batch_idx, start_page, end_page, cached_path_or_None)
    batches = []
    total_pages = len(png_paths)
    i = 0
    batch_idx = 0
    while i < total_pages:
        page_num = i + 1  # 1-indexed

        # Check if this page is in a cached range
        cached_hit = None
        if not args.redo_claude:
            for start, end, path in cached_ranges:
                if start == page_num:
                    cached_hit = (start, end, path)
                    break

        if cached_hit:
            start, end, path = cached_hit
            batches.append((batch_idx, start, end, path))
            i = end  # Skip to end of cached range
        else:
            end_idx = min(i + batch_size, total_pages)
            start_page = i + 1
            end_page = end_idx
            batches.append((batch_idx, start_page, end_page, None))
            i = end_idx
        batch_idx += 1

    # Separate cached vs uncached batches
    cached_batches = [(idx, s, e, p) for idx, s, e, p in batches if p is not None]
    uncached_batches = [(idx, s, e) for idx, s, e, p in batches if p is None]

    # Report cached batches
    for _, start, end, _ in cached_batches:
        print(f"  pages {start}-{end} (cached)")

    # Process uncached batches (parallel or sequential)
    batch_results = {}  # batch_idx -> result

    # Load cached results
    for idx, _, _, path in cached_batches:
        batch_results[idx] = path.read_text()

    if uncached_batches:
        def process_batch(batch_info):
            idx, start_page, end_page = batch_info
            batch_pngs = png_paths[start_page - 1:end_page]
            batch_markers = marker_pages[start_page - 1:end_page]
            result = convert_batch_to_markdown(
                batch_pngs, batch_markers, pages_dir, start_page, end_page, args.redo_claude
            )
            return idx, result

        if args.jobs > 1:
            # Parallel execution - show what we're starting
            page_ranges = [f"{s}-{e}" for _, s, e in uncached_batches]
            print(f"  starting {len(uncached_batches)} batches: {', '.join(page_ranges)}")
            with ThreadPoolExecutor(max_workers=args.jobs) as executor:
                futures = {executor.submit(process_batch, b): b for b in uncached_batches}
                for future in as_completed(futures):
                    idx, result = future.result()
                    batch_results[idx] = result
        else:
            # Sequential execution
            for batch_info in uncached_batches:
                idx, result = process_batch(batch_info)
                batch_results[idx] = result

    # Assemble outputs in order
    batch_outputs = [batch_results[idx] for idx in sorted(batch_results.keys())]

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

#!/usr/bin/env python3
"""Render PDF pages to PNG on-demand."""

import argparse
import sys
from pathlib import Path

try:
    import pymupdf
except ImportError:
    print("pymupdf not installed. Install with: uv add pymupdf")
    sys.exit(1)


def find_original_pdf(doc_folder: Path) -> Path:
    """Find the original PDF in a document folder."""
    pdfs = list(doc_folder.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDF found in {doc_folder}")
    if len(pdfs) > 1:
        # Prefer one that matches folder name
        for pdf in pdfs:
            if pdf.stem in doc_folder.name or doc_folder.name in pdf.stem:
                return pdf
        # Otherwise just take the first
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


def render_pages(pdf_path: Path, page_nums: list[int], output_dir: Path, dpi: int = 200) -> list[Path]:
    """Render PDF pages to PNG.

    Args:
        pdf_path: Path to the PDF file
        page_nums: List of 1-based page numbers
        output_dir: Directory to save PNGs
        dpi: Resolution (default: 200)

    Returns:
        List of output paths
    """
    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    width = len(str(total_pages))

    scale = dpi / 72
    mat = pymupdf.Matrix(scale, scale)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = []

    for page_num in page_nums:
        if page_num < 1 or page_num > total_pages:
            doc.close()
            raise ValueError(f"Page {page_num} out of range (1-{total_pages})")

        page = doc[page_num - 1]  # Convert to 0-based index
        pix = page.get_pixmap(matrix=mat, colorspace=pymupdf.csGRAY)

        output_path = output_dir / f"page_{page_num:0{width}d}.png"
        pix.save(output_path)
        output_paths.append(output_path)

    doc.close()
    return output_paths


def main():
    parser = argparse.ArgumentParser(
        description="Render PDF pages to PNG (200 DPI grayscale)"
    )
    parser.add_argument("doc_folder", type=Path, help="Document folder containing the PDF")
    parser.add_argument("page_range", type=str, help="Page range: '5' for single page, '1-10' for range, '5-' for page 5 to end")
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Resolution in DPI (default: 200)",
    )

    args = parser.parse_args()

    if not args.doc_folder.exists():
        print(f"Error: Folder not found: {args.doc_folder}")
        sys.exit(1)

    pdf_path = find_original_pdf(args.doc_folder)
    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    doc.close()

    page_nums = parse_page_range(args.page_range, total_pages)
    png_dir = args.doc_folder / "1_original_png_pages"

    output_paths = render_pages(pdf_path, page_nums, png_dir, args.dpi)

    for path in output_paths:
        print(path)


if __name__ == "__main__":
    main()

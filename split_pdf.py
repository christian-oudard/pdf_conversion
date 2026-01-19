#!/usr/bin/env python3
"""Split a PDF into individual page files with organized folder structure."""

import argparse
import shutil
import sys
from pathlib import Path

try:
    import pymupdf
except ImportError:
    print("pymupdf not installed. Install with: uv add pymupdf")
    sys.exit(1)


def split_pdf(input_path: Path, pages_dir: Path) -> int:
    """Split a PDF into individual page files.

    Args:
        input_path: Path to the input PDF file
        pages_dir: Directory to save individual page PDFs

    Returns:
        Number of pages extracted
    """
    pages_dir.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open(input_path)
    total_pages = len(doc)

    # Determine padding width for filenames
    width = len(str(total_pages))

    for page_num in range(total_pages):
        # Create a new PDF with just this page
        new_doc = pymupdf.open()
        new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

        # Save with zero-padded page number
        output_path = pages_dir / f"page_{page_num + 1:0{width}d}.pdf"
        new_doc.save(output_path)
        new_doc.close()

        print(f"Extracted page {page_num + 1}/{total_pages}: {output_path.name}")

    doc.close()
    return total_pages


def setup_document_folder(input_path: Path, documents_dir: Path) -> Path:
    """Create organized folder structure for a document.

    Creates:
        documents/<document_name>/
            original.pdf
            1_original_pdf_pages/
            2_markdown/
            3_latex/
            4_reconstructed_pdf_pages/
            5_original_png/
            6_reconstructed_png/

    Args:
        input_path: Path to the input PDF file
        documents_dir: Base documents directory

    Returns:
        Path to the document folder
    """
    # Use stem (filename without extension) as document name
    doc_name = input_path.stem
    # Clean up common suffixes
    for suffix in ["_text", "_ocr", "_scan"]:
        if doc_name.endswith(suffix):
            doc_name = doc_name[: -len(suffix)]

    doc_folder = documents_dir / doc_name

    # Create all workflow folders
    folders = [
        "1_original_pdf_pages",
        "2_markdown",
        "3_latex",
        "4_reconstructed_pdf_pages",
        "5_original_png",
        "6_reconstructed_png",
    ]

    doc_folder.mkdir(parents=True, exist_ok=True)
    for folder in folders:
        (doc_folder / folder).mkdir(exist_ok=True)

    # Copy original PDF with original name
    original_path = doc_folder / input_path.name
    if not original_path.exists():
        shutil.copy2(input_path, original_path)
        print(f"Copied original to: {original_path}")
    else:
        print(f"Original already exists: {original_path}")

    return doc_folder


def main():
    parser = argparse.ArgumentParser(
        description="Split a PDF into individual page files with organized folder structure"
    )
    parser.add_argument("input_pdf", type=Path, help="Path to input PDF file")
    parser.add_argument(
        "-d",
        "--documents-dir",
        type=Path,
        default=Path("documents"),
        help="Base documents directory (default: ./documents)",
    )

    args = parser.parse_args()

    if not args.input_pdf.exists():
        print(f"Error: File not found: {args.input_pdf}")
        sys.exit(1)

    print(f"Processing: {args.input_pdf}")

    # Set up folder structure
    doc_folder = setup_document_folder(args.input_pdf, args.documents_dir)
    pages_folder = doc_folder / "1_original_pdf_pages"

    print(f"Document folder: {doc_folder}")

    # Split the PDF
    count = split_pdf(args.input_pdf, pages_folder)

    print(f"\nDone! Extracted {count} pages.")
    print(f"Structure created:")
    print(f"  {doc_folder}/")
    print(f"    {args.input_pdf.name}")
    print(f"    1_original_pdf_pages/ ({count} files)")
    print(f"    2_markdown/")
    print(f"    3_latex/")
    print(f"    4_reconstructed_pdf_pages/")
    print(f"    5_original_png/")
    print(f"    6_reconstructed_png/")


if __name__ == "__main__":
    main()

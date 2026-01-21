#!/usr/bin/env python3
"""Extract text from PDF pages to .txt files."""

import sys
from pathlib import Path
import pymupdf


def extract_text_from_pdfs(book_dir: Path):
    """Extract text from all PDF pages in a book directory."""
    pdf_dir = book_dir / "1_original_pdf_pages"
    txt_dir = book_dir / "3_text"

    if not pdf_dir.exists():
        print(f"PDF directory not found: {pdf_dir}")
        return

    txt_dir.mkdir(exist_ok=True)

    pdf_files = sorted(pdf_dir.glob("page_*.pdf"))
    print(f"Found {len(pdf_files)} PDF files")

    for pdf_path in pdf_files:
        txt_path = txt_dir / pdf_path.name.replace(".pdf", ".txt")

        if txt_path.exists():
            print(f"Skipping {pdf_path.name} (already exists)")
            continue

        try:
            doc = pymupdf.open(pdf_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()

            txt_path.write_text(text.strip())
            print(f"Extracted {pdf_path.name} -> {txt_path.name}")
        except Exception as e:
            print(f"Error extracting {pdf_path.name}: {e}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_text.py <book_directory>")
        print("Example: python extract_text.py 'documents/Portfolio Selection - Harry M. Markowitz'")
        sys.exit(1)

    book_dir = Path(sys.argv[1])
    if not book_dir.exists():
        print(f"Directory not found: {book_dir}")
        sys.exit(1)

    extract_text_from_pdfs(book_dir)


if __name__ == "__main__":
    main()

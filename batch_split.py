#!/usr/bin/env python3
"""Batch split PDFs from specified directories."""

import sys
from pathlib import Path

# Add the script directory to handle imports
sys.path.insert(0, str(Path(__file__).parent))

from split_pdf import split_pdf, setup_document_folder


def batch_split(source_dirs: list[Path], documents_dir: Path):
    """Split all PDFs in source directories."""
    for source_dir in source_dirs:
        if not source_dir.exists():
            print(f"Directory not found: {source_dir}")
            continue

        pdfs = sorted(source_dir.glob("*.pdf"))
        print(f"\n=== Processing {source_dir.name}: {len(pdfs)} PDFs ===\n")

        for pdf_path in pdfs:
            # Check if already processed
            doc_name = pdf_path.stem
            for suffix in ["_text", "_ocr", "_scan"]:
                if doc_name.endswith(suffix):
                    doc_name = doc_name[: -len(suffix)]

            pages_dir = documents_dir / doc_name / "1_original_pdf_pages"
            if pages_dir.exists() and any(pages_dir.glob("*.pdf")):
                print(f"SKIP (already split): {pdf_path.name}")
                continue

            print(f"Processing: {pdf_path.name}")
            try:
                doc_folder = setup_document_folder(pdf_path, documents_dir)
                pages_folder = doc_folder / "1_original_pdf_pages"
                count = split_pdf(pdf_path, pages_folder)
                print(f"  -> {count} pages\n")
            except Exception as e:
                print(f"  ERROR: {e}\n")


if __name__ == "__main__":
    base = Path("/home/christian/files/library")
    docs_dir = Path("/home/christian/files/library/pdf_conversion/documents")

    source_dirs = [
        base / "finance",
        base / "mathematics",
    ]

    batch_split(source_dirs, docs_dir)

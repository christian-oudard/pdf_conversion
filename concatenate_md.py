#!/usr/bin/env python3
"""Concatenate all markdown page files into a single document."""

import argparse
import re
from pathlib import Path


def find_document_dir() -> Path:
    """Find the document directory (assumes single document in documents/)."""
    docs = Path("documents")
    subdirs = [d for d in docs.iterdir() if d.is_dir()]
    if len(subdirs) == 1:
        return subdirs[0]
    raise ValueError(f"Expected 1 document folder, found {len(subdirs)}: {subdirs}")


def validate_pages(doc_dir: Path) -> list[str]:
    """Validate that all PDF pages have corresponding markdown files with content.

    Returns a list of error messages (empty if all valid).
    """
    errors = []
    pdf_dir = doc_dir / "1_original_pdf_pages"
    md_dir = doc_dir / "2_markdown"

    # Find all PDF page files and extract their numbers
    pdf_files = list(pdf_dir.glob("page_*.pdf"))
    if not pdf_files:
        errors.append("No PDF pages found in 1_original_pdf_pages/")
        return errors

    page_numbers = sorted(
        int(re.search(r'page_(\d+)', p.name).group(1))
        for p in pdf_files
    )

    # Check for gaps in page numbers
    expected = list(range(page_numbers[0], page_numbers[-1] + 1))
    missing_pages = set(expected) - set(page_numbers)
    for page_num in sorted(missing_pages):
        errors.append(f"Page {page_num} missing from PDF sequence")

    # Check each PDF has a corresponding markdown with content
    for pdf_file in pdf_files:
        page_num = re.search(r'page_(\d+)', pdf_file.name).group(1)
        md_file = md_dir / f"page_{page_num}.md"

        if not md_file.exists():
            errors.append(f"Missing markdown file: {md_file.name}")
        elif not md_file.read_text().strip():
            errors.append(f"Empty markdown file: {md_file.name}")

    return errors


def concatenate_pages(doc_dir: Path | None = None):
    if doc_dir is None:
        doc_dir = find_document_dir()

    # Validate before concatenating
    errors = validate_pages(doc_dir)
    if errors:
        print("Validation errors found:")
        for error in errors:
            print(f"  - {error}")
        return

    md_dir = doc_dir / "2_markdown"

    # Find all page files and sort numerically
    page_files = sorted(
        md_dir.glob("page_*.md"),
        key=lambda p: int(re.search(r'page_(\d+)', p.name).group(1))
    )

    if not page_files:
        print(f"No page files found in {md_dir}")
        return

    # Find original PDF and use its name with .md extension
    pdfs = list(doc_dir.glob("*.pdf"))
    if pdfs:
        output_name = pdfs[0].stem + ".md"
    else:
        output_name = doc_dir.name + ".md"

    output_path = doc_dir / output_name

    # Concatenate
    with open(output_path, 'w') as out:
        for i, page_file in enumerate(page_files):
            content = page_file.read_text().strip()
            if i > 0:
                out.write("\n\n")
            out.write(content)

    print(f"Concatenated {len(page_files)} pages into {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Concatenate markdown pages into single file")
    parser.add_argument("doc_dir", type=Path, nargs="?", help="Document directory (auto-detected if omitted)")
    args = parser.parse_args()

    concatenate_pages(args.doc_dir)


if __name__ == "__main__":
    main()

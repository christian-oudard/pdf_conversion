#!/usr/bin/env python3
"""Convert a batch of PNG pages to markdown.

Usage: uv run python convert_batch.py [model]

Examples:
    uv run python convert_batch.py haiku
    uv run python convert_batch.py sonnet
    uv run python convert_batch.py opus
"""

import sys
from pathlib import Path
from convert_page import convert_page

DOC_DIR = Path("documents/Portfolio Selection - Harry M. Markowitz")
PNG_DIR = DOC_DIR / "1_original_png_pages"

PAGES = range(199, 211)


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "sonnet"
    md_dir = DOC_DIR / f"2_markdown_{model}"
    md_dir.mkdir(parents=True, exist_ok=True)

    print(f"Model: {model}")
    print(f"Output: {md_dir}")
    print()

    for page_num in PAGES:
        png = PNG_DIR / f"page_{page_num}.png"
        md = md_dir / f"page_{page_num}.md"

        if not png.exists():
            print(f"Skipping page {page_num}: PNG not found")
            continue

        if md.exists():
            print(f"Skipping page {page_num}: markdown already exists")
            continue

        print(f"Converting page {page_num}...", end=" ", flush=True)
        try:
            convert_page(png, md, model=model)
            print(f"-> {md.name}")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()

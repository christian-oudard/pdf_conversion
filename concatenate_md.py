#!/usr/bin/env python3
"""Concatenate all markdown page files into a single document."""

import argparse
import re
from pathlib import Path

DOC_DIR = Path("documents/Principles of Mathematical Analysis - W. Rudin")


def concatenate_pages(output_path: Path | None = None):
    md_dir = DOC_DIR / "2_markdown"

    # Find all page files and sort numerically
    page_files = sorted(
        md_dir.glob("page_*.md"),
        key=lambda p: int(re.search(r'page_(\d+)', p.name).group(1))
    )

    if not page_files:
        print(f"No page files found in {md_dir}")
        return

    # Default output path
    if output_path is None:
        output_path = DOC_DIR / "full_book.md"

    # Concatenate
    with open(output_path, 'w') as out:
        for i, page_file in enumerate(page_files):
            content = page_file.read_text().strip()
            if i > 0:
                out.write("\n\n")
            out.write(content)

    print(f"Concatenated {len(page_files)} pages into {output_path}")
    print(f"Total lines: {sum(1 for _ in open(output_path))}")


def main():
    parser = argparse.ArgumentParser(description="Concatenate markdown pages into single file")
    parser.add_argument("-o", "--output", type=Path, help="Output file path")
    args = parser.parse_args()

    concatenate_pages(args.output)


if __name__ == "__main__":
    main()

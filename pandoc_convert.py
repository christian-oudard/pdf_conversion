#!/usr/bin/env python3
"""Convert markdown to LaTeX using pandoc, then compile with tectonic."""

import argparse
import os
import subprocess
from pathlib import Path

DOC_DIR = Path("documents/Principles of Mathematical Analysis - W. Rudin")
TECTONIC_CACHE = Path(".tectonic_cache").absolute()
HEADER_FILE = Path("latex_header.tex")  # Required for math packages


def is_up_to_date(output: Path, *inputs: Path) -> bool:
    """Check if output exists and is newer than all inputs."""
    if not output.exists():
        return False
    out_mtime = output.stat().st_mtime
    return all(inp.stat().st_mtime <= out_mtime for inp in inputs if inp.exists())


def convert_page(page_num: int):
    page_str = f"page_{page_num:03d}"

    md_path = DOC_DIR / f"2_markdown/{page_str}.md"
    tex_path = DOC_DIR / f"3_latex/{page_str}.tex"
    pdf_dir = DOC_DIR / "4_reconstructed_pdf_pages"
    pdf_path = pdf_dir / f"{page_str}.pdf"

    if not md_path.exists():
        print(f"Markdown not found: {md_path}")
        return

    if not HEADER_FILE.exists():
        print(f"Missing {HEADER_FILE} - needed for math packages")
        return

    # Step 1: pandoc markdown → tex (standalone)
    if is_up_to_date(tex_path, md_path, HEADER_FILE):
        print(f"Step 1: {tex_path} (up to date)")
    else:
        pandoc_cmd = [
            'pandoc', str(md_path),
            '-o', str(tex_path),
            '--standalone',
            '-V', 'geometry:margin=1in',
            '-V', 'documentclass=article',
            '--include-in-header', str(HEADER_FILE),
        ]

        result = subprocess.run(pandoc_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Pandoc failed: {result.stderr}")
            return

        print(f"Step 1: {tex_path}")

    # Step 2: tectonic tex → pdf
    pdf_dir.mkdir(exist_ok=True)

    if is_up_to_date(pdf_path, tex_path):
        print(f"Step 2: {pdf_path} (up to date)")
    else:
        env = os.environ.copy()
        env['TECTONIC_CACHE_DIR'] = str(TECTONIC_CACHE)

        result = subprocess.run(
            ['tectonic', '-o', str(pdf_dir), str(tex_path)],
            capture_output=True, text=True, env=env
        )

        if result.returncode != 0:
            print(f"Tectonic failed: {result.stderr}")
            return

        print(f"Step 2: {pdf_path}")


def main():
    parser = argparse.ArgumentParser(description="Convert markdown to PDF via pandoc+tectonic")
    parser.add_argument("page", type=int, help="Page number to convert")
    args = parser.parse_args()

    convert_page(args.page)


if __name__ == "__main__":
    main()

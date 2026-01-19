#!/usr/bin/env python3
"""Convert original PDF and rendered outputs to PNG for comparison."""

import argparse
from pathlib import Path

import pymupdf

DOC_DIR = Path("documents/Principles of Mathematical Analysis - W. Rudin")


def is_up_to_date(output: Path, *inputs: Path) -> bool:
    """Check if output exists and is newer than all inputs."""
    if not output.exists():
        return False
    out_mtime = output.stat().st_mtime
    return all(inp.stat().st_mtime <= out_mtime for inp in inputs if inp.exists())


def pdf_to_png(pdf_path: Path, output_path: Path, dpi: int = 150):
    """Convert PDF page to PNG."""
    doc = pymupdf.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap(dpi=dpi)
    pix.save(output_path)
    doc.close()


def main():
    parser = argparse.ArgumentParser(description="Convert renders to PNG for comparison")
    parser.add_argument("page", type=int, help="Page number to compare")
    args = parser.parse_args()

    page_num = args.page
    page_str = f"page_{page_num:03d}"

    # Output folders
    orig_png_dir = DOC_DIR / "5_original_png"
    recon_png_dir = DOC_DIR / "6_reconstructed_png"
    orig_png_dir.mkdir(exist_ok=True)
    recon_png_dir.mkdir(exist_ok=True)

    # 1. Original PDF page
    orig_pdf = DOC_DIR / f"1_original_pdf_pages/{page_str}.pdf"
    orig_png = orig_png_dir / f"{page_str}.png"
    if not orig_pdf.exists():
        print(f"Original PDF not found: {orig_pdf}")
    elif is_up_to_date(orig_png, orig_pdf):
        print(f"Original PNG: {orig_png} (up to date)")
    else:
        pdf_to_png(orig_pdf, orig_png)
        print(f"Original PNG: {orig_png}")

    # 2. Reconstructed PDF
    recon_pdf = DOC_DIR / f"4_reconstructed_pdf_pages/{page_str}.pdf"
    recon_png = recon_png_dir / f"{page_str}.png"
    if not recon_pdf.exists():
        print(f"Reconstructed PDF not found: {recon_pdf}")
    elif is_up_to_date(recon_png, recon_pdf):
        print(f"Reconstructed PNG: {recon_png} (up to date)")
    else:
        pdf_to_png(recon_pdf, recon_png)
        print(f"Reconstructed PNG: {recon_png}")


if __name__ == "__main__":
    main()

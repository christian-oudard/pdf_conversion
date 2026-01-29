#!/usr/bin/env python3
"""Extract image resolution information from a PDF."""

import sys
import pymupdf


def get_image_info(pdf_path: str, max_pages: int = 5):
    """Print image resolution info for the first few pages of a PDF."""
    doc = pymupdf.open(pdf_path)

    print(f"PDF: {pdf_path}")
    print(f"Total pages: {len(doc)}")
    print()

    for page_num in range(min(max_pages, len(doc))):
        page = doc[page_num]
        images = page.get_images(full=True)

        print(f"Page {page_num + 1}: {len(images)} image(s)")

        for img_idx, img in enumerate(images):
            xref = img[0]
            base_image = doc.extract_image(xref)

            width = base_image["width"]
            height = base_image["height"]
            colorspace = base_image["colorspace"]
            bpc = base_image.get("bpc", "?")
            ext = base_image["ext"]

            print(f"  Image {img_idx + 1}: {width} x {height} px, "
                  f"{colorspace}, {bpc} bpc, format: {ext}")

        print()

    doc.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pdf_image_info.py <pdf_path> [max_pages]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    get_image_info(pdf_path, max_pages)

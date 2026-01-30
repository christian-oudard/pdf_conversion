#!/usr/bin/env python3
"""Test context limit by sending many pages at once."""

import sys
from pathlib import Path

from claude_runner import run_with_images, ClaudeError
from convert_md import SYSTEM_PROMPT
from experiment_batch import get_marker_md

PNG_DIR = Path("documents/Portfolio Selection - Harry M. Markowitz/png")
MARKER_CACHE = Path("documents/Portfolio Selection - Harry M. Markowitz/marker_cache")


def main():
    n_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 100

    pages = list(range(1, n_pages + 1))
    png_paths = [PNG_DIR / f"page_{p:03d}.png" for p in pages]

    # Cache marker md for all pages first
    print(f"Loading/caching marker md for {n_pages} pages...")
    marker_mds = [get_marker_md(p) for p in png_paths]
    print("Done caching.")

    combined = "\n\n".join(marker_mds)
    prompt = f"Review this OCR output against the images and correct errors.\n\n{combined}"

    print(f"Sending {len(png_paths)} pages...")
    try:
        r = run_with_images(prompt, png_paths, system_prompt=SYSTEM_PROMPT, model="opus")
        print(f"SUCCESS")
        print(f"Input tokens: {r.input_tokens:,}")
        print(f"  - input_tokens: {r.raw['usage'].get('input_tokens', 0):,}")
        print(f"  - cache_creation: {r.raw['usage'].get('cache_creation_input_tokens', 0):,}")
        print(f"  - cache_read: {r.raw['usage'].get('cache_read_input_tokens', 0):,}")
    except ClaudeError as e:
        print(f"FAILED: {e}")
        if e.usage:
            print(f"Usage: {e.usage}")


if __name__ == "__main__":
    main()

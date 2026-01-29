# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
uv run python -m unittest discover -v

# Run a single test file
uv run python -m unittest test_concatenate_md -v

# Run a single test
uv run python -m unittest test_concatenate_md.TestValidatePages.test_missing_page_in_sequence -v
```

## Environment

**Always use `uv run` to execute Python scripts** in this project.

**Dependencies:** pymupdf, pillow (Python), pandoc + tectonic (system, for PDF output)

## Usage

```bash
# Convert PDF to markdown (default)
uv run python pdfconvert.py documents/<book>

# Explicit format
uv run python pdfconvert.py md documents/<book>
uv run python pdfconvert.py pdf documents/<book>
uv run python pdfconvert.py epub documents/<book>

# Specific pages
uv run python pdfconvert.py pdf documents/<book> --pages 1-10

# Double-page spreads (splits each page in half)
uv run python pdfconvert.py md documents/<book> --split
```

## Output

```
documents/<book>/
    <original>.pdf           ← input
    <original>.md            ← markdown output
    <original>_output.pdf    ← PDF output
    <original>_output.epub   ← EPUB output
```

Intermediate PNGs and per-page markdown are created in a temp directory and cleaned up automatically.

## Internal Modules

- `render_png.py` — Render PDF pages to grayscale PNG (200 DPI)
- `convert_md.py` — Convert PNG to markdown via Claude
- `concatenate_md.py` — Merge markdown files
- `output_format.py` — Convert markdown to PDF/EPUB via pandoc
- `claude_runner.py` — Claude subprocess wrapper
- `pdf_utils.py` — Shared PDF utilities

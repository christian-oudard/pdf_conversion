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

**Dependencies:** pymupdf (Python), pandoc + tectonic (system, for PDF output)

## Workflow

```
documents/<book>/
    <original>.pdf
    2_markdown/
        page_001.md
        page_002.md
        ...
    <original>.md         ← (2) concatenate_md.py
    <original>_output.pdf ← (3) convert_output.py
    <original>_output.epub
```

## Step-by-Step

### Step 1: Convert Each Page to Markdown

Process in batches of 10 pages:

1. Render batch to PNG: `uv run python render_pages.py documents/<book> 1-10`
2. For each PNG:
   - Read the PNG
   - Convert to markdown with LaTeX math
   - Write: `Write documents/<book>/2_markdown/page_XXX.md`
3. Delete all 10 PNGs after successful markdown creation
4. Repeat for next batch (11-20, 21-30, etc.)

**Omit print artifacts:**
- Page numbers at top/bottom of page
- Running headers/footers (book title, chapter title repeated on every page)
- Chapter numbers repeated in headers

These are navigation aids for print that don't belong in the markdown.

**Markdown format:**
- `# ` for headers
- `**text**` for bold, `*text*` for italic
- `$...$` for inline math
- `$$...$$` for display math (on separate lines)

**LaTeX conventions:**
- `\|` for norm: `\|f\|_2`
- `\bar{}` for conjugate: `\bar{\gamma}`
- `\mathscr{R}` for script letters
- `\varepsilon` not `\epsilon`

### Step 2: Concatenate

```bash
uv run python concatenate_md.py documents/<book>
```

### Step 3: Convert to PDF/EPUB

```bash
uv run python convert_output.py documents/<book>
```

Options:
- `--format pdf` — PDF only
- `--format epub` — EPUB only
- (no flags) — both formats

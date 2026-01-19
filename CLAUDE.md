# PDF to Markdown Conversion Workflow

This project converts math-heavy PDFs to markdown with LaTeX math notation.

## Environment

**Always use `uv run` to execute Python scripts** in this project.

## Workflow

```
Original PDF
    │
    ▼ (1) split_pdf.py
1_original_pdf_pages/
    │
    ▼ (2) Convert each page to markdown (Claude)
2_markdown/
    │
    ▼ (3) concatenate_md.py
<original>.md
    │
    ▼ (4) convert_output.py
<original>_output.pdf, <original>_output.epub
```

## Folder Structure

```
documents/<book_name>/
├── <original>.pdf              # Original source PDF
├── 1_original_pdf_pages/       # Split single-page PDFs
├── 2_markdown/                 # Markdown with LaTeX math
├── <original>.md               # Concatenated markdown
├── <original>_output.pdf       # Reconstructed PDF (from pandoc)
└── <original>_output.epub      # EPUB version
```

## Step-by-Step

### Step 1: Split PDF

```bash
uv run python split_pdf.py <path_to_pdf>
```

### Step 2: Convert Each Page to Markdown

For each page:
1. Read the PDF: `Read documents/<book>/1_original_pdf_pages/page_XXX.pdf`
2. Convert to markdown with LaTeX math
3. Write: `Write documents/<book>/2_markdown/page_XXX.md`

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

### Step 3: Concatenate

```bash
uv run python concatenate_md.py
```

### Step 4: Convert to PDF/EPUB

```bash
uv run python convert_output.py
```

Generates `<original>_output.pdf` and `<original>_output.epub`.

Options:
- `--format pdf` — PDF only
- `--format epub` — EPUB only
- (no flags) — both formats

## Scripts

| Script | Usage | Description |
|--------|-------|-------------|
| `split_pdf.py` | `uv run python split_pdf.py <pdf>` | Split PDF, create folder structure |
| `concatenate_md.py` | `uv run python concatenate_md.py` | Combine all pages, validate completeness |
| `convert_output.py` | `uv run python convert_output.py` | Convert markdown to PDF and EPUB |

## Dependencies

- **Python:** pymupdf
- **System:** pandoc, tectonic (for PDF output)

```bash
uv sync
```

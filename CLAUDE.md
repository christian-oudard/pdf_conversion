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
full_book.md
```

## Folder Structure

```
documents/<book_name>/
├── <original>.pdf              # Original source PDF
├── 1_original_pdf_pages/       # Split single-page PDFs
├── 2_markdown/                 # Markdown with LaTeX math
└── full_book.md                # Concatenated output
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

## Scripts

| Script | Usage | Description |
|--------|-------|-------------|
| `split_pdf.py` | `uv run python split_pdf.py <pdf>` | Split PDF, create folder structure |
| `concatenate_md.py` | `uv run python concatenate_md.py` | Combine all pages into `full_book.md` |

## Dependencies

- **Python:** pymupdf

```bash
uv sync
```

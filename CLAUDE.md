# PDF to LaTeX Conversion Workflow

This project converts math-heavy PDFs to reconstructed LaTeX PDFs for quality comparison.

## Environment

**Always use `uv run` to execute Python scripts** in this project. Dependencies are managed with uv.

```bash
uv run python script.py <args>
```

## Workflow Overview

```
Original PDF
    │
    ▼ (1) split_pdf.py
1_original_pdf_pages/
    │
    ▼ (2) Claude Opus 4.5 (manual)
2_markdown/
    │
    ▼ (3) pandoc
3_latex/
    │
    ▼ (4) tectonic
4_reconstructed_pdf_pages/
    │
    ▼ (5) compare_renders.py
5_original_png/ + 6_reconstructed_png/
    │
    ▼ (6) Claude Opus 4.5 (manual comparison)
Quality assessment / fixes
```

## Folder Structure

```
documents/<book_name>/
├── <original>.pdf              # Original source PDF
├── 1_original_pdf_pages/       # Split single-page PDFs
├── 2_markdown/                 # Markdown with LaTeX math
├── 3_latex/                    # Generated .tex files
├── 4_reconstructed_pdf_pages/  # Rendered PDFs from LaTeX
├── 5_original_png/             # PNG of original pages
└── 6_reconstructed_png/        # PNG of reconstructed pages
```

## Step-by-Step Instructions

### Step 1: Split PDF (Automatic, one-time)

```bash
uv run python split_pdf.py <path_to_pdf>
```

This creates the folder structure and splits the PDF into individual pages.

### Steps 2-6: Process One Page at a Time

**Important:** Process each page through the full pipeline before moving to the next page. Do NOT batch operations (e.g., don't convert all pages to markdown first, then run pandoc on all). This ensures errors are caught immediately.

For each page N:
1. Convert to markdown (manual)
2. Run `uv run python pandoc_convert.py N`
3. Run `uv run python compare_renders.py N`
4. Compare PNGs, fix markdown if needed
5. Repeat steps 2-4 until quality is acceptable
6. Move to page N+1

### Step 2: Convert PDF Page to Markdown (Manual - Claude Opus)

1. Read the original PDF page:
   ```
   Read documents/<book>/1_original_pdf_pages/page_XXX.pdf
   ```

2. Convert to markdown with LaTeX math:
   - Use `# ` for headers
   - Use `**text**` for bold
   - Use `*text*` for italic
   - Use `$...$` for inline math
   - Use `$$...$$` for display math (on separate lines)

3. Write the markdown file:
   ```
   Write documents/<book>/2_markdown/page_XXX.md
   ```

**Example markdown format:**
```markdown
# CHAPTER TITLE

**8.16 Theorem Name** *Statement of theorem with $f$ and $g$ being functions.*

$$
(82) \qquad f(x) \sim \sum_{-\infty}^{\infty} c_n e^{inx}
$$

**Proof** Let $\varepsilon > 0$ be given. Since $f \in \mathscr{R}$...
```

**Important LaTeX conventions:**
- Use `\|` for norm: `\|f\|_2` renders as ‖f‖₂
- Use `\bar{}` for conjugate: `\bar{\gamma}` renders as γ̄
- Use `\overline{}` for wide overline: `\overline{g(x)}`
- Use `\mathscr{R}` for script letters (requires mathrsfs package)
- Use `\varepsilon` not `\epsilon` for ε
- Use `\qquad` for equation number spacing

### Step 3 & 4: Convert Markdown to PDF (Automatic)

```bash
uv run python pandoc_convert.py <page_number>
```

This runs:
1. `pandoc` to convert markdown → .tex
2. `tectonic` to compile .tex → .pdf

**Note:** Tectonic needs `TECTONIC_CACHE_DIR` set to `.tectonic_cache` for sandbox environments.

### Step 5: Generate Comparison PNGs (Automatic)

```bash
uv run python compare_renders.py <page_number>
```

This converts both original and reconstructed PDFs to PNGs at 150 DPI.

### Step 6: Compare and Fix (Manual - Claude Opus)

1. Read both PNG files:
   ```
   Read documents/<book>/5_original_png/page_XXX.png
   Read documents/<book>/6_reconstructed_png/page_XXX.png
   ```

2. Compare visually and note discrepancies.

3. If issues found, fix the markdown and re-run steps 3-5.

## Troubleshooting

### Common Issues and Fixes

#### Math doesn't render correctly

**Problem:** Symbols appear as boxes or wrong characters.

**Fix:** Check LaTeX commands:
- Wrong: `||f||` → Right: `\|f\|`
- Wrong: `\epsilon` → Right: `\varepsilon`
- Wrong: Missing `$` delimiters

#### Tectonic fails with missing package

**Problem:** `File 'xxx.sty' not found`

**Fix:** The package isn't cached. Run with network access to download:
```bash
TECTONIC_CACHE_DIR=".tectonic_cache" tectonic <file.tex>
```

Required packages in `latex_header.tex`:
```latex
\usepackage{amsmath,amssymb,amsfonts,mathrsfs}
```

#### Pandoc outputs HTML instead of LaTeX

**Problem:** Output has `<span>` tags instead of `\textbf{}`

**Fix:** Ensure pandoc uses LaTeX output format. The script uses `--standalone` which should handle this, but verify the .tex file content.

#### Display math not centered

**Problem:** Equations appear inline instead of displayed.

**Fix:** Ensure `$$` is on its own line:
```markdown
Wrong:
Some text $$equation$$ more text.

Right:
Some text

$$
equation
$$

more text.
```

#### Missing or wrong symbols

| Original | Wrong | Correct LaTeX |
|----------|-------|---------------|
| ‖f‖ | \|\|f\|\| | `\|f\|` |
| ∈ | \in | `\in` (correct) |
| ℛ | R | `\mathscr{R}` |
| γ̄ | \gamma | `\bar{\gamma}` |
| ε | \epsilon | `\varepsilon` |
| → | -> | `\to` or `\rightarrow` |
| ≤ | <= | `\leq` or `\le` |
| ∞ | infinity | `\infty` |

#### Equation numbers misaligned

**Problem:** Equation numbers like (82) not aligned with original.

**Fix:** Use `\qquad` for spacing:
```latex
(82) \qquad f(x) = ...
```

#### Text formatting issues

**Problem:** Bold/italic not rendering.

**Fix:** Check markdown syntax:
- Bold: `**text**` (no spaces inside)
- Italic: `*text*` (no spaces inside)
- Don't nest: `***text***` won't work as expected

## Scripts Reference

| Script | Usage | Description |
|--------|-------|-------------|
| `split_pdf.py` | `uv run python split_pdf.py <pdf>` | Split PDF, create folder structure |
| `pandoc_convert.py` | `uv run python pandoc_convert.py <page>` | Markdown → .tex → .pdf |
| `compare_renders.py` | `uv run python compare_renders.py <page>` | Generate comparison PNGs |
| `concatenate_md.py` | `uv run python concatenate_md.py` | Combine all pages into `full_book.md` |

## Dependencies

- **Python:** pymupdf
- **System:** pandoc, tectonic

Install Python deps:
```bash
uv sync
```

Install system deps (Arch Linux):
```bash
sudo pacman -S pandoc tectonic
```

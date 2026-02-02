# pdfconvert

Convert scanned PDF books to markdown, EPUB, or reconstructed PDF, using OCR on Modal (cloud GPU) with Claude-powered review.

## Installation

```bash
uv tool install .
```

## Setup

### 1. Modal (Cloud GPU for OCR)

The OCR step runs [marker-pdf](https://github.com/VikParuchuri/marker) on Modal's cloud GPUs.

1. Create a Modal account at https://modal.com
2. Install and authenticate:
   ```bash
   uv tool install modal
   modal setup
   ```
3. Deploy the marker app:
   ```bash
   modal deploy pdf_conversion/modal_marker.py
   ```

The first run downloads ~2GB of ML models into the Modal image. Subsequent runs use the cached image.

Modal gives $30/month in free credits to starter accounts. At ~$1.10/hour for A10G GPU, a 100-page book typically costs $0.05-0.10.

### 2. Claude Code CLI

Claude reviews and corrects the OCR output. This requires the Claude Code CLI and a paid Claude subscription (Pro, Max, or Team).

1. Install Claude Code: https://docs.anthropic.com/en/docs/claude-code
2. Authenticate:
   ```bash
   claude login
   ```

### 3. Output Directory (Optional)

By default, converted documents are stored in `./documents`. To change this, set the `PDFCONVERT_OUTPUT_DIR` environment variable in your shell config:

```bash
# ~/.bashrc or ~/.zshrc
export PDFCONVERT_OUTPUT_DIR="$HOME/books"
```

### 4. PDF/EPUB Output (Optional)

For PDF or EPUB output formats, install pandoc and tectonic:

```bash
# macOS
brew install pandoc tectonic

# Arch Linux
pacman -S pandoc tectonic

# Ubuntu/Debian
apt install pandoc
# tectonic: see https://tectonic-typesetting.github.io/
```

## Usage

```bash
# Convert PDF to markdown (default)
pdfconvert documents/mybook.pdf

# Explicit format
pdfconvert md documents/mybook.pdf
pdfconvert pdf documents/mybook.pdf
pdfconvert epub documents/mybook.pdf

# Specific pages
pdfconvert md documents/mybook.pdf --pages 1-10
pdfconvert md documents/mybook.pdf --pages 50-   # page 50 to end

# Double-page spreads (splits each page in half)
pdfconvert md documents/mybook.pdf --split

# Parallel Claude API calls (default: 8)
pdfconvert md documents/mybook.pdf -j 4

# Force regeneration
pdfconvert md documents/mybook.pdf --redo-marker  # re-run Modal OCR
pdfconvert md documents/mybook.pdf --redo-png     # re-render PNGs
pdfconvert md documents/mybook.pdf --redo-claude  # re-run Claude review
```

## Output Structure

```
$PDFCONVERT_OUTPUT_DIR/mybook/
    mybook.pdf              # input (copied here)
    mybook.md               # markdown output
    mybook_output.pdf       # PDF output (if requested)
    mybook_output.epub      # EPUB output (if requested)
    marker_full.md          # cached marker OCR output
    png/                    # rendered page images
    pages/                  # cached Claude review batches
```

## How It Works

1. **Modal OCR**: Uploads PDF to Modal, runs marker-pdf on GPU, returns paginated markdown
2. **PNG Rendering**: Renders each page to grayscale PNG (extracts embedded images when possible)
3. **Claude Review**: Sends batches of 5 pages (PNG + marker output) to Claude Opus for OCR correction
4. **Concatenation**: Combines reviewed pages into final markdown
5. **Format Conversion**: Optionally converts to PDF/EPUB via pandoc

# pdf-conversion

Convert scanned PDF books to markdown, PDF, or EPUB.

## Usage

```bash
# Convert PDF to markdown (default)
uv run python pdfconvert.py documents/<book>

# Explicit format
uv run python pdfconvert.py pdf documents/<book>
uv run python pdfconvert.py epub documents/<book>

# Specific pages
uv run python pdfconvert.py pdf documents/<book> --pages 1-10

# Double-page spreads (splits each page in half)
uv run python pdfconvert.py md documents/<book> --split

# Force regeneration
uv run python pdfconvert.py md documents/<book> --redo-png  # re-render PNGs
uv run python pdfconvert.py md documents/<book> --redo-md   # re-convert markdown
```

## Dependencies

- Python: pymupdf, pillow, marker-pdf
- System: pandoc, tectonic (for PDF/EPUB output)

## Future Work

- **Marker server**: Run marker-pdf as a service to avoid VRAM contention when running multiple conversions in parallel. Would load models once and accept PNG→markdown requests over HTTP.

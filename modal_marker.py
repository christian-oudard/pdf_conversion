#!/usr/bin/env python3
"""Run marker-pdf on Modal for fast GPU conversion.

Usage:
    # Deploy and run on a PDF
    modal run modal_marker.py --pdf documents/Avellaneda_Stoikov_2008/Avellaneda_Stoikov_2008.pdf

    # Or import and call from Python
    from modal_marker import convert_pdf
    markdown = convert_pdf.remote(pdf_bytes)
"""

import modal

app = modal.App("marker-pdf")


def download_models():
    """Download marker models during image build."""
    from marker.models import create_model_dict

    create_model_dict()  # Downloads and caches all models


# Build image with marker and dependencies, models pre-downloaded
marker_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1-mesa-glx", "libglib2.0-0")
    .pip_install(
        "marker-pdf",
        "torch",
        "torchvision",
    )
    .run_function(download_models)  # Bake models into image
)


@app.cls(
    image=marker_image,
    gpu="A100-40GB",
    timeout=3600,  # 1 hour
    scaledown_window=120,  # Keep warm for 2 min
)
class MarkerConverter:
    @modal.enter()
    def load_models(self):
        """Load marker models once when container starts."""
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        from marker.config.parser import ConfigParser

        print("Loading marker models...")
        config = {
            "output_format": "markdown",
            "force_ocr": True,  # Always OCR, skip text extraction
            "batch_multiplier": 64,  # Use more VRAM for speed (A100-40GB has 40GB)
        }
        config_parser = ConfigParser(config)

        self.converter = PdfConverter(
            config=config_parser.generate_config_dict(),
            artifact_dict=create_model_dict(),
            processor_list=config_parser.get_processors(),
            renderer=config_parser.get_renderer(),
        )
        self.converter.renderer.paginate_output = True  # type: ignore[union-attr]
        print("Models loaded.")

    @modal.method()
    def convert(self, pdf_bytes: bytes) -> str:
        """Convert PDF bytes to paginated markdown."""
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            pdf_path = Path(f.name)

        try:
            rendered = self.converter(str(pdf_path))
            return rendered.markdown
        finally:
            pdf_path.unlink()


@app.local_entrypoint()
def main(pdf: str):
    """Convert a local PDF file using Modal."""
    from pathlib import Path

    pdf_path = Path(pdf)
    if not pdf_path.exists():
        print(f"Error: {pdf_path} not found")
        return

    print(f"Uploading {pdf_path.name} ({pdf_path.stat().st_size / 1024:.1f} KB)...")
    pdf_bytes = pdf_path.read_bytes()

    print("Converting on Modal...")
    converter = MarkerConverter()
    markdown = converter.convert.remote(pdf_bytes)

    output_path = pdf_path.with_suffix(".modal.md")
    output_path.write_text(markdown)
    print(f"Output: {output_path}")
    print(f"Length: {len(markdown):,} chars")

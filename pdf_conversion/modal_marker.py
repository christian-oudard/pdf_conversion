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

# Modal GPU pricing (USD/hour) - https://modal.com/pricing
GPU_PRICES = {
    "T4": 0.59,
    "L4": 0.80,
    "A10G": 1.10,
    "A100-40GB": 3.00,
    "A100-80GB": 4.58,
    "H100": 5.49,
}

# Configuration (importable by pdfconvert.py)
GPU = "A10G"

# Batch sizes - surya recommended defaults (from README)
RECOGNITION_BATCH_SIZE = 512   # 40MB/item, ~20GB VRAM
LAYOUT_BATCH_SIZE = 32         # 220MB/item, ~7GB VRAM
DETECTION_BATCH_SIZE = 36      # 440MB/item, ~16GB VRAM
OCR_ERROR_BATCH_SIZE = 32      # Similar to layout
EQUATION_BATCH_SIZE = 512      # Same as recognition
TABLE_REC_BATCH_SIZE = 64      # 150MB/item, ~10GB VRAM

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
    gpu=GPU,
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
            "extract_images": False,  # We do our own PNG rendering
            # Batch sizes for different model stages (marker 1.10.1+)
            "recognition_batch_size": RECOGNITION_BATCH_SIZE,
            "layout_batch_size": LAYOUT_BATCH_SIZE,
            "detection_batch_size": DETECTION_BATCH_SIZE,
            "ocr_error_batch_size": OCR_ERROR_BATCH_SIZE,
            "equation_batch_size": EQUATION_BATCH_SIZE,
            "table_rec_batch_size": TABLE_REC_BATCH_SIZE,
        }
        print(f"Config: rec={RECOGNITION_BATCH_SIZE}, layout={LAYOUT_BATCH_SIZE}, det={DETECTION_BATCH_SIZE}, ocr_err={OCR_ERROR_BATCH_SIZE}, eq={EQUATION_BATCH_SIZE}, table={TABLE_REC_BATCH_SIZE}")
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
        """Convert PDF bytes to paginated markdown (non-streaming)."""
        for item in self.convert_streaming(pdf_bytes):
            if item.startswith("RESULT:"):
                return item[7:]
        raise RuntimeError("No result returned from convert_streaming")

    @modal.method()
    def convert_streaming(self, pdf_bytes: bytes):
        """Convert PDF bytes to paginated markdown, yielding progress lines."""
        import os
        import sys
        import tempfile
        import threading
        import time
        from pathlib import Path

        import torch

        # Track peak VRAM usage
        peak_vram = [0.0]
        stop_monitor = threading.Event()

        def monitor_gpu():
            while not stop_monitor.is_set():
                allocated = torch.cuda.memory_allocated() / 1024**3
                peak_vram[0] = max(peak_vram[0], allocated)
                time.sleep(1)

        # Capture stderr (where tqdm writes) via a pipe
        progress_lines = []
        old_stderr = sys.stderr
        read_fd, write_fd = os.pipe()
        sys.stderr = os.fdopen(write_fd, 'w', buffering=1)

        def read_progress():
            with os.fdopen(read_fd, 'r') as pipe:
                for line in pipe:
                    progress_lines.append(line.rstrip())

        reader_thread = threading.Thread(target=read_progress, daemon=True)
        reader_thread.start()

        monitor_thread = threading.Thread(target=monitor_gpu, daemon=True)
        monitor_thread.start()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            pdf_path = Path(f.name)

        try:
            # Yield progress lines while conversion runs
            result = [None]
            error = [None]

            def do_convert():
                try:
                    result[0] = self.converter(str(pdf_path))
                except Exception as e:
                    error[0] = e

            convert_thread = threading.Thread(target=do_convert)
            convert_thread.start()

            last_idx = 0
            while convert_thread.is_alive():
                time.sleep(0.5)
                # Yield any new progress lines
                while last_idx < len(progress_lines):
                    yield progress_lines[last_idx]
                    last_idx += 1

            convert_thread.join()

            # Restore stderr and close pipe
            sys.stderr.close()
            sys.stderr = old_stderr
            reader_thread.join(timeout=1)

            # Yield remaining progress lines
            while last_idx < len(progress_lines):
                yield progress_lines[last_idx]
                last_idx += 1

            stop_monitor.set()

            if error[0]:
                raise error[0]

            yield f"Peak VRAM: {peak_vram[0]:.1f} GB"
            yield f"RESULT:{result[0].markdown}"
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

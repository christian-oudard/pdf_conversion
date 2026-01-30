#!/usr/bin/env python3
"""Experiment to find optimal batch size for Opus page conversion.

Usage:
    # Test specific batch size
    uv run python experiment_batch.py --batch-size 10 --pages 1-20

    # Binary search for max batch size
    uv run python experiment_batch.py --find-max --pages 1-30

    # Test at different DPI
    uv run python experiment_batch.py --batch-size 10 --dpi 150 --pages 1-20
"""

import argparse
import io
import sys
from pathlib import Path

from PIL import Image

from claude_runner import run_with_images, ClaudeError
from convert_md import get_marker_converter, SYSTEM_PROMPT
from pdf_utils import parse_page_range

BOOK_DIR = Path("documents/Portfolio Selection - Harry M. Markowitz")
PNG_DIR = BOOK_DIR / "png"
PAGES_DIR = BOOK_DIR / "pages"
MARKER_CACHE_DIR = BOOK_DIR / "marker_cache"

CURRENT_DPI = 200


def resize_to_dpi(png_path: Path, target_dpi: int) -> bytes:
    """Resize PNG to different DPI, return as bytes."""
    if target_dpi == CURRENT_DPI:
        return png_path.read_bytes()

    scale = target_dpi / CURRENT_DPI
    img = Image.open(png_path)
    new_size = (int(img.width * scale), int(img.height * scale))
    img = img.resize(new_size, Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def get_marker_md(png_path: Path) -> str:
    """Get marker markdown for a PNG, using cache."""
    MARKER_CACHE_DIR.mkdir(exist_ok=True)
    cache_path = MARKER_CACHE_DIR / png_path.with_suffix('.md').name

    if cache_path.exists():
        return cache_path.read_text()

    # Generate with marker and cache
    import contextlib
    print(f"  marker {png_path.name}...", end=" ", flush=True)
    converter = get_marker_converter()
    with contextlib.redirect_stderr(io.StringIO()):
        rendered = converter(str(png_path))
    cache_path.write_text(rendered.markdown)
    print("done")
    return rendered.markdown


def build_batch_prompt(marker_mds: list[str]) -> str:
    """Build prompt for batch review."""
    combined_md = "\n\n".join(marker_mds)
    return f"""Here is OCR output from {len(marker_mds)} consecutive scanned book pages.
Review against the original images and correct any errors.

{combined_md}"""


def run_batch_test(
    png_paths: list[Path],
    marker_mds: list[str],
    dpi: int = CURRENT_DPI,
    tmp_dir: Path | None = None,
) -> dict:
    """Send batch to Opus, return results.

    Returns dict with:
    - success: bool
    - input_tokens: int
    - output_tokens: int
    - result: str | None
    - error: str | None
    """
    # Resize images if needed
    if dpi != CURRENT_DPI:
        if tmp_dir is None:
            tmp_dir = Path("/tmp/claude/batch_experiment")
        tmp_dir.mkdir(parents=True, exist_ok=True)

        resized_paths = []
        for png_path in png_paths:
            resized_path = tmp_dir / f"{png_path.stem}_{dpi}dpi.png"
            if not resized_path.exists():
                resized_bytes = resize_to_dpi(png_path, dpi)
                resized_path.write_bytes(resized_bytes)
            resized_paths.append(resized_path)
        png_paths = resized_paths

    prompt = build_batch_prompt(marker_mds)

    try:
        response = run_with_images(
            prompt,
            png_paths,
            allowed_tools=["Read"],
            system_prompt=SYSTEM_PROMPT,
            model="opus",
        )
        return {
            "success": True,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "result": response.result,
            "error": None,
        }
    except ClaudeError as e:
        return {
            "success": False,
            "input_tokens": e.usage.get("input_tokens", 0),
            "output_tokens": e.usage.get("output_tokens", 0),
            "result": None,
            "error": str(e),
        }


def estimate_max_batch(
    png_paths: list[Path],
    marker_mds: list[str],
    dpi: int = CURRENT_DPI,
    sample_size: int = 10,
    context_limit: int = 200_000,
) -> dict:
    """Estimate max batch size by testing a sample and extrapolating."""
    print(f"Testing {sample_size} pages to estimate tokens per page...")

    result = run_batch_test(
        png_paths[:sample_size],
        marker_mds[:sample_size],
        dpi=dpi,
    )

    if not result["success"]:
        return {"error": result["error"], "max_batch": 0}

    tokens_per_page = result["input_tokens"] / sample_size
    # Leave room for output (~20% of context)
    available = context_limit * 0.8
    max_batch = int(available / tokens_per_page)

    return {
        "sample_size": sample_size,
        "input_tokens": result["input_tokens"],
        "tokens_per_page": tokens_per_page,
        "estimated_max_batch": max_batch,
    }


def main():
    parser = argparse.ArgumentParser(description="Batch conversion experiments")
    parser.add_argument("--pages", type=str, default="1-30", help="Page range")
    parser.add_argument("--dpi", type=int, default=200, help="Target DPI")
    parser.add_argument("--batch-size", type=int, help="Specific batch size to test")
    parser.add_argument("--find-max", action="store_true", help="Binary search for max batch size")
    args = parser.parse_args()

    # Parse page range
    page_nums = parse_page_range(args.pages, 360)
    print(f"Pages: {page_nums[0]}-{page_nums[-1]} ({len(page_nums)} pages)")
    print(f"DPI: {args.dpi}")
    print()

    # Load PNGs
    png_paths = []
    for page_num in page_nums:
        png_path = PNG_DIR / f"page_{page_num:03d}.png"
        if not png_path.exists():
            print(f"Warning: {png_path} not found", file=sys.stderr)
            continue
        png_paths.append(png_path)

    print(f"Loaded {len(png_paths)} PNGs")

    # Pre-cache marker markdown (this is the slow part)
    uncached = [p for p in png_paths if not (MARKER_CACHE_DIR / p.with_suffix('.md').name).exists()]
    if uncached:
        print(f"Caching {len(uncached)} marker conversions...")
    marker_mds = [get_marker_md(p) for p in png_paths]
    print(f"Loaded {len(marker_mds)} marker MDs (cached)")
    print()

    if args.find_max:
        print("=== Binary search for max batch size ===")
        max_size, result = find_max_batch_size(
            png_paths, marker_mds, page_nums, dpi=args.dpi
        )
        print()
        print(f"Max batch size at {args.dpi} DPI: {max_size}")
        if result:
            print(f"Input tokens: {result['input_tokens']:,}")
            print(f"Output tokens: {result['output_tokens']:,}")
            tokens_per_page = result['input_tokens'] / max_size
            print(f"Tokens per page: {tokens_per_page:,.0f}")

    elif args.batch_size:
        print(f"=== Testing batch size {args.batch_size} ===")
        result = run_batch_test(
            png_paths[:args.batch_size],
            marker_mds[:args.batch_size],
            page_nums[:args.batch_size],
            dpi=args.dpi,
        )
        print()
        if result["success"]:
            print("SUCCESS")
            print(f"Input tokens: {result['input_tokens']:,}")
            print(f"Output tokens: {result['output_tokens']:,}")
            tokens_per_page = result['input_tokens'] / args.batch_size
            print(f"Tokens per page: {tokens_per_page:,.0f}")
        else:
            print(f"FAILED: {result['error']}")

    else:
        parser.error("Specify --batch-size or --find-max")


if __name__ == "__main__":
    main()

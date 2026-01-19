#!/usr/bin/env python3
"""Convert concatenated markdown to PDF and EPUB using pandoc."""

import argparse
import subprocess
import sys
from pathlib import Path


def find_document_dir() -> Path:
    """Find the document directory (assumes single document in documents/)."""
    docs = Path("documents")
    subdirs = [d for d in docs.iterdir() if d.is_dir()]
    if len(subdirs) == 1:
        return subdirs[0]
    raise ValueError(f"Expected 1 document folder, found {len(subdirs)}: {subdirs}")


def find_markdown_file(doc_dir: Path) -> Path:
    """Find the concatenated markdown file (not page_XXX.md files)."""
    # Look for .md files directly in doc_dir (not in subdirectories)
    md_files = [
        f for f in doc_dir.glob("*.md")
        if not f.name.startswith("page_")
    ]

    if not md_files:
        raise FileNotFoundError(f"No concatenated markdown file found in {doc_dir}")

    if len(md_files) > 1:
        # Prefer one matching the PDF name
        pdfs = list(doc_dir.glob("*.pdf"))
        if pdfs:
            expected_name = pdfs[0].stem + ".md"
            for md in md_files:
                if md.name == expected_name:
                    return md

    return md_files[0]


def build_pandoc_command(md_file: Path, output_format: str) -> list[str]:
    """Build the pandoc command for the given output format."""
    # Use _output suffix to avoid overwriting original PDF
    output_file = md_file.with_stem(md_file.stem + "_output").with_suffix(f".{output_format}")

    cmd = ["pandoc", str(md_file), "-o", str(output_file)]

    if output_format == "pdf":
        # Use tectonic for better unicode and font support
        cmd.extend([
            "--pdf-engine=tectonic",
            "-V", "geometry:margin=1in",
        ])
    elif output_format == "epub":
        # Use MathML for math formulas in EPUB
        cmd.append("--mathml")

    return cmd


def convert(doc_dir: Path | None = None, formats: list[str] | None = None):
    """Convert markdown to specified output formats."""
    if doc_dir is None:
        doc_dir = find_document_dir()

    if formats is None:
        formats = ["pdf", "epub"]

    md_file = find_markdown_file(doc_dir)
    print(f"Converting {md_file.name}...")

    for fmt in formats:
        cmd = build_pandoc_command(md_file, fmt)
        output_file = md_file.with_stem(md_file.stem + "_output").with_suffix(f".{fmt}")

        print(f"  → {output_file.name}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Error converting to {fmt}:")
            print(result.stderr)
            sys.exit(1)

    print("Done.")


def main():
    parser = argparse.ArgumentParser(
        description="Convert concatenated markdown to PDF and EPUB"
    )
    parser.add_argument(
        "doc_dir",
        type=Path,
        nargs="?",
        help="Document directory (auto-detected if omitted)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["pdf", "epub"],
        action="append",
        dest="formats",
        help="Output format (can be specified multiple times, default: both)",
    )
    args = parser.parse_args()

    convert(args.doc_dir, args.formats)


if __name__ == "__main__":
    main()

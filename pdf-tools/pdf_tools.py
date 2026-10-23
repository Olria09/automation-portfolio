"""Merge PDF files by filename prefix and optionally make them searchable."""

from __future__ import annotations

import argparse
import io
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from pdf2image import convert_from_path
from pypdf import PdfWriter
import pytesseract


def safe_filename(value: str) -> str:
    """Return a filesystem-friendly name while preserving readable text."""
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", value).strip(" ._")
    return cleaned or "merged"


def collect_groups(input_dir: Path) -> dict[str, list[Path]]:
    """Group top-level PDFs by the text before the first hyphen."""
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input directory does not exist: {input_dir}")

    groups: dict[str, list[Path]] = defaultdict(list)
    for path in input_dir.iterdir():
        if path.is_file() and path.suffix.lower() == ".pdf":
            prefix = path.stem.split("-", maxsplit=1)[0].strip()
            if prefix:
                groups[prefix].append(path)

    for paths in groups.values():
        paths.sort(key=lambda item: item.name.casefold())
    return dict(sorted(groups.items(), key=lambda item: item[0].casefold()))


def append_pdf(
    writer: PdfWriter,
    pdf_path: Path,
    *,
    run_ocr: bool = False,
    language: str = "spa+eng",
    dpi: int = 200,
    poppler_path: str | None = None,
    keepalive: list[io.BytesIO] | None = None,
) -> None:
    """Append a PDF directly, or append OCR-searchable pages when requested."""
    if not run_ocr:
        writer.append(str(pdf_path))
        return

    images = convert_from_path(
        str(pdf_path), dpi=dpi, poppler_path=poppler_path or None
    )
    if not images:
        raise ValueError(f"No pages were rendered from {pdf_path.name}")

    for page_number, image in enumerate(images, start=1):
        pdf_bytes = pytesseract.image_to_pdf_or_hocr(
            image, extension="pdf", lang=language
        )
        page_stream = io.BytesIO(pdf_bytes)
        writer.append(page_stream)
        if keepalive is not None:
            keepalive.append(page_stream)
        print(f"  OCR page {page_number}/{len(images)}: {pdf_path.name}")


def write_pdf(
    pdf_paths: Iterable[Path],
    output_path: Path,
    *,
    run_ocr: bool = False,
    language: str = "spa+eng",
    dpi: int = 200,
    poppler_path: str | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    keepalive: list[io.BytesIO] = []
    try:
        for pdf_path in pdf_paths:
            append_pdf(
                writer,
                pdf_path,
                run_ocr=run_ocr,
                language=language,
                dpi=dpi,
                poppler_path=poppler_path,
                keepalive=keepalive,
            )
        with output_path.open("wb") as output_file:
            writer.write(output_file)
    finally:
        writer.close()
        for stream in keepalive:
            stream.close()


def merge_by_prefix(
    input_dir: Path,
    output_dir: Path,
    *,
    run_ocr: bool = False,
    language: str = "spa+eng",
    dpi: int = 200,
    poppler_path: str | None = None,
) -> list[Path]:
    if input_dir.resolve() == output_dir.resolve():
        raise ValueError("Choose a separate output directory so generated PDFs are not merged again")
    groups = collect_groups(input_dir)
    if not groups:
        raise FileNotFoundError(f"No PDF files found in {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for group, pdf_paths in groups.items():
        base = safe_filename(group)
        version = 1
        while True:
            output_path = output_dir / f"{base}{version}.pdf"
            if not output_path.exists():
                break
            version += 1

        print(f"Merging {len(pdf_paths)} file(s) for '{group}'...")
        write_pdf(
            pdf_paths,
            output_path,
            run_ocr=run_ocr,
            language=language,
            dpi=dpi,
            poppler_path=poppler_path,
        )
        created.append(output_path)
        print(f"Created: {output_path}")
    return created


def make_searchable(
    input_pdf: Path,
    output_pdf: Path,
    *,
    language: str = "spa+eng",
    dpi: int = 200,
    poppler_path: str | None = None,
) -> Path:
    if not input_pdf.is_file() or input_pdf.suffix.lower() != ".pdf":
        raise FileNotFoundError(f"PDF file does not exist: {input_pdf}")
    if input_pdf.resolve() == output_pdf.resolve():
        raise ValueError("Input and output paths must be different")
    write_pdf(
        [input_pdf],
        output_pdf,
        run_ocr=True,
        language=language,
        dpi=dpi,
        poppler_path=poppler_path,
    )
    return output_pdf


def positive_dpi(value: str) -> int:
    try:
        dpi = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("DPI must be a whole number") from exc
    if dpi < 50 or dpi > 600:
        raise argparse.ArgumentTypeError("DPI must be between 50 and 600")
    return dpi


def add_ocr_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--lang", default="spa+eng", help="Tesseract language(s), e.g. spa+eng")
    parser.add_argument("--dpi", type=positive_dpi, default=200, help="OCR render resolution (50–600; default: 200)")
    parser.add_argument("--poppler-path", help="Optional path to Poppler's bin directory")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge PDFs by filename prefix and optionally add searchable OCR text."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    merge_parser = commands.add_parser("merge", help="Merge PDFs grouped by filename prefix")
    merge_parser.add_argument("input_dir", type=Path)
    merge_parser.add_argument("output_dir", type=Path)
    merge_parser.add_argument("--ocr", action="store_true", help="Run OCR on each source PDF before merging")
    add_ocr_options(merge_parser)

    ocr_parser = commands.add_parser("ocr", help="Create a searchable copy of one PDF")
    ocr_parser.add_argument("input_pdf", type=Path)
    ocr_parser.add_argument("output_pdf", type=Path)
    add_ocr_options(ocr_parser)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "merge":
            merge_by_prefix(
                args.input_dir,
                args.output_dir,
                run_ocr=args.ocr,
                language=args.lang,
                dpi=args.dpi,
                poppler_path=args.poppler_path,
            )
        else:
            print(f"Created: {make_searchable(args.input_pdf, args.output_pdf, language=args.lang, dpi=args.dpi, poppler_path=args.poppler_path)}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

# PDF Merge and OCR Tool

A command-line tool to merge PDF files by filename prefix and optionally make scanned PDFs searchable with OCR. It runs locally and does not upload documents to a service.

## Features

- Groups PDFs by the text before the first hyphen in each filename.
- Merges each group in alphabetical filename order.
- Adds a numbered suffix when an output filename already exists.
- Creates searchable PDFs from scanned documents with Tesseract OCR.
- Accepts input, output, language, DPI, and Poppler paths as command-line options.

## Requirements

- Python 3.10+
- Tesseract OCR with the language data you plan to use (for example, Spanish and English).
- Poppler, required by `pdf2image` to render pages.

Install the Python packages:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

Install Tesseract and Poppler separately for your operating system. On Windows, pass the Poppler `bin` directory with `--poppler-path` when it is not on `PATH`.

## Usage

Merge PDFs into one output per filename group:

```bash
python pdf_tools.py merge ./incoming ./output
```

Run OCR on each source PDF before merging:

```bash
python pdf_tools.py merge ./incoming ./output --ocr --lang spa+eng --dpi 200
```

Create a searchable copy of one scanned PDF:

```bash
python pdf_tools.py ocr ./scans/document.pdf ./output/document-searchable.pdf --lang spa+eng
```

Filenames such as `Venue-01.pdf` and `Venue-02.pdf` are grouped as `Venue`. Files without a hyphen are grouped by their full filename stem. Existing outputs are preserved; the tool creates the next available numbered output name.

## Notes

- OCR quality depends on scan quality and the installed Tesseract language data.
- OCR renders pages into images, so OCR output can be larger and slower to create than the original PDF.
- Test with copies of important files and review the generated output.

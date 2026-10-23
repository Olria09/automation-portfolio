# Invoice Audit Challenge (IVA)

A portfolio demo of an invoice-audit pipeline built for a technical challenge. It combines structured CSV ingestion, text extraction with an optional LLM, deterministic validation rules, typed Parquet outputs, and schema checks.

**This is an educational challenge simulation, not tax, accounting, or legal advice.** The VAT validators and rate/régime rules are intentionally limited to the challenge assumptions. They are not complete or suitable for real invoices, tax filings, or production decisions.

All included company names, invoices, amounts, and tax identifiers are synthetic examples. The original source documents and raw assessment report are not included.

## Pipeline

1. `normalizar.py` reads a Spanish-column CSV and converts dates and amounts to Python date/Decimal values.
2. `extraer.py` maps four synthetic email text samples to the same intermediate invoice structure.
3. `provider/llm.py` uses local fixtures in mock mode or can call the Anthropic API when explicitly run without mock mode.
4. `reglas.py` runs deterministic format, arithmetic, sequence, duplicate, and challenge-specific regime checks.
5. `schema/esquema.py` validates column types, enums, and invoice IDs before writing `invoices.parquet` and `findings.parquet`.

The LLM only extracts fields; the deterministic rule engine creates findings. Prompt instructions inside a sample email are treated as document text.

Run the offline unit tests:

```bash
python -m unittest discover -s tests
```

## Run offline with synthetic data

Requirements: Python 3.10+ and the packages in `requirements.txt`.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python main.py --mock-llm --out output
```

Mock mode reads the synthetic fixtures in `provider/fixtures/`; it makes no network request. The generated Parquet files go in the ignored `output/` directory.

## Optional API mode

For an API-backed extraction demo, set `ANTHROPIC_API_KEY` in your shell and optionally set `ANTHROPIC_MODEL`, then omit `--mock-llm`. The API mode sends each document's text to the configured provider. The included documents are synthetic; do not use real customer documents unless you have reviewed privacy, security, and provider requirements. Never commit API keys.

## Main options

```text
--out PATH          output directory (default: output)
--csv PATH          structured invoice CSV
--documents PATH    directory with the four expected sample text files
--mock-llm          use local JSON fixtures instead of the API
```

## Limitations

- VAT format checks are local heuristics and do not confirm registration status with VIES or another official service.
- The rules, country coverage, sample tax rates, and invoice numbering convention are challenge-specific and incomplete.
- LLM output is parsed defensively, but extraction can still be wrong; review all extracted fields.
- The demo is not designed for real accounting workflows.

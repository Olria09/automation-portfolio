#!/usr/bin/env python3
"""Run the invoice-audit demo and write validated Parquet outputs."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

import extraer
import normalizar
import reglas
from schema.esquema import FINDINGS_SCHEMA, INVOICES_SCHEMA, validar


PROJECT_DIR = Path(__file__).resolve().parent


def build_table(rows: list[dict], schema: pa.Schema) -> pa.Table:
    columns = {
        field.name: [row.get(field.name) for row in rows]
        for field in schema
    }
    arrays = [pa.array(columns[field.name], type=field.type) for field in schema]
    return pa.Table.from_arrays(arrays, schema=schema)


def main() -> int:
    parser = argparse.ArgumentParser(description="Demonstration invoice-audit pipeline")
    parser.add_argument("--out", type=Path, default=Path("output"), help="output directory for Parquet files")
    parser.add_argument("--csv", type=Path, default=PROJECT_DIR / "data" / "facturas.csv", help="structured invoice CSV")
    parser.add_argument("--documents", type=Path, default=PROJECT_DIR / "data" / "documentos", help="sample email text files")
    parser.add_argument("--mock-llm", action="store_true", help="use local fixtures instead of the Anthropic API")
    args = parser.parse_args()

    if args.mock_llm:
        os.environ["MOCK_LLM"] = "1"

    try:
        structured = normalizar.leer_csv(args.csv)
        extracted = extraer.extraer_todos(args.documents)
        invoices, findings = reglas.evaluar_lote(structured + extracted)

        invoice_table = build_table(invoices, INVOICES_SCHEMA)
        finding_table = build_table(findings, FINDINGS_SCHEMA)
        invoice_issues = validar(invoice_table, INVOICES_SCHEMA)
        finding_issues = validar(finding_table, FINDINGS_SCHEMA)
        valid_ids = set(invoice_table.column("invoice_id").to_pylist())
        orphan_ids = sorted({row["invoice_id"] for row in findings if row["invoice_id"] not in valid_ids})
        if invoice_issues or finding_issues or orphan_ids:
            for issue in invoice_issues:
                print(f"[invoices] {issue}", file=sys.stderr)
            for issue in finding_issues:
                print(f"[findings] {issue}", file=sys.stderr)
            if orphan_ids:
                print(f"Orphan findings: {orphan_ids}", file=sys.stderr)
            return 1

        args.out.mkdir(parents=True, exist_ok=True)
        pq.write_table(invoice_table, args.out / "invoices.parquet")
        pq.write_table(finding_table, args.out / "findings.parquet")
        print(f"Processed {len(invoices)} invoices and {len(findings)} findings.")
        print(f"Schema validation passed. Parquet files written to {args.out.resolve()}")
        return 0
    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

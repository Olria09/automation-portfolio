"""Parquet output schemas and their local validator."""

import pyarrow as pa

CODES = [
    "INVALID_VAT", "ARITHMETIC_MISMATCH", "NUMBERING_GAP", "DUPLICATE_INVOICE",
    "PERIODO_CERRADO", "TIPO_IVA_INCORRECTO", "REVERSE_CHARGE_NOT_APPLIED",
    "DUPLICATE_CUSTOMER", "INCOMPLETE_DATA", "AMBIGUOUS_JURISDICTION",
]
SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
OPERATION_TYPES = ["DOMESTIC", "INTRA_EU_B2B", "OSS_B2C", "EXPORT", "IGIC",
                   "UNDETERMINED"]
SOURCES = ["STRUCTURED", "EXTRACTED"]

_EUR = pa.decimal128(12, 2)

INVOICES_SCHEMA = pa.schema([
    pa.field("invoice_id", pa.string(), nullable=False),
    pa.field("issue_date", pa.date32(), nullable=False),
    pa.field("customer_raw", pa.string(), nullable=False),
    pa.field("customer_normalized", pa.string(), nullable=False),
    pa.field("customer_country", pa.string(), nullable=False),
    pa.field("customer_vat", pa.string(), nullable=True),
    pa.field("taxable_base", _EUR, nullable=False),
    pa.field("vat_rate", pa.decimal128(5, 2), nullable=False),
    pa.field("vat_amount", _EUR, nullable=False),
    pa.field("total_amount", _EUR, nullable=False),
    pa.field("currency", pa.string(), nullable=False),
    pa.field("operation_type", pa.string(), nullable=False),
    pa.field("source", pa.string(), nullable=False),
])

FINDINGS_SCHEMA = pa.schema([
    pa.field("invoice_id", pa.string(), nullable=False),
    pa.field("code", pa.string(), nullable=False),
    pa.field("severity", pa.string(), nullable=False),
    pa.field("amount_at_risk_eur", _EUR, nullable=False),
    pa.field("field", pa.string(), nullable=True),
    pa.field("observed", pa.string(), nullable=True),
    pa.field("expected", pa.string(), nullable=True),
    pa.field("confidence", pa.float32(), nullable=False),
    pa.field("needs_human_review", pa.bool_(), nullable=False),
    pa.field("explanation", pa.string(), nullable=False),
])

_ENUMS = {"code": CODES, "severity": SEVERITIES,
          "operation_type": OPERATION_TYPES, "source": SOURCES}


def validar(tabla, schema):
    """Devuelve la lista de problemas de `tabla` frente a `schema`. [] = correcta."""
    problemas = []
    esperadas = [f.name for f in schema]
    if tabla.schema.names != esperadas:
        problemas.append(
            f"columnas: expected {esperadas}, encontrado {tabla.schema.names}")
    for f in schema:
        if f.name not in tabla.schema.names:
            continue
        col = tabla.column(f.name)
        if col.type != f.type:
            problemas.append(f"{f.name}: tipo expected {f.type}, encontrado {col.type}")
            continue
        if not f.nullable and col.null_count:
            problemas.append(f"{f.name}: {col.null_count} nulos y no admite nulos")
        if f.name in _ENUMS:
            malos = sorted({v for v in col.to_pylist() if v is not None}
                           - set(_ENUMS[f.name]))
            if malos:
                problemas.append(f"{f.name}: valores fuera del enum {malos}")
        if f.name == "confidence":
            fuera = [v for v in col.to_pylist() if v is not None and not 0.0 <= v <= 1.0]
            if fuera:
                problemas.append(f"confidence: valores fuera de [0,1] {fuera[:5]}")
    if schema is INVOICES_SCHEMA and "invoice_id" in tabla.schema.names:
        ids = tabla.column("invoice_id").to_pylist()
        dups = sorted({i for i in ids if ids.count(i) > 1})
        if dups:
            problemas.append(f"invoice_id: clave primaria duplicada {dups[:5]}")
    return problemas

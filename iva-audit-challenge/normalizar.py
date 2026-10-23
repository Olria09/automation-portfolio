"""Capa 1: CSV en español -> formato intermedio común (Parte A del reto).

Puramente mecánico: parseo de tipos, sin ninguna decisión fiscal (eso vive en
reglas.py). La única normalización de contenido que ocurre aquí es dejar
customer_vat como None cuando el CSV trae cadena vacía, para que el motor de
reglas no tenga que distinguir "" de None en dos sitios distintos.
"""

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path


def leer_csv(path: str | Path) -> list[dict]:
    """Lee facturas.csv y devuelve filas en el formato intermedio común,
    listas para pasar a reglas.evaluar_lote(). source siempre STRUCTURED."""
    filas = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            filas.append(dict(
                invoice_id=r["invoice_id"].strip(),
                issue_date=datetime.strptime(r["fecha_emision"].strip(), "%Y-%m-%d").date(),
                customer_raw=r["cliente_raw"].strip(),
                customer_country=(r["pais_cliente"].strip() or None),
                customer_vat=(r["vat_cliente"].strip() or None),
                taxable_base=Decimal(r["base_imponible"].strip()),
                vat_rate=Decimal(r["tipo_iva"].strip()),
                vat_amount=Decimal(r["cuota"].strip()),
                total_amount=Decimal(r["total"].strip()),
                currency=r["moneda"].strip(),
                source="STRUCTURED",
            ))
    return filas

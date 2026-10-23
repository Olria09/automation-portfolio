"""Motor de reglas: fiscalidad + calidad de datos. 100% determinista, sin LLM.

Recibe una lista de facturas ya normalizadas (misma forma venga del CSV o de un
email) y produce (invoices_rows, findings_rows) listas para construir las tablas
Parquet. No sabe ni le importa si una factura vino de STRUCTURED o EXTRACTED:
esa distinción vive solo en el campo `source` de cada fila, ya puesta por quien
la produjo (normalizar.py / extraer.py).

Cada factura de entrada es un dict con estas claves (todas ya tipadas):
    invoice_id: str
    issue_date: datetime.date
    customer_raw: str
    customer_country: str | None      # ISO 3166-1 alpha-2, o None si no se sabe
    customer_vat: str | None
    taxable_base: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total_amount: Decimal
    currency: str
    source: str                        # "STRUCTURED" | "EXTRACTED"

El motor añade: customer_normalized, operation_type, y todos los findings.
"""

from decimal import Decimal, ROUND_HALF_UP

from vat import valido, UE

# Canarias no tiene código ISO propio: lo detectamos por texto en la razón
# social / domicilio, tal como vienen en los datos de origen. Es una heurística
# del reto, no una regla robusta de producción.
_CANARIAS_HINTS = ("las palmas", "santa cruz de tenerife", "tenerife",
                    "gran canaria", "canarias")

# Reino Unido salió de la UE el 01/01/2021: todas las facturas de este
# ejercicio (2024) con cliente GB son EXPORT, nunca INTRA_EU_B2B, con
# independencia de que el VAT tenga o no formato de VAT británico.
_TIPOS_ES = {"general": Decimal("21.00"), "reducido": Decimal("10.00"),
             "superreducido": Decimal("4.00")}

_OSS_RATES = {"DE": Decimal("19.00"), "FR": Decimal("20.00"), "IT": Decimal("22.00"),
              "PT": Decimal("23.00"), "NL": Decimal("21.00"), "IE": Decimal("23.00")}

CENT = Decimal("0.01")


def _q(x) -> Decimal:
    """Cuantiza a centavo. Acepta float o Decimal de entrada (los floats del
    CSV/JSON se convierten vía str para no arrastrar el error binario)."""
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def es_canarias(texto: str) -> bool:
    t = (texto or "").lower()
    return any(h in t for h in _CANARIAS_HINTS)


def normalizar_nombre_cliente(nombre: str) -> str:
    """Forma canónica para agrupar el mismo cliente pese a variaciones de grafía.

    Estrategia deliberadamente simple: mayúsculas, colapsar espacios, quitar
    puntuación de abreviaturas societarias comunes (S.A. / S.L. / GmbH / B.V. /
    S.r.l. / Ltd / SARL / Lda) y el paréntesis de sede que aparece en dos
    clientes canarios. No es un matching difuso general: cubre los casos que
    aparecen en este dataset, documentado como supuesto.
    """
    import re
    n = nombre.strip()
    n = re.sub(r"\s*\([^)]*\)\s*$", "", n)          # quita "(Las Palmas...)" al final
    n = re.sub(r"[.\-]", "", n)                      # quita puntos y guiones
    n = re.sub(r"\s+", " ", n).strip()
    return n.upper()


def determinar_operacion(pais_cliente: str | None, vat_cliente: str | None,
                          vat_valido: bool | None):
    """Devuelve (operation_type, vat_rate_esperado_o_None, necesita_revision:bool).

    vat_rate_esperado es None cuando depende de una tabla de tipos reducidos
    españoles que no podemos inferir solo del país (ver ARITHMETIC_MISMATCH /
    TIPO_IVA_INCORRECTO más abajo, que comparan contra el tipo *declarado*
    cuando no hay un único tipo correcto posible).
    """
    if pais_cliente is None:
        return "UNDETERMINED", None, True

    if pais_cliente == "ES":
        return "DOMESTIC", None, False  # tipo depende del producto: 21/10/4, no inferible aquí

    if pais_cliente == "GB":
        return "EXPORT", Decimal("0.00"), False

    if pais_cliente in UE:
        if vat_cliente and vat_valido:
            return "INTRA_EU_B2B", Decimal("0.00"), False
        # UE sin VAT válido -> OSS B2C, tipo del país del cliente
        tipo = _OSS_RATES.get(pais_cliente)
        return "OSS_B2C", tipo, tipo is None

    # Fuera de la UE y no GB (ya cubierto) -> exportación
    return "EXPORT", Decimal("0.00"), False


def evaluar_factura(f: dict) -> tuple[dict, list[dict]]:
    """Procesa UNA factura ya normalizada. Devuelve (fila_invoice, [findings])."""
    findings = []
    inv_id = f["invoice_id"]

    pais = f.get("customer_country")
    vat_raw = f.get("customer_vat")
    es_canaria = es_canarias(f.get("customer_raw", "")) or pais == "IC"

    # --- 1. Validación de VAT ---------------------------------------------  EEK
    # Si el VAT tal cual no valida, se prueba una corrección de confusiones
    # típicas de OCR (O<->0, l/I<->1) antes de darlo por inválido. Si la
    # versión corregida sí valida, se usa esa como customer_vat definitivo y
    # se dejan ambos valores (observado/corregido) en el finding para que
    # quede constancia y no se pierda la trazabilidad del cambio.
    vat_ok = None
    if vat_raw:
        vat_ok = valido(vat_raw, pais) if pais else None
        if vat_ok is False and pais:
            corregido = (vat_raw.upper().replace("O", "0")
                         .replace("L", "1").replace("I", "1"))
            if corregido != vat_raw.upper() and valido(corregido, pais):
                findings.append(dict(
                    invoice_id=inv_id, code="INVALID_VAT", severity="LOW",
                    amount_at_risk_eur=Decimal("0.00"),
                    field="customer_vat", observed=vat_raw, expected=corregido,
                    confidence=0.7, needs_human_review=True,
                    explanation=("El NIF no valida tal como se transcribió, pero sí "
                                  "corrigiendo confusiones típicas de OCR (O/0, l/I/1). "
                                  "Se usa la versión corregida; confirmar contra el original."),
                ))
                vat_raw = corregido
                vat_ok = True
            else:
                findings.append(dict(
                    invoice_id=inv_id, code="INVALID_VAT", severity="HIGH",
                    amount_at_risk_eur=_q(f["total_amount"]),
                    field="customer_vat", observed=vat_raw, expected=None,
                    confidence=0.6 if f.get("source") == "EXTRACTED" else 1.0,
                    needs_human_review=(f.get("source") == "EXTRACTED"),
                    explanation=("El identificador fiscal del cliente no supera la "
                                  "validación de formato/dígito de control, ni siquiera "
                                  "tras corregir confusiones típicas de OCR. El documento "
                                  "de origen es un escaneo de baja calidad admitido como "
                                  "tal por el remitente: pedir el dato de nuevo antes de "
                                  "descartar la factura."
                                  if f.get("source") == "EXTRACTED" else
                                  "El identificador fiscal del cliente no supera la "
                                  "validación de formato/dígito de control."),
                ))
        elif vat_ok is False:
            findings.append(dict(
                invoice_id=inv_id, code="INVALID_VAT", severity="HIGH",
                amount_at_risk_eur=_q(f["total_amount"]),
                field="customer_vat", observed=vat_raw, expected=None,
                confidence=1.0, needs_human_review=False,
                explanation=("El identificador fiscal del cliente no supera la "
                              "validación de formato/dígito de control."),
            ))

    # --- 2. Determinar el régimen fiscal esperado --------------------------- EEK
    if es_canaria:
        operation_type = "IGIC"
        # IGIC no es IVA y no tenemos su tabla de tipos en el enunciado, así
        # que no podemos afirmar cuál es el tipo correcto -- ni siquiera
        # cuando el tipo observado ya es 0.00, porque eso podría ser
        # casualidad (factura sin IVA por otro motivo) en vez de una
        # aplicación deliberada de IGIC. Se marca SIEMPRE para revisión.
        findings.append(dict(
            invoice_id=inv_id, code="TIPO_IVA_INCORRECTO",
            severity="HIGH" if f["vat_rate"] != Decimal("0.00") else "MEDIUM",
            amount_at_risk_eur=_q(f["vat_amount"]),
            field="vat_rate", observed=str(f["vat_rate"]), expected="IGIC (no IVA peninsular)",
            confidence=0.7, needs_human_review=True,
            explanation=("Cliente en Canarias: aplica IGIC, no IVA peninsular. "
                          "No se dispone de la tabla de tipos IGIC para confirmar "
                          "si el importe repercutido es correcto; revisar manualmente."),
        ))
    else:
        operation_type, tipo_esperado, revisar = determinar_operacion(pais, vat_raw, vat_ok)

        if operation_type == "UNDETERMINED":
            findings.append(dict(
                invoice_id=inv_id, code="AMBIGUOUS_JURISDICTION", severity="MEDIUM",
                amount_at_risk_eur=_q(f["total_amount"]),
                field="customer_country", observed=str(pais), expected=None,
                confidence=0.5, needs_human_review=True,
                explanation="No se puede determinar el país del cliente ni, por tanto, el régimen fiscal aplicable.",
            ))
        elif operation_type == "INTRA_EU_B2B" and f["vat_rate"] != Decimal("0.00"):
            findings.append(dict(
                invoice_id=inv_id, code="REVERSE_CHARGE_NOT_APPLIED", severity="CRITICAL",
                amount_at_risk_eur=_q(f["vat_amount"]),
                field="vat_rate", observed=str(f["vat_rate"]), expected="0.00",
                confidence=1.0, needs_human_review=False,
                explanation=("Cliente UE con VAT válido: procedía inversión del "
                              "sujeto pasivo (0% IVA) y se aplicó tipo distinto."),
            ))
        elif operation_type == "OSS_B2C" and tipo_esperado is not None and f["vat_rate"] != tipo_esperado:
            findings.append(dict(
                invoice_id=inv_id, code="TIPO_IVA_INCORRECTO", severity="HIGH",
                amount_at_risk_eur=_q(abs(f["vat_amount"] - _q(f["taxable_base"] * tipo_esperado / 100))),
                field="vat_rate", observed=str(f["vat_rate"]), expected=str(tipo_esperado),
                confidence=0.85, needs_human_review=False,
                explanation=(f"Cliente UE (particular, régimen OSS) sin VAT válido: "
                              f"corresponde el tipo del país del cliente ({tipo_esperado}%)."),
            ))
        elif operation_type == "EXPORT" and f["vat_rate"] != Decimal("0.00"):
            findings.append(dict(
                invoice_id=inv_id, code="TIPO_IVA_INCORRECTO", severity="HIGH",
                amount_at_risk_eur=_q(f["vat_amount"]),
                field="vat_rate", observed=str(f["vat_rate"]), expected="0.00",
                confidence=0.9, needs_human_review=False,
                explanation="Cliente fuera de la UE (o Reino Unido, tras el Brexit): exportación, exenta de IVA.",
            ))
        elif revisar:
            findings.append(dict(
                invoice_id=inv_id, code="AMBIGUOUS_JURISDICTION", severity="LOW",
                amount_at_risk_eur=Decimal("0.00"),
                field="vat_rate", observed=str(f["vat_rate"]), expected=None,
                confidence=0.5, needs_human_review=True,
                explanation="Régimen fiscal determinado con baja certeza; confirmar manualmente.",
            ))

    # --- 3. Descuadre aritmético --------------------------------------------
    base, tipo, cuota, total = (_q(f["taxable_base"]), f["vat_rate"],
                                 _q(f["vat_amount"]), _q(f["total_amount"]))
    cuota_esperada = _q(base * tipo / 100)
    if abs(cuota - cuota_esperada) > CENT:
        findings.append(dict(
            invoice_id=inv_id, code="ARITHMETIC_MISMATCH", severity="HIGH",
            amount_at_risk_eur=_q(abs(cuota - cuota_esperada)),
            field="vat_amount", observed=str(cuota), expected=str(cuota_esperada),
            confidence=1.0, needs_human_review=False,
            explanation="La cuota de IVA no corresponde a base × tipo / 100.",
        ))
    if abs(total - _q(base + cuota)) > CENT:
        # En una factura EXTRACTED, un descuadre entre total y base+cuota
        # suele venir de que el documento de origen mezcla dos fuentes
        # humanas de importe (p. ej. un total confirmado de palabra frente a
        # un desglose escrito aparte) -- no de un error de captura como en el
        # CSV. Se marca así para revisión humana en vez de darlo por un
        # simple fallo aritmético cerrado.
        es_extraida = f.get("source") == "EXTRACTED"
        findings.append(dict(
            invoice_id=inv_id, code="ARITHMETIC_MISMATCH", severity="HIGH",
            amount_at_risk_eur=_q(abs(total - _q(base + cuota))),
            field="total_amount", observed=str(total), expected=str(_q(base + cuota)),
            confidence=0.6 if es_extraida else 1.0,
            needs_human_review=es_extraida,
            explanation=(
                "El documento de origen contiene un total que no coincide con "
                "la suma de base imponible y cuota de IVA que el propio "
                "documento reporta; es probable que existan dos fuentes de "
                "importe distintas (p. ej. lo confirmado de palabra frente a "
                "un desglose escrito). Confirmar el importe correcto antes de emitir."
                if es_extraida else
                "El total no corresponde a la suma de base imponible y cuota de IVA."
            ),
        ))

    # --- 4. Datos incompletos ------------------------------------------------
    if pais is None or f.get("customer_country") in (None, ""):
        findings.append(dict(
            invoice_id=inv_id, code="INCOMPLETE_DATA", severity="MEDIUM",
            amount_at_risk_eur=Decimal("0.00"),
            field="customer_country", observed=None, expected=None,
            confidence=0.9, needs_human_review=True,
            explanation="Falta el país del cliente, necesario para determinar el régimen fiscal.",
        ))
    if not vat_raw and pais and pais != "ES" and pais not in ("US",):
        # Fuera de España sin VAT: puede ser legítimo (particular / exportación
        # a país sin VAT) o un dato que falta. Se marca como revisión ligera,
        # no como error duro, salvo que ya haya findings más fuertes arriba.
        pass  # cubierto por AMBIGUOUS_JURISDICTION/OSS_B2C cuando aplica

    row = dict(
        invoice_id=inv_id,
        issue_date=f["issue_date"],
        customer_raw=f["customer_raw"],
        customer_normalized=normalizar_nombre_cliente(f["customer_raw"]),
        customer_country=pais or "",
        customer_vat=vat_raw,
        taxable_base=base,
        vat_rate=tipo,
        vat_amount=cuota,
        total_amount=total,
        currency=f["currency"],
        operation_type=operation_type,
        source=f["source"],
    )
    return row, findings

#EEK

def evaluar_lote(facturas: list[dict]) -> tuple[list[dict], list[dict]]:
    """Procesa todas las facturas + detecta problemas cruzados (duplicados,
    huecos de numeración, clientes duplicados) que no se pueden ver factura
    a factura."""
    invoice_rows = []
    all_findings = []

    for f in facturas:
        row, findings = evaluar_factura(f)
        invoice_rows.append(row)
        all_findings.extend(findings)

    # --- DUPLICATE_INVOICE: mismo cliente + misma fecha + mismo importe -----
    vistos = {}
    for row in invoice_rows:
        clave = (row["customer_normalized"], row["issue_date"], row["total_amount"])
        vistos.setdefault(clave, []).append(row["invoice_id"])
    for clave, ids in vistos.items():
        if len(ids) > 1:
            for dup_id in ids[1:]:  # la primera se considera "original"
                all_findings.append(dict(
                    invoice_id=dup_id, code="DUPLICATE_INVOICE", severity="CRITICAL",
                    amount_at_risk_eur=_q(next(r["total_amount"] for r in invoice_rows if r["invoice_id"] == dup_id)),
                    field="invoice_id", observed=dup_id, expected=ids[0],
                    confidence=0.8, needs_human_review=True,
                    explanation=(f"Mismo cliente, fecha e importe que {ids[0]}: "
                                  "posible factura emitida por duplicado."),
                ))

    # --- NUMBERING_GAP: demo sequence INV-2024-NNNN -------------------------
    import re
    numeros = []
    for row in invoice_rows:
        m = re.fullmatch(r"INV-2024-(\d+)", row["invoice_id"])
        if m:
            numeros.append((int(m.group(1)), row["invoice_id"]))
    numeros.sort()
    for (n_prev, _), (n_next, id_next) in zip(numeros, numeros[1:]):
        if n_next - n_prev > 1:
            for faltante in range(n_prev + 1, n_next):
                all_findings.append(dict(
                    invoice_id=id_next, code="NUMBERING_GAP", severity="MEDIUM",
                    amount_at_risk_eur=Decimal("0.00"),
                    field="invoice_id", observed=f"INV-2024-{faltante:04d}", expected=None,
                    confidence=1.0, needs_human_review=True,
                    explanation=(f"Hueco en la numeración: falta INV-2024-{faltante:04d}. "
                                  f"Imputado a {id_next}, la siguiente factura existente."),
                ))

    # --- DUPLICATE_CUSTOMER: mismo VAT, distinta grafía cruda ----------------
    # Se agrupa por VAT (identificador estable) y se compara customer_raw
    # -- no customer_normalized, que por construcción ya coincide para todas
    # las grafías del mismo cliente y nunca dispararía nada.
    por_vat = {}
    for row in invoice_rows:
        if row["customer_vat"]:
            por_vat.setdefault(row["customer_vat"], set()).add(row["customer_raw"])
    for vat_id, grafias_crudas in por_vat.items():
        if len(grafias_crudas) > 1:
            forma_canonica = sorted(grafias_crudas)[0]
            for row in invoice_rows:
                if row["customer_vat"] == vat_id:
                    all_findings.append(dict(
                        invoice_id=row["invoice_id"], code="DUPLICATE_CUSTOMER", severity="LOW",
                        amount_at_risk_eur=Decimal("0.00"),
                        field="customer_raw", observed=row["customer_raw"], expected=row["customer_normalized"],
                        confidence=0.9, needs_human_review=False,
                        explanation=(f"Mismo VAT ({vat_id}) registrado con grafías distintas: "
                                      f"{', '.join(sorted(g.strip() for g in grafias_crudas))}."),
                    ))

    return invoice_rows, all_findings

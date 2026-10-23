"""Validacion de identificadores fiscales: formato + digito de control, en local.

Te lo damos hecho: implementar los algoritmos de siete paises es trabajo mecanico
que no es lo que evaluamos. Uso:

    from vat import valido, limpiar, UE
    valido("DE811925031", "DE")   -> False   (digito de control incorrecto)
    valido("ESB45190287", "ES")   -> True
    limpiar("ES-B45190287", "ES") -> "B45190287"
    "PT" in UE                    -> True

Cubre ES, DE, FR, IT, PT, NL, IE y GB. Para un pais sin validador devuelve True:
preferimos no afirmar que algo es invalido cuando no podemos comprobarlo.
Puedes usarlo tal cual, ampliarlo o sustituirlo.
"""
import re

UE = {"ES", "DE", "FR", "IT", "PT", "NL", "IE", "BE", "AT", "SE", "DK", "PL", "FI", "GR", "LU"}


def limpiar(vat, pais):
    """Quita separadores y el prefijo de pais redundante: 'ES-B45190287' -> 'B45190287'."""
    v = re.sub(r"[\s.\-/]", "", (vat or "")).upper()
    return v[2:] if v[:2] == pais else v


def _es(v):
    if not re.fullmatch(r"[A-Z0-9]\d{7}[A-Z0-9]", v):
        return False
    if re.fullmatch(r"\d{8}[A-Z]", v):                      # NIF persona fisica
        return v[8] == "TRWAGMYFPDXBNJZSQVHLCKE"[int(v[:8]) % 23]
    pares = sum(int(d) for d in v[2:8:2])                   # CIF sociedad
    impares = sum(sum(divmod(int(d) * 2, 10)) for d in v[1:8:2])
    c = (10 - (pares + impares) % 10) % 10
    return v[8] == str(c) or v[8] == "JABCDEFGHI"[c]


def _de(v):
    if not re.fullmatch(r"\d{9}", v):
        return False
    p = 10
    for d in v[:8]:
        m = (int(d) + p) % 10 or 10
        p = (2 * m) % 11
    return int(v[8]) == (11 - p) % 10


def _fr(v):
    if not re.fullmatch(r"[A-Z0-9]{2}\d{9}", v):
        return False
    if not v[:2].isdigit():                                 # clave alfabetica: no verificable en local
        return True
    return int(v[:2]) == (12 + 3 * (int(v[2:]) % 97)) % 97


def _it(v):
    if not re.fullmatch(r"\d{11}", v):
        return False
    s = sum(int(d) for d in v[:10:2]) + sum(sum(divmod(int(d) * 2, 10)) for d in v[1:10:2])
    return int(v[10]) == (10 - s % 10) % 10


def _pt(v):
    if not re.fullmatch(r"\d{9}", v):
        return False
    c = 11 - sum(int(d) * (9 - i) for i, d in enumerate(v[:8])) % 11
    return int(v[8]) == (0 if c >= 10 else c)


def _nl(v):
    if not re.fullmatch(r"\d{9}B\d{2}", v):
        return False
    return sum(int(d) * (9 - i) for i, d in enumerate(v[:8])) % 11 == int(v[8])


def _ie(v):
    return bool(re.fullmatch(r"\d{7}[A-W][A-IW]?|\d[A-Z+*]\d{5}[A-W]", v))


def _gb(v):
    return bool(re.fullmatch(r"\d{9}|\d{12}|(GD|HA)\d{3}", v))


VALIDADORES = {"ES": _es, "DE": _de, "FR": _fr, "IT": _it,
               "PT": _pt, "NL": _nl, "IE": _ie, "GB": _gb}


def valido(vat, pais):
    """True/False. Si no hay validador para el pais, no afirmamos que sea invalido."""
    v = limpiar(vat, pais)
    if not v:
        return False
    return VALIDADORES.get(pais, lambda _: True)(v)

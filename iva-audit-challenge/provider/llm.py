"""Proveedor LLM para la prueba. Una sola función pública: `completar`.

    from provider.llm import completar

    texto = completar(f"Extrae los campos de la factura de doc3:\\n{contenido}")

Con `MOCK_LLM=1` no se llama a la red: se busca `doc1`..`doc4` en el prompt y se
devuelve la respuesta grabada en `provider/fixtures/docN.json`.
El prompt debe mencionar el documento para que se pueda localizar su fixture.

Sin `MOCK_LLM` se llama a la API de Anthropic (modelo `claude-haiku-4-5`) leyendo
`ANTHROPIC_API_KEY` del entorno. Si se pasa `schema`, se usa como JSON Schema de
structured outputs. En ambos modos se devuelve el texto crudo de la respuesta:
puede no ser JSON válido, es parte del ejercicio.
"""

import os
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MODELO = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
DOCUMENTOS = ("doc1", "doc2", "doc3", "doc4")


def completar(prompt: str, schema: dict | None = None) -> str:
    """Devuelve la respuesta del modelo (o la fixture grabada) como texto."""
    if os.environ.get("MOCK_LLM", "") not in ("", "0"):
        for nombre in DOCUMENTOS:
            if nombre in prompt:
                return (FIXTURES / f"{nombre}.json").read_text(encoding="utf-8")
        raise ValueError(
            "MOCK_LLM está activo pero el prompt no menciona ningún documento: "
            "debe contener 'doc1', 'doc2', 'doc3' o 'doc4' para localizar su fixture en "
            f"{FIXTURES}. Incluye el nombre del documento en el prompt."
        )

    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Set ANTHROPIC_API_KEY or run with MOCK_LLM=1 for offline fixtures.")
    cliente = anthropic.Anthropic(api_key=api_key)
    extra: dict = {}
    if schema is not None:
        extra["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        **extra,
    )
    return "".join(b.text for b in respuesta.content if b.type == "text")

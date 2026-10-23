import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os
import unittest
from pathlib import Path
from unittest.mock import patch

import extraer
import normalizar
import reglas


ROOT = Path(__file__).resolve().parents[1]


class InvoicePipelineTests(unittest.TestCase):
    def test_mock_pipeline_is_local_and_processes_synthetic_records(self):
        with patch.dict(os.environ, {"MOCK_LLM": "1"}):
            structured = normalizar.leer_csv(ROOT / "data" / "facturas.csv")
            extracted = extraer.extraer_todos(ROOT / "data" / "documentos")
        invoices, findings = reglas.evaluar_lote(structured + extracted)

        self.assertEqual(len(invoices), 7)
        self.assertIn("INV-2024-0007", {row["invoice_id"] for row in invoices})
        self.assertTrue(all(row["invoice_id"].startswith("INV-2024-") for row in invoices))
        codes = {finding["code"] for finding in findings}
        self.assertTrue({"NUMBERING_GAP", "DUPLICATE_INVOICE", "INVALID_VAT"}.issubset(codes))
        self.assertFalse(any("4111" in str(row) for row in invoices + findings))

    def test_parser_accepts_prose_and_trailing_comma(self):
        parsed = extraer._parsear_respuesta('Result: ```json\n{"invoice_id":"INV-1",}\n```')
        self.assertEqual(parsed, {"invoice_id": "INV-1"})


if __name__ == "__main__":
    unittest.main()

import unittest
from backend.app.services.integrations.sheets_exporter import GoogleSheetsExporter, sheets_exporter

class TestGoogleSheetsExporter(unittest.TestCase):
    def setUp(self):
        self.exporter = GoogleSheetsExporter()

    def test_generate_nifty_sheet_matrix(self):
        matrix = self.exporter.generate_sheet_matrix(
            underlying="NIFTY",
            expiry="26MAR2026",
            strike_window=5,
            exchange="NFO"
        )
        self.assertEqual(matrix["underlying"], "NIFTY")
        self.assertEqual(matrix["exchange"], "NFO")
        self.assertGreater(matrix["total_rows"], 5)
        self.assertEqual(matrix["columns_count"], 17)

        # Verify header row
        headers = matrix["values"][0]
        self.assertEqual(headers[0], "CE OI")
        self.assertEqual(headers[8], "STRIKE")
        self.assertEqual(headers[16], "PE OI")

        # Verify formulas in totals row
        totals_row = matrix["values"][-2]
        self.assertTrue(totals_row[0].startswith("=SUM("))
        self.assertEqual(totals_row[8], "TOTALS / RATIOS")

        # Verify dynamic PCR formula row
        pcr_row = matrix["values"][-1]
        self.assertTrue(pcr_row[0].startswith("=Q"))
        self.assertEqual(pcr_row[1], "PCR (PE OI / CE OI)")

    def test_generate_crudeoil_sheet_matrix(self):
        matrix = self.exporter.generate_sheet_matrix(
            underlying="CRUDEOIL",
            expiry="19FEB2026",
            strike_window=4,
            exchange="MCX"
        )
        self.assertEqual(matrix["underlying"], "CRUDEOIL")
        self.assertEqual(matrix["exchange"], "MCX")
        self.assertGreater(matrix["total_rows"], 4)
        
        # Check that strike values are in sorted order
        strikes = [row[8] for row in matrix["values"][1:-2]]
        self.assertEqual(strikes, sorted(strikes))

    def test_sync_to_sheet_payload(self):
        result = self.exporter.sync_to_sheet(
            spreadsheet_id="test-spreadsheet-12345",
            sheet_tab_name="LiveNifty",
            underlying="NIFTY",
            expiry="26MAR2026"
        )
        self.assertEqual(result.spreadsheet_id, "test-spreadsheet-12345")
        self.assertEqual(result.sheet_tab_name, "LiveNifty")
        self.assertEqual(result.underlying, "NIFTY")
        self.assertEqual(result.status, "success")
        self.assertGreater(result.synced_rows_count, 0)

        # Dictionary serialization
        d = result.to_dict()
        self.assertEqual(d["spreadsheet_id"], "test-spreadsheet-12345")
        self.assertEqual(d["status"], "success")

if __name__ == "__main__":
    unittest.main()

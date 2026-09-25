import unittest
from backend.app.services.analytics.option_chain_builder import OptionChainBuilder, option_chain_builder

class TestOptionChainBuilder(unittest.TestCase):
    def setUp(self):
        self.builder = OptionChainBuilder(default_strike_window=5)

    def test_option_chain_build_crudeoil(self):
        matrix = self.builder.build("CRUDEOIL", expiry="19FEB2026", strike_window=3, exchange="MCX")
        self.assertIsNotNone(matrix)
        summary = matrix.summary
        self.assertEqual(summary.underlying, "CRUDEOIL")
        self.assertEqual(summary.exchange, "MCX")
        self.assertEqual(summary.lot_size, 100)
        self.assertEqual(summary.atm_strike, 8900.0)
        self.assertEqual(len(matrix.rows), 7)  # 3 below + ATM + 3 above = 7 strikes

        # Verify ascending strike sort order
        strikes = [r.strike for r in matrix.rows]
        self.assertEqual(strikes, sorted(strikes))

        # Check ATM row
        atm_row = next((r for r in matrix.rows if r.is_atm), None)
        self.assertIsNotNone(atm_row)
        self.assertEqual(atm_row.strike, 8900.0)
        self.assertIsNotNone(atm_row.call)
        self.assertIsNotNone(atm_row.put)
        self.assertEqual(atm_row.call.token, "MCX_CRUDE_8900_CE")
        self.assertEqual(atm_row.put.token, "MCX_CRUDE_8900_PE")

    def test_moneyness_classification(self):
        matrix = self.builder.build("CRUDEOIL", expiry="19FEB2026", strike_window=3, exchange="MCX")
        
        # Spot is 8908.0
        # ATM: 8900
        atm_row = next(r for r in matrix.rows if r.strike == 8900.0)
        self.assertEqual(atm_row.call.moneyness, "ATM")
        self.assertEqual(atm_row.put.moneyness, "ATM")

        # ITM Call / OTM Put: strike 8800 (< spot 8908)
        itm_call_row = next(r for r in matrix.rows if r.strike == 8800.0)
        self.assertEqual(itm_call_row.call.moneyness, "ITM")
        self.assertEqual(itm_call_row.put.moneyness, "OTM")

        # OTM Call / ITM Put: strike 9000 (> spot 8908)
        otm_call_row = next(r for r in matrix.rows if r.strike == 9000.0)
        self.assertEqual(otm_call_row.call.moneyness, "OTM")
        self.assertEqual(otm_call_row.put.moneyness, "ITM")

    def test_option_chain_aggregations(self):
        matrix = self.builder.build("CRUDEOIL", expiry="19FEB2026", strike_window=5, exchange="MCX")
        summary = matrix.summary

        self.assertGreater(summary.total_call_oi, 0)
        self.assertGreater(summary.total_put_oi, 0)
        self.assertGreater(summary.total_call_volume, 0)
        self.assertGreater(summary.total_put_volume, 0)

        # PCR check
        expected_pcr = round(summary.total_put_oi / summary.total_call_oi, 4)
        self.assertEqual(summary.pcr, expected_pcr)

        # Max OI strikes check
        self.assertIsNotNone(summary.max_call_oi_strike)
        self.assertIsNotNone(summary.max_put_oi_strike)

    def test_option_chain_nifty(self):
        matrix = self.builder.build("NIFTY", expiry="26MAR2026", strike_window=2, exchange="NFO")
        self.assertIsNotNone(matrix)
        self.assertEqual(matrix.summary.underlying, "NIFTY")
        self.assertEqual(matrix.summary.exchange, "NFO")
        self.assertEqual(matrix.summary.lot_size, 25)
        self.assertEqual(matrix.summary.atm_strike, 23000.0)
        self.assertTrue(len(matrix.rows) <= 5)

        for row in matrix.rows:
            self.assertIsNotNone(row.call)
            self.assertIsNotNone(row.put)
            self.assertGreater(row.call.ltp, 0)
            self.assertGreater(row.put.ltp, 0)

    def test_matrix_serialization_to_dict(self):
        matrix = self.builder.build("CRUDEOIL", expiry="19FEB2026", strike_window=2, exchange="MCX")
        d = matrix.to_dict()
        self.assertIn("summary", d)
        self.assertIn("rows", d)
        self.assertEqual(len(d["rows"]), len(matrix.rows))
        self.assertIn("pcr", d["summary"])
        self.assertIn("spot_price", d["summary"])
        self.assertIn("strike", d["rows"][0])
        self.assertIn("call", d["rows"][0])
        self.assertIn("put", d["rows"][0])

if __name__ == "__main__":
    unittest.main()

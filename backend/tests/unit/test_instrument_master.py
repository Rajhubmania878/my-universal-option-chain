import unittest
from backend.app.services.angel.instrument_master import InstrumentMasterService, Instrument

class TestInstrumentMaster(unittest.TestCase):
    def setUp(self):
        self.service = InstrumentMasterService()

    def test_dynamic_underlyings_discovery(self):
        underlyings = self.service.get_supported_underlyings()
        symbols = [u["symbol"] for u in underlyings]
        
        # Verify indices, commodities, and equities are present
        self.assertIn("NIFTY", symbols)
        self.assertIn("BANKNIFTY", symbols)
        self.assertIn("FINNIFTY", symbols)
        self.assertIn("CRUDEOIL", symbols)
        self.assertIn("GOLD", symbols)
        self.assertIn("SILVER", symbols)
        self.assertIn("RELIANCE", symbols)

    def test_dynamic_expiries_discovery_and_sorting(self):
        # Expiries should be discovered dynamically and sorted
        nifty_exps = self.service.get_expiries("NIFTY", "NFO")
        self.assertTrue(len(nifty_exps) >= 2)
        # Verify chronological order
        self.assertEqual(nifty_exps[0], "26MAR2026")
        self.assertEqual(nifty_exps[1], "02APR2026")

        crude_exps = self.service.get_expiries("CRUDEOIL", "MCX")
        self.assertIn("19FEB2026", crude_exps)

    def test_dynamic_strikes_discovery_and_sorting(self):
        strikes = self.service.get_strikes("NIFTY", "26MAR2026", "NFO")
        self.assertTrue(len(strikes) > 5)
        # Verify sorted ascending
        self.assertEqual(strikes, sorted(strikes))
        self.assertIn(22000.0, strikes)
        self.assertIn(23000.0, strikes)

    def test_option_contract_lookup(self):
        ce_contract = self.service.get_option_contract("NIFTY", "26MAR2026", 23000.0, "CE", "NFO")
        self.assertIsNotNone(ce_contract)
        self.assertEqual(ce_contract.name, "NIFTY")
        self.assertEqual(ce_contract.strike, 23000.0)
        self.assertEqual(ce_contract.option_type, "CE")
        self.assertEqual(ce_contract.lotsize, 25)

        pe_contract = self.service.get_option_contract("NIFTY", "26MAR2026", 23000.0, "PE", "NFO")
        self.assertIsNotNone(pe_contract)
        self.assertEqual(pe_contract.option_type, "PE")
        self.assertNotEqual(ce_contract.token, pe_contract.token)

    def test_mcx_crudeoil_support(self):
        crude_matrix = self.service.get_option_chain_tokens("CRUDEOIL", "19FEB2026", "MCX")
        self.assertTrue(len(crude_matrix) > 0)
        
        # Check an ATM strike like 8900
        row_8900 = next((r for r in crude_matrix if r["strike"] == 8900.0), None)
        self.assertIsNotNone(row_8900)
        self.assertEqual(row_8900["lot_size"], 100)
        self.assertEqual(row_8900["tick_size"], 1.0)
        self.assertEqual(row_8900["exchange"], "MCX")
        self.assertEqual(row_8900["ce_token"], "MCX_CRUDE_8900_CE")
        self.assertEqual(row_8900["pe_token"], "MCX_CRUDE_8900_PE")

    def test_equity_fno_reliance(self):
        rel_strikes = self.service.get_strikes("RELIANCE", "26MAR2026", "NFO")
        self.assertIn(3000.0, rel_strikes)
        
        ce_rel = self.service.get_option_contract("RELIANCE", "26MAR2026", 3000.0, "CE", "NFO")
        self.assertIsNotNone(ce_rel)
        self.assertEqual(ce_rel.lotsize, 250)
        self.assertEqual(ce_rel.instrumenttype, "OPTSTK")

    def test_token_lookup_and_search(self):
        inst = self.service.get_instrument_by_token("MCX_CRUDE_8900_CE")
        self.assertIsNotNone(inst)
        self.assertEqual(inst.symbol, "CRUDEOIL19FEB268900CE")
        self.assertEqual(inst.strike, 8900.0)

        # Search query
        results = self.service.search("CRUDEOIL", limit=5)
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["name"], "CRUDEOIL")

    def test_strike_normalization(self):
        # 2300000 in NFO should scale down to 23000.0
        normalized = self.service._normalize_strike("2300000.000000", "NFO", "NIFTY26MAR2623000CE")
        self.assertEqual(normalized, 23000.0)

        # 8900 in MCX should remain 8900.0
        normalized_mcx = self.service._normalize_strike("8900.000000", "MCX", "CRUDEOIL19FEB268900CE")
        self.assertEqual(normalized_mcx, 8900.0)

if __name__ == "__main__":
    unittest.main()

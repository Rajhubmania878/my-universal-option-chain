import unittest
from backend.app.services.analytics.straddle_engine import StraddleEngine, straddle_engine

class TestStraddleEngine(unittest.TestCase):
    def setUp(self):
        self.engine = StraddleEngine()

    def test_atm_straddle_calculation_crudeoil(self):
        straddle = self.engine.calculate_atm_straddle("CRUDEOIL", expiry="19FEB2026", exchange="MCX")
        self.assertEqual(straddle.underlying, "CRUDEOIL")
        self.assertEqual(straddle.expiry, "19FEB2026")
        self.assertEqual(straddle.lot_size, 100)
        self.assertEqual(straddle.strike, 8900.0)

        # Call + Put = Straddle Premium
        self.assertAlmostEqual(straddle.straddle_premium, straddle.call_ltp + straddle.put_ltp, places=2)
        self.assertGreater(straddle.straddle_premium, 0.0)

        # Lot cost
        self.assertAlmostEqual(straddle.straddle_lot_cost, straddle.straddle_premium * 100, places=2)

    def test_straddle_breakevens_and_implied_move(self):
        straddle = self.engine.calculate_atm_straddle("CRUDEOIL", expiry="19FEB2026", exchange="MCX")
        
        # Lower BE = Strike - Premium
        self.assertAlmostEqual(straddle.lower_breakeven, straddle.strike - straddle.straddle_premium, places=2)

        # Upper BE = Strike + Premium
        self.assertAlmostEqual(straddle.upper_breakeven, straddle.strike + straddle.straddle_premium, places=2)

        # Implied Move % = (Premium / Spot) * 100
        expected_move = round((straddle.straddle_premium / straddle.spot_price) * 100.0, 2)
        self.assertAlmostEqual(straddle.implied_move_pct, expected_move, places=2)
        self.assertGreater(straddle.implied_move_pct, 0.0)

    def test_combined_greeks_straddle(self):
        straddle = self.engine.calculate_atm_straddle("NIFTY", expiry="26MAR2026", exchange="NFO")
        greeks = straddle.combined_greeks

        # Net Delta should be near 0 for ATM straddle (Call ~0.5, Put ~ -0.5)
        self.assertAlmostEqual(greeks.net_delta, 0.0, delta=0.25)

        # Net Gamma is positive (double long option gamma)
        self.assertGreater(greeks.net_gamma, 0.0)

        # Net Theta is negative (accelerated time decay)
        self.assertLess(greeks.net_theta, 0.0)

        # Net Vega is positive (double long option vega)
        self.assertGreater(greeks.net_vega, 0.0)

    def test_strangle_configurations(self):
        strangle = self.engine.calculate_strangle("CRUDEOIL", expiry="19FEB2026", otm_offset=1, exchange="MCX")
        self.assertEqual(strangle.underlying, "CRUDEOIL")
        self.assertGreater(strangle.call_strike, strangle.put_strike)
        self.assertEqual(strangle.strike_width, strangle.call_strike - strangle.put_strike)

        # Lower BE = Put Strike - Premium, Upper BE = Call Strike + Premium
        self.assertAlmostEqual(strangle.lower_breakeven, strangle.put_strike - strangle.strangle_premium, places=2)
        self.assertAlmostEqual(strangle.upper_breakeven, strangle.call_strike + strangle.strangle_premium, places=2)

        # Strangle premium should be less than ATM straddle premium
        atm_straddle = self.engine.calculate_atm_straddle("CRUDEOIL", expiry="19FEB2026", exchange="MCX")
        self.assertLess(strangle.strangle_premium, atm_straddle.straddle_premium)

    def test_multi_strike_comparison_table(self):
        analysis = self.engine.multi_strike_comparison("CRUDEOIL", expiry="19FEB2026", strike_window=3, exchange="MCX")
        self.assertEqual(analysis.underlying, "CRUDEOIL")
        self.assertGreater(len(analysis.rows), 0)
        self.assertIsNotNone(analysis.cheapest_straddle_strike)
        self.assertIsNotNone(analysis.max_oi_strike)

        for row in analysis.rows:
            self.assertAlmostEqual(row.straddle_premium, row.call_ltp + row.put_ltp, places=2)
            self.assertEqual(row.total_oi, row.call_oi + row.put_oi)
            self.assertGreaterEqual(row.pcr, 0.0)
            self.assertGreater(row.implied_move_pct, 0.0)

    def test_strangle_wider_offset(self):
        strangle_1 = self.engine.calculate_strangle("NIFTY", expiry="26MAR2026", otm_offset=1, exchange="NFO")
        strangle_2 = self.engine.calculate_strangle("NIFTY", expiry="26MAR2026", otm_offset=2, exchange="NFO")

        self.assertGreater(strangle_2.strike_width, strangle_1.strike_width)
        # Wider strangle premium should be cheaper than narrower strangle
        self.assertLess(strangle_2.strangle_premium, strangle_1.strangle_premium)

if __name__ == "__main__":
    unittest.main()

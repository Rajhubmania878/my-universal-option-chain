import unittest
from backend.app.services.analytics.vol_arbitrage_engine import (
    VolatilityArbitrageEngine,
    volatility_arbitrage_engine
)


class TestVolatilityArbitrageEngine(unittest.TestCase):
    def setUp(self):
        self.engine = VolatilityArbitrageEngine()

    def test_calendar_spread_scanner(self):
        results = self.engine.scan_calendar_spreads(
            underlying="CRUDEOIL",
            spot=8908.0,
            strikes=[8800.0, 8900.0, 9000.0]
        )
        self.assertEqual(len(results), 3)
        item = results[1]
        self.assertEqual(item.underlying, "CRUDEOIL")
        self.assertEqual(item.strike, 8900.0)
        self.assertGreater(item.near_iv, 0)
        self.assertGreater(item.far_iv, 0)
        self.assertIsNotNone(item.net_theta_per_day)
        self.assertIsNotNone(item.net_vega)

        d = item.to_dict()
        self.assertIn("spread_id", d)
        self.assertIn("roi_potential_pct", d)

    def test_parity_arbitrage_scanner(self):
        signals = self.engine.scan_parity_arbitrage(
            underlying="CRUDEOIL",
            spot=8908.0,
            strikes=[8900.0]
        )
        self.assertGreaterEqual(len(signals), 1)
        sig = signals[0]
        self.assertEqual(sig.strike, 8900.0)
        self.assertIn(sig.arbitrage_type, ["CONVERSION", "REVERSAL", "NONE", "BOX_SPREAD"])
        self.assertIsNotNone(sig.synthetic_futures_price)

        d = sig.to_dict()
        self.assertIn("signal_id", d)
        self.assertIn("annualized_yield_pct", d)


if __name__ == '__main__':
    unittest.main()

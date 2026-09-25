import unittest
from backend.app.services.analytics.buildup_tracker import BuildupTracker, buildup_tracker

class TestBuildupTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = BuildupTracker()

    def test_buildup_classification_matrix(self):
        # 1. Price UP + OI UP -> Long Buildup (Bullish)
        t1, b1 = self.tracker.classify_buildup(12.5, 1500)
        self.assertEqual(t1, "Long Buildup")
        self.assertEqual(b1, "Bullish")

        # 2. Price DOWN + OI UP -> Short Buildup (Bearish)
        t2, b2 = self.tracker.classify_buildup(-8.0, 3200)
        self.assertEqual(t2, "Short Buildup")
        self.assertEqual(b2, "Bearish")

        # 3. Price DOWN + OI DOWN -> Long Unwinding (Bearish)
        t3, b3 = self.tracker.classify_buildup(-15.0, -2100)
        self.assertEqual(t3, "Long Unwinding")
        self.assertEqual(b3, "Bearish")

        # 4. Price UP + OI DOWN -> Short Covering (Bullish)
        t4, b4 = self.tracker.classify_buildup(25.0, -1800)
        self.assertEqual(t4, "Short Covering")
        self.assertEqual(b4, "Bullish")

        # 5. Low fluctuation threshold -> Neutral
        t5, b5 = self.tracker.classify_buildup(0.01, 2)
        self.assertEqual(t5, "Neutral")
        self.assertEqual(b5, "Neutral")

    def test_nifty_buildup_analysis(self):
        analysis = self.tracker.analyze_buildup("NIFTY", expiry="26MAR2026", strike_window=5, exchange="NFO")
        self.assertEqual(analysis.underlying, "NIFTY")
        self.assertGreater(analysis.spot_price, 0.0)
        self.assertGreater(len(analysis.contracts), 0)

        # Check summary properties
        s = analysis.summary
        self.assertGreaterEqual(s.total_long_buildup, 0)
        self.assertGreaterEqual(s.total_short_buildup, 0)
        self.assertGreaterEqual(s.total_long_unwinding, 0)
        self.assertGreaterEqual(s.total_short_covering, 0)
        self.assertIn(s.dominant_market_bias, ["Bullish", "Bearish", "Indecisive"])

        # Check top ranking lists
        self.assertLessEqual(len(analysis.top_oi_gainers), 5)
        self.assertLessEqual(len(analysis.top_oi_losers), 5)
        self.assertLessEqual(len(analysis.top_volume_actives), 5)

    def test_crudeoil_buildup_analysis(self):
        analysis = self.tracker.analyze_buildup("CRUDEOIL", expiry="19FEB2026", strike_window=5, exchange="MCX")
        self.assertEqual(analysis.underlying, "CRUDEOIL")
        self.assertEqual(analysis.exchange, "MCX")
        self.assertGreater(len(analysis.contracts), 0)

        for c in analysis.contracts:
            self.assertIn(c.option_type, ["CE", "PE"])
            self.assertIn(c.buildup_type, ["Long Buildup", "Short Buildup", "Long Unwinding", "Short Covering", "Neutral"])
            self.assertIn(c.bias, ["Bullish", "Bearish", "Neutral"])

    def test_serialization_to_dict(self):
        analysis = self.tracker.analyze_buildup("CRUDEOIL", expiry="19FEB2026", strike_window=3, exchange="MCX")
        d = analysis.to_dict()
        self.assertEqual(d["underlying"], "CRUDEOIL")
        self.assertIn("summary", d)
        self.assertIn("dominant_market_bias", d["summary"])
        self.assertIn("top_oi_gainers", d)
        self.assertIn("top_volume_actives", d)

if __name__ == "__main__":
    unittest.main()

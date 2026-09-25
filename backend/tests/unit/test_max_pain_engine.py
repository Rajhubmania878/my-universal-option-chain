import unittest
from backend.app.services.analytics.max_pain_engine import MaxPainEngine, max_pain_engine

class TestMaxPainEngine(unittest.TestCase):
    def setUp(self):
        self.engine = MaxPainEngine()

    def test_max_pain_calculation_crudeoil(self):
        result = self.engine.calculate_max_pain("CRUDEOIL", expiry="19FEB2026", exchange="MCX")
        self.assertEqual(result.underlying, "CRUDEOIL")
        self.assertEqual(result.expiry, "19FEB2026")
        self.assertEqual(result.exchange, "MCX")
        self.assertIsNotNone(result.max_pain_strike)
        self.assertGreater(result.max_pain_strike, 0.0)

        # Max Pain strike must be present within loss curve strikes
        curve_strikes = [p.strike for p in result.loss_curve]
        self.assertIn(result.max_pain_strike, curve_strikes)

        # The loss at max pain strike must indeed be minimal across all points in loss curve
        mp_point = next(p for p in result.loss_curve if p.strike == result.max_pain_strike)
        for point in result.loss_curve:
            self.assertGreaterEqual(point.total_loss, mp_point.total_loss)

    def test_max_pain_calculation_nifty(self):
        result = self.engine.calculate_max_pain("NIFTY", expiry="26MAR2026", exchange="NFO")
        self.assertEqual(result.underlying, "NIFTY")
        self.assertGreater(result.spot_price, 0.0)
        self.assertIsNotNone(result.distance_to_spot)
        self.assertIsNotNone(result.distance_pct)
        self.assertGreater(len(result.loss_curve), 0)

    def test_pcr_suite_metrics(self):
        result = self.engine.calculate_max_pain("NIFTY", expiry="26MAR2026", exchange="NFO")
        pcr = result.pcr_suite

        self.assertGreaterEqual(pcr.oi_pcr, 0.0)
        self.assertGreaterEqual(pcr.volume_pcr, 0.0)
        self.assertIn(pcr.sentiment, [
            "Extremely Bullish",
            "Bullish",
            "Neutral",
            "Bearish",
            "Extremely Bearish"
        ])
        self.assertIsNotNone(pcr.interpretation)
        self.assertGreater(len(pcr.interpretation), 10)

    def test_pcr_sentiment_classification_logic(self):
        # Test edge thresholds
        s1, _ = self.engine._classify_pcr_sentiment(1.65)
        self.assertEqual(s1, "Extremely Bullish")

        s2, _ = self.engine._classify_pcr_sentiment(1.25)
        self.assertEqual(s2, "Bullish")

        s3, _ = self.engine._classify_pcr_sentiment(1.00)
        self.assertEqual(s3, "Neutral")

        s4, _ = self.engine._classify_pcr_sentiment(0.75)
        self.assertEqual(s4, "Bearish")

        s5, _ = self.engine._classify_pcr_sentiment(0.45)
        self.assertEqual(s5, "Extremely Bearish")

    def test_loss_curve_structure(self):
        result = self.engine.calculate_max_pain("CRUDEOIL", expiry="19FEB2026", exchange="MCX")
        self.assertGreater(len(result.loss_curve), 0)

        for pt in result.loss_curve:
            self.assertGreater(pt.strike, 0.0)
            self.assertGreaterEqual(pt.call_loss, 0.0)
            self.assertGreaterEqual(pt.put_loss, 0.0)
            self.assertAlmostEqual(pt.total_loss, pt.call_loss + pt.put_loss, places=2)

    def test_serialization_to_dict(self):
        result = self.engine.calculate_max_pain("CRUDEOIL", expiry="19FEB2026", exchange="MCX")
        d = result.to_dict()
        self.assertEqual(d["underlying"], "CRUDEOIL")
        self.assertIn("pcr_suite", d)
        self.assertIn("loss_curve", d)
        self.assertIn("max_pain_strike", d)
        self.assertIn("sentiment", d["pcr_suite"])

if __name__ == "__main__":
    unittest.main()

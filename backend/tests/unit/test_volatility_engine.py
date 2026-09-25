import unittest
import math
from backend.app.services.analytics.volatility_engine import VolatilityEngine, volatility_engine

class TestVolatilityEngine(unittest.TestCase):
    def setUp(self):
        self.engine = VolatilityEngine()

    def test_close_to_close_hv_calculation(self):
        # Simulated 20-day constant return price series with ~16% volatility
        base = 23000.0
        prices = [base * (1.0 + 0.01 * math.sin(i)) for i in range(20)]
        hv = self.engine.calculate_close_to_close_hv(prices)
        self.assertGreater(hv, 0.0)
        self.assertLess(hv, 100.0)

    def test_parkinson_hv_calculation(self):
        # High/Low pairs
        pairs = [(100.0 * 1.02, 100.0 * 0.98) for _ in range(20)]
        p_hv = self.engine.calculate_parkinson_hv(pairs)
        self.assertGreater(p_hv, 0.0)
        self.assertLess(p_hv, 80.0)

    def test_iv_rank_bounds(self):
        # Midpoint: (20 - 10) / (30 - 10) = 50%
        ivr_mid = self.engine.calculate_iv_rank(20.0, 10.0, 30.0)
        self.assertAlmostEqual(ivr_mid, 50.0, places=1)

        # Min edge: 0%
        ivr_min = self.engine.calculate_iv_rank(10.0, 10.0, 30.0)
        self.assertAlmostEqual(ivr_min, 0.0, places=1)

        # Max edge: 100%
        ivr_max = self.engine.calculate_iv_rank(30.0, 10.0, 30.0)
        self.assertAlmostEqual(ivr_max, 100.0, places=1)

        # Clamping check
        ivr_overflow = self.engine.calculate_iv_rank(40.0, 10.0, 30.0)
        self.assertEqual(ivr_overflow, 100.0)

    def test_iv_percentile_calculation(self):
        samples = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0, 26.0, 28.0]
        # Current IV = 15.0 -> 3 values below (10, 12, 14) out of 10 = 30%
        ivp = self.engine.calculate_iv_percentile(15.0, samples)
        self.assertAlmostEqual(ivp, 30.0, places=1)

    def test_regime_classification_logic(self):
        # High Volatility (IVR >= 65)
        r_high = self.engine._determine_regime(75.0, 5.0)
        self.assertEqual(r_high.regime, "High Volatility")
        self.assertEqual(r_high.bias, "Premium Selling")
        self.assertGreater(len(r_high.strategy_suggestions), 2)

        # Moderate Volatility (35 <= IVR < 65)
        r_mod = self.engine._determine_regime(50.0, 1.0)
        self.assertEqual(r_mod.regime, "Moderate Volatility")
        self.assertEqual(r_mod.bias, "Neutral / Calendar Spreads")

        # Low Volatility (IVR < 35)
        r_low = self.engine._determine_regime(20.0, -3.0)
        self.assertEqual(r_low.regime, "Low Volatility")
        self.assertEqual(r_low.bias, "Premium Buying")

    def test_volatility_analysis_nifty(self):
        analysis = self.engine.analyze_volatility("NIFTY", expiry="26MAR2026", exchange="NFO")
        self.assertEqual(analysis.underlying, "NIFTY")
        self.assertGreater(analysis.spot_price, 0.0)
        self.assertGreater(analysis.current_atm_iv, 0.0)
        self.assertGreaterEqual(analysis.iv_rank, 0.0)
        self.assertLessEqual(analysis.iv_rank, 100.0)
        self.assertGreaterEqual(analysis.iv_percentile, 0.0)
        self.assertLessEqual(analysis.iv_percentile, 100.0)

        # HV Suite
        self.assertGreater(analysis.hv_suite.hv_10d, 0.0)
        self.assertGreater(analysis.hv_suite.hv_20d, 0.0)
        self.assertGreater(analysis.hv_suite.hv_30d, 0.0)
        self.assertGreater(analysis.hv_suite.parkinson_hv_20d, 0.0)

        # VRP calculation
        self.assertIsNotNone(analysis.vrp)
        self.assertIsNotNone(analysis.regime.regime)

    def test_volatility_analysis_crudeoil(self):
        analysis = self.engine.analyze_volatility("CRUDEOIL", expiry="19FEB2026", exchange="MCX")
        self.assertEqual(analysis.underlying, "CRUDEOIL")
        self.assertEqual(analysis.exchange, "MCX")
        self.assertGreater(analysis.current_atm_iv, 0.0)
        self.assertIn("CRUDEOIL", self.engine.HISTORICAL_IV_BOUNDS)

if __name__ == "__main__":
    unittest.main()

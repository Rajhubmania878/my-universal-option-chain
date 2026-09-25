import unittest
from backend.app.services.analytics.sensitivity_stress_engine import (
    SensitivityAndStressEngine,
    sensitivity_stress_engine
)


class TestSensitivityAndStressEngine(unittest.TestCase):
    def setUp(self):
        self.engine = SensitivityAndStressEngine()

    def test_higher_order_greeks_calculation(self):
        higher = self.engine.calculate_higher_order_greeks(
            spot=8908.0,
            strike=8900.0,
            time_to_expiry_years=25.0 / 365.0,
            iv=0.28,
            is_call=True
        )
        self.assertIsNotNone(higher.vanna)
        self.assertIsNotNone(higher.volga)
        self.assertIsNotNone(higher.charm)
        self.assertIsNotNone(higher.color)
        self.assertIsNotNone(higher.speed)

        d = higher.to_dict()
        self.assertIn("vanna", d)
        self.assertIn("volga", d)
        self.assertIn("charm", d)
        self.assertIn("color", d)
        self.assertIn("speed", d)

    def test_gamma_scalp_simulation(self):
        res = self.engine.simulate_gamma_scalp(
            underlying="CRUDEOIL",
            strike=8900.0,
            option_type="CE",
            entry_spot=8908.0,
            entry_iv=0.28,
            realized_vol=0.35,
            days_simulated=10,
            lot_size=100
        )
        self.assertEqual(res.underlying, "CRUDEOIL")
        self.assertGreater(res.gross_gamma_pnl, 0)
        self.assertGreater(res.total_theta_decay, 0)
        self.assertGreater(res.total_hedges_executed, 0)
        self.assertGreater(res.scalping_efficiency_ratio, 0)

    def test_portfolio_stress_testing(self):
        positions = [
            {"symbol": "CRUDEOIL24OCT8900CE", "strike": 8900.0, "option_type": "CE", "netQty": -100, "buyAvg": 150.0, "ltp": 150.0, "iv": 0.28, "dte": 25},
            {"symbol": "CRUDEOIL24OCT8900PE", "strike": 8900.0, "option_type": "PE", "netQty": -100, "buyAvg": 140.0, "ltp": 140.0, "iv": 0.28, "dte": 25}
        ]
        results = self.engine.run_portfolio_stress_test(
            positions=positions,
            underlying_spot=8908.0,
            custom_spot_shock_pct=-5.0,
            custom_iv_shock_pct=10.0,
            custom_days_decay=2
        )
        self.assertEqual(len(results), 5)
        flash_crash = results[0]
        self.assertEqual(flash_crash.scenario_id, "SCN-FLASH-CRASH")
        self.assertEqual(flash_crash.spot_shock_pct, -7.0)
        self.assertIn("simulated_pnl", flash_crash.to_dict())
        self.assertIn("risk_level", flash_crash.to_dict())


if __name__ == '__main__':
    unittest.main()

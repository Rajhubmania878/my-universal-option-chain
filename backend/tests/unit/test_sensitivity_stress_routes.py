import unittest
from backend.app.api.routes.sensitivity_stress import (
    calculate_cross_greeks,
    simulate_gamma_scalping,
    run_stress_test,
    CrossGreeksRequest,
    GammaScalpRequest,
    PortfolioStressTestRequest
)


class TestSensitivityStressRoutes(unittest.TestCase):
    def test_calculate_cross_greeks_route(self):
        req = CrossGreeksRequest(
            spot=8908.0,
            strike=8900.0,
            dte_days=25.0,
            iv=0.28,
            is_call=True
        )
        res = calculate_cross_greeks(req)
        self.assertEqual(res["status"], "success")
        data = res["data"]
        self.assertIn("vanna", data)
        self.assertIn("volga", data)
        self.assertIn("charm", data)
        self.assertIn("color", data)
        self.assertIn("speed", data)

    def test_simulate_gamma_scalping_route(self):
        req = GammaScalpRequest(
            underlying="CRUDEOIL",
            strike=8900.0,
            option_type="CE",
            entry_spot=8908.0,
            entry_iv=0.28,
            realized_volatility=0.35,
            days_simulated=10,
            lot_size=100
        )
        res = simulate_gamma_scalping(req)
        self.assertEqual(res["status"], "success")
        data = res["data"]
        self.assertEqual(data["underlying"], "CRUDEOIL")
        self.assertIn("gross_gamma_pnl", data)
        self.assertIn("total_theta_decay", data)
        self.assertIn("net_scalping_pnl", data)

    def test_run_stress_test_route(self):
        req = PortfolioStressTestRequest(
            underlying_spot=8908.0,
            custom_spot_shock_pct=-5.0,
            custom_iv_shock_pct=12.0,
            custom_days_decay=3,
            positions=[]
        )
        res = run_stress_test(req)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["count"], 5)
        self.assertIsInstance(res["data"], list)


if __name__ == '__main__':
    unittest.main()

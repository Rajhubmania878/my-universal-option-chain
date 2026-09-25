import unittest
import asyncio
from backend.app.api.routes.payoff import (
    evaluate_custom_payoff,
    get_strategy_template_payoff,
    PayoffEvaluationRequest,
    LegInput
)

class TestPayoffRoutes(unittest.TestCase):
    def test_get_strategy_template_short_straddle(self):
        result = asyncio.run(get_strategy_template_payoff(
            template_name="short_straddle",
            underlying="CRUDEOIL",
            spot=8900.0,
            step=100.0,
            target_days=0.0,
            iv_shift=0.0
        ))
        self.assertEqual(result["status"], "success")
        data = result["data"]
        self.assertEqual(data["underlying"], "CRUDEOIL")
        self.assertEqual(len(data["legs"]), 2)
        self.assertTrue(data["is_net_credit"])
        self.assertGreater(len(data["payoff_curve"]), 20)
        self.assertEqual(len(data["scenario_matrix"]), 7)

    def test_get_strategy_template_bull_call_spread(self):
        result = asyncio.run(get_strategy_template_payoff(
            template_name="bull_call_spread",
            underlying="NIFTY",
            spot=23500.0,
            step=50.0
        ))
        self.assertEqual(result["status"], "success")
        data = result["data"]
        self.assertEqual(data["underlying"], "NIFTY")
        self.assertFalse(data["is_net_credit"])
        self.assertIsInstance(data["max_profit"], (int, float))
        self.assertIsInstance(data["max_loss"], (int, float))

    def test_evaluate_custom_payoff_endpoint(self):
        req = PayoffEvaluationRequest(
            strategy_name="Custom Bull Put",
            underlying="CRUDEOIL",
            current_spot=8900.0,
            legs=[
                LegInput(symbol="CRUDEOIL8900PE", option_type="PE", strike=8900.0, action="SELL", quantity=100, entry_price=230.0, iv=20.0),
                LegInput(symbol="CRUDEOIL8800PE", option_type="PE", strike=8800.0, action="BUY", quantity=100, entry_price=170.0, iv=20.0)
            ],
            tte_days=7.0,
            target_days=1.0,
            iv_shift_pct=-1.5
        )
        result = asyncio.run(evaluate_custom_payoff(req))
        self.assertEqual(result["status"], "success")
        data = result["data"]
        self.assertTrue(data["is_net_credit"])
        self.assertEqual(data["net_premium"], 6000.0) # (230 - 170) * 100
        self.assertIn("delta", data["net_greeks"])

if __name__ == "__main__":
    unittest.main()

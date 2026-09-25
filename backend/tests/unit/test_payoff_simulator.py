import unittest
from backend.app.services.analytics.payoff_simulator import StrategyPayoffEngine, StrategyLeg

class TestPayoffSimulator(unittest.TestCase):
    def setUp(self):
        self.engine = StrategyPayoffEngine()

    def test_single_call_buy_expiry_payoff(self):
        # Long 1 Lot 8900 CE @ 200.0, Qty 100
        leg = StrategyLeg(
            symbol="CRUDEOIL8900CE",
            option_type="CE",
            strike=8900.0,
            action="BUY",
            quantity=100,
            entry_price=200.0,
            iv=20.0
        )

        # At spot 8800 (OTM), pnl should be -200 * 100 = -20,000
        pnl_otm = self.engine.calculate_leg_expiry_pnl(leg, 8800.0)
        self.assertEqual(pnl_otm, -20000.0)

        # At spot 9100 (ITM by 200), intrinsic 200, unit pnl 0, total 0
        pnl_be = self.engine.calculate_leg_expiry_pnl(leg, 9100.0)
        self.assertEqual(pnl_be, 0.0)

        # At spot 9300 (ITM by 400), intrinsic 400, unit pnl +200, total +20,000
        pnl_itm = self.engine.calculate_leg_expiry_pnl(leg, 9300.0)
        self.assertEqual(pnl_itm, 20000.0)

    def test_short_straddle_payoff_and_breakevens(self):
        # CRUDEOIL ATM Short Straddle: Sell 8900 CE @ 240, Sell 8900 PE @ 235 (Total credit = 475)
        legs = self.engine.create_short_straddle(
            underlying="CRUDEOIL",
            atm_strike=8900.0,
            premium_ce=240.0,
            premium_pe=235.0,
            iv=22.0,
            qty=100
        )

        result = self.engine.evaluate_strategy_payoff(
            strategy_name="ATM Short Straddle",
            underlying="CRUDEOIL",
            current_spot=8900.0,
            legs=legs,
            tte_days=7.0
        )

        self.assertEqual(result["underlying"], "CRUDEOIL")
        self.assertTrue(result["is_net_credit"])
        self.assertEqual(result["net_premium"], 47500.0)
        self.assertEqual(result["max_loss"], "Unlimited")

        # Breakevens should be approximately 8900 - 475 = 8425 and 8900 + 475 = 9375
        self.assertEqual(len(result["breakevens"]), 2)
        lower_be = min(result["breakevens"])
        upper_be = max(result["breakevens"])
        self.assertAlmostEqual(lower_be, 8425.0, delta=20.0)
        self.assertAlmostEqual(upper_be, 9375.0, delta=20.0)

        # Probability of Profit should be > 50% for a short straddle
        self.assertGreater(result["probability_of_profit_pct"], 50.0)

    def test_bull_call_spread_bounded_risk(self):
        # Bull Call Spread: Buy 8900 CE @ 240, Sell 9000 CE @ 180 (Net Debit = 60/unit, Spread = 100)
        # Max Profit = (100 - 60) * 100 = 4,000
        # Max Loss = -60 * 100 = -6,000
        legs = self.engine.create_bull_call_spread(
            underlying="CRUDEOIL",
            atm_strike=8900.0,
            step=100.0,
            buy_ce_price=240.0,
            sell_ce_price=180.0,
            iv=20.0,
            qty=100
        )

        result = self.engine.evaluate_strategy_payoff(
            strategy_name="Bull Call Spread",
            underlying="CRUDEOIL",
            current_spot=8900.0,
            legs=legs,
            tte_days=7.0
        )

        self.assertFalse(result["is_net_credit"])
        self.assertEqual(result["net_premium"], -6000.0)
        self.assertAlmostEqual(result["max_profit"], 4000.0, delta=5.0)
        self.assertAlmostEqual(result["max_loss"], -6000.0, delta=5.0)
        self.assertIsNotNone(result["risk_reward_ratio"])
        self.assertAlmostEqual(result["risk_reward_ratio"], 0.67, delta=0.05)

    def test_iron_condor_profile(self):
        # 4 legs: Sell 8800 PE, Buy 8700 PE, Sell 9000 CE, Buy 9100 CE
        # Width = 100. Put credit = 145 - 115 = 30. Call credit = 150 - 120 = 30. Total credit = 60.
        # Max Profit = 60 * 100 = 6,000. Max Loss = (60 - 100) * 100 = -4,000.
        legs = self.engine.create_iron_condor(
            underlying="CRUDEOIL",
            atm_strike=8900.0,
            step=100.0,
            otm_call_short=150.0,
            otm_call_long=120.0,
            otm_put_short=145.0,
            otm_put_long=115.0,
            iv=21.0,
            qty=100
        )

        result = self.engine.evaluate_strategy_payoff(
            strategy_name="Iron Condor",
            underlying="CRUDEOIL",
            current_spot=8900.0,
            legs=legs,
            tte_days=7.0
        )

        self.assertEqual(len(result["legs"]), 4)
        self.assertTrue(result["is_net_credit"])
        # Both wings should be capped (not Unlimited)
        self.assertIsInstance(result["max_profit"], (int, float))
        self.assertIsInstance(result["max_loss"], (int, float))
        self.assertGreater(result["max_profit"], 0)
        self.assertLess(result["max_loss"], 0)

    def test_target_date_mark_to_market_pricing(self):
        legs = self.engine.create_short_straddle(
            underlying="CRUDEOIL",
            atm_strike=8900.0,
            premium_ce=240.0,
            premium_pe=235.0,
            iv=22.0,
            qty=100
        )

        result = self.engine.evaluate_strategy_payoff(
            strategy_name="ATM Short Straddle",
            underlying="CRUDEOIL",
            current_spot=8900.0,
            legs=legs,
            tte_days=7.0,
            target_days=2.0,
            iv_shift_pct=-2.0
        )

        curve = result["payoff_curve"]
        self.assertGreater(len(curve), 20)
        # Spot at 8900 should have target P&L calculated
        center_pt = [pt for pt in curve if abs(pt["spot"] - 8900.0) < 10][0]
        self.assertIn("pnl_target", center_pt)
        self.assertIn("pnl_expiry", center_pt)

    def test_scenario_matrix_generation(self):
        legs = self.engine.create_short_straddle(
            underlying="CRUDEOIL",
            atm_strike=8900.0,
            premium_ce=240.0,
            premium_pe=235.0,
            iv=22.0,
            qty=100
        )

        result = self.engine.evaluate_strategy_payoff(
            strategy_name="ATM Short Straddle",
            underlying="CRUDEOIL",
            current_spot=8900.0,
            legs=legs,
            tte_days=7.0
        )

        matrix = result["scenario_matrix"]
        self.assertEqual(len(matrix), 7) # 7 spot shocks
        self.assertEqual(len(matrix[0]["pnl_by_iv_shift"]), 5) # 5 IV shifts
        self.assertIn("0%", matrix[0]["pnl_by_iv_shift"])

if __name__ == "__main__":
    unittest.main()

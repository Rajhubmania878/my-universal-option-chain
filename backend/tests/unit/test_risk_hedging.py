import unittest
from backend.app.services.trading.risk_and_hedging import risk_hedging_engine, PortfolioRiskAndHedgingEngine


class TestRiskAndHedgingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = PortfolioRiskAndHedgingEngine()

    def test_empty_portfolio_risk(self):
        analysis = self.engine.analyze_portfolio_risk(
            underlying="CRUDEOIL",
            positions=[],
            capital=1000000.0,
            spot_override=8900.0
        )
        self.assertEqual(analysis.total_positions_count, 0)
        self.assertEqual(analysis.total_open_qty, 0)
        self.assertEqual(analysis.greeks.net_delta, 0.0)
        self.assertEqual(analysis.greeks.net_delta_cash, 0.0)
        self.assertEqual(analysis.greeks.var_99_1day, 0.0)
        self.assertGreater(len(analysis.stress_scenarios), 0)

    def test_single_long_call_risk(self):
        # Long 100 qty (1 lot) of CRUDEOIL 8900 CE
        positions = [
            {
                "symbol": "CRUDEOIL24OCT8900CE",
                "underlying": "CRUDEOIL",
                "netQty": 100,
                "ltp": 250.0
            }
        ]
        analysis = self.engine.analyze_portfolio_risk(
            underlying="CRUDEOIL",
            positions=positions,
            capital=1000000.0,
            spot_override=8900.0
        )
        self.assertEqual(analysis.total_positions_count, 1)
        self.assertEqual(analysis.total_open_qty, 100)
        # Delta for ATM Call should be positive (~0.50 * 100 = ~50)
        self.assertGreater(analysis.greeks.net_delta, 20.0)
        self.assertGreater(analysis.greeks.net_delta_cash, 0.0)
        self.assertGreater(analysis.greeks.net_gamma, 0.0)
        self.assertLess(analysis.greeks.net_theta_daily, 0.0)  # Long option pays theta decay
        self.assertGreater(analysis.greeks.net_vega, 0.0)     # Long option gains from vol expansion
        self.assertGreater(analysis.greeks.var_99_1day, 0.0)

        # Hedging check: with positive delta, it should recommend SELL futures or BUY puts
        futures_hedge = next((h for h in analysis.hedging_recommendations if h.hedge_type == "DELTA_FUTURES"), None)
        self.assertIsNotNone(futures_hedge)
        self.assertEqual(futures_hedge.recommended_action, "SELL")

    def test_short_straddle_neutrality(self):
        # Short Straddle: Sell 100 ATM CE and Sell 100 ATM PE
        positions = [
            {
                "symbol": "CRUDEOIL24OCT8900CE",
                "underlying": "CRUDEOIL",
                "netQty": -100,
                "ltp": 240.0
            },
            {
                "symbol": "CRUDEOIL24OCT8900PE",
                "underlying": "CRUDEOIL",
                "netQty": -100,
                "ltp": 230.0
            }
        ]
        analysis = self.engine.analyze_portfolio_risk(
            underlying="CRUDEOIL",
            positions=positions,
            capital=1000000.0,
            spot_override=8900.0
        )
        # Net Delta should be near zero for ATM straddle
        self.assertAlmostEqual(analysis.greeks.net_delta, 0.0, delta=15.0)
        # Net Theta should be positive (seller earns theta)
        self.assertGreater(analysis.greeks.net_theta_daily, 0.0)
        # Net Vega should be negative (short volatility)
        self.assertLess(analysis.greeks.net_vega, 0.0)

        # Stress testing: Black swan shock should show significant loss for naked short straddle
        black_swan = next((s for s in analysis.stress_scenarios if s.scenario_id == "BLACK_SWAN"), None)
        self.assertIsNotNone(black_swan)
        self.assertLess(black_swan.projected_pnl, 0.0)

    def test_futures_position_greeks(self):
        # Long 100 qty (1 lot) CRUDEOIL Futures
        positions = [
            {
                "symbol": "CRUDEOIL-FUT",
                "underlying": "CRUDEOIL",
                "netQty": 100,
                "ltp": 8900.0
            }
        ]
        analysis = self.engine.analyze_portfolio_risk(
            underlying="CRUDEOIL",
            positions=positions,
            capital=1000000.0,
            spot_override=8900.0
        )
        # 100 units of Futures has exactly 100.0 Delta
        self.assertEqual(analysis.greeks.net_delta, 100.0)
        self.assertEqual(analysis.greeks.net_gamma, 0.0)
        self.assertEqual(analysis.greeks.net_theta_daily, 0.0)
        self.assertEqual(analysis.greeks.net_vega, 0.0)

    def test_stress_scenarios_structure(self):
        positions = [
            {"symbol": "CRUDEOIL24OCT8900CE", "underlying": "CRUDEOIL", "netQty": 100, "ltp": 250.0}
        ]
        analysis = self.engine.analyze_portfolio_risk("CRUDEOIL", positions, spot_override=8900.0)
        self.assertEqual(len(analysis.stress_scenarios), 6)
        scenario_ids = [s.scenario_id for s in analysis.stress_scenarios]
        self.assertIn("BULL_RALLY", scenario_ids)
        self.assertIn("FLASH_CRASH", scenario_ids)
        self.assertIn("BLACK_SWAN", scenario_ids)
        self.assertIn("VOL_EXPLOSION", scenario_ids)
        self.assertIn("VOL_CRUSH", scenario_ids)


if __name__ == '__main__':
    unittest.main()

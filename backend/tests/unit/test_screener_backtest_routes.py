import unittest
from backend.app.api.routes.screener_backtest import (
    query_options_screener,
    run_strategy_backtest,
    get_strategy_presets,
    ScreenerQueryRequest,
    BacktestRunRequest
)


class TestScreenerBacktestRoutes(unittest.TestCase):
    def test_screener_query_route(self):
        req = ScreenerQueryRequest(
            underlying="CRUDEOIL",
            min_iv_rank=50.0,
            option_type="ALL"
        )
        res = query_options_screener(req)
        self.assertEqual(res["status"], "success")
        self.assertGreater(res["count"], 0)
        self.assertIsInstance(res["data"], list)

    def test_backtest_run_route(self):
        req = BacktestRunRequest(
            strategy_name="IRON_CONDOR",
            underlying="CRUDEOIL",
            initial_capital=1000000.0,
            profit_target_pct=50.0,
            stop_loss_pct=100.0
        )
        res = run_strategy_backtest(req)
        self.assertEqual(res["status"], "success")
        data = res["data"]
        self.assertEqual(data["strategy_name"], "IRON_CONDOR")
        self.assertIn("equity_curve", data)
        self.assertIn("trades", data)
        self.assertIn("win_rate_pct", data)

    def test_strategy_presets_route(self):
        res = get_strategy_presets()
        self.assertEqual(res["status"], "success")
        self.assertGreater(len(res["data"]), 3)
        self.assertEqual(res["data"][0]["id"], "IRON_CONDOR")


if __name__ == '__main__':
    unittest.main()

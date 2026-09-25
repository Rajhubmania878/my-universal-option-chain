import unittest
from backend.app.services.analytics.screener_backtest import (
    OptionsScreenerAndBacktestEngine,
    screener_backtest_engine
)


class TestOptionsScreenerAndBacktestEngine(unittest.TestCase):
    def setUp(self):
        self.engine = OptionsScreenerAndBacktestEngine()

    def test_screener_database_seeding(self):
        self.assertGreater(len(self.engine.screener_cache), 20)
        first_item = self.engine.screener_cache[0]
        self.assertIsNotNone(first_item.symbol)
        self.assertIsNotNone(first_item.iv_rank)
        self.assertIsNotNone(first_item.delta)
        self.assertIsNotNone(first_item.theta_efficiency)

    def test_screener_query_with_iv_rank_filter(self):
        # Query items with IV Rank >= 60
        results = self.engine.run_screener_query(min_iv_rank=60.0)
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertGreaterEqual(r["iv_rank"], 60.0)

    def test_screener_query_by_underlying_and_option_type(self):
        results = self.engine.run_screener_query(
            underlying="CRUDEOIL",
            option_type="CE"
        )
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r["underlying"], "CRUDEOIL")
            self.assertEqual(r["option_type"], "CE")

    def test_screener_query_by_tag_filter(self):
        results = self.engine.run_screener_query(tag_filter="HIGH_IV_SELL")
        for r in results:
            self.assertIn("HIGH_IV_SELL", r["tags"])

    def test_screener_sorting(self):
        results = self.engine.run_screener_query(sort_by="iv_rank", sort_desc=True)
        self.assertGreater(len(results), 1)
        self.assertGreaterEqual(results[0]["iv_rank"], results[1]["iv_rank"])

    def test_iron_condor_backtest_simulation(self):
        res = self.engine.run_strategy_backtest(
            strategy_name="IRON_CONDOR",
            underlying="CRUDEOIL",
            initial_capital=1000000.0
        )
        self.assertEqual(res.strategy_name, "IRON_CONDOR")
        self.assertEqual(res.underlying, "CRUDEOIL")
        self.assertEqual(res.total_trades, 24)
        self.assertGreater(res.winning_trades, 0)
        self.assertGreater(res.win_rate_pct, 50.0)
        self.assertGreater(res.profit_factor, 1.0)
        self.assertGreater(len(res.equity_curve), 20)
        self.assertGreater(len(res.trades), 0)

    def test_short_straddle_backtest(self):
        res = self.engine.run_strategy_backtest(
            strategy_name="SHORT_STRADDLE",
            underlying="NIFTY",
            initial_capital=500000.0
        )
        self.assertEqual(res.strategy_name, "SHORT_STRADDLE")
        self.assertEqual(res.underlying, "NIFTY")
        self.assertIsNotNone(res.sharpe_ratio)
        self.assertIsNotNone(res.max_drawdown_pct)


if __name__ == '__main__':
    unittest.main()

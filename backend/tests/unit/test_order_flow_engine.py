import unittest
from backend.app.services.analytics.order_flow_engine import (
    OrderFlowAndMicrostructureEngine,
    order_flow_engine
)


class TestOrderFlowAndMicrostructureEngine(unittest.TestCase):
    def setUp(self):
        self.engine = OrderFlowAndMicrostructureEngine()

    def test_order_book_depth_structure(self):
        snapshot = self.engine.get_order_book_depth("CRUDEOIL24OCT8900CE", depth_levels=5)
        self.assertEqual(snapshot.symbol, "CRUDEOIL24OCT8900CE")
        self.assertEqual(len(snapshot.bids), 5)
        self.assertEqual(len(snapshot.asks), 5)
        self.assertGreater(snapshot.total_bid_qty, 0)
        self.assertGreater(snapshot.total_ask_qty, 0)
        self.assertGreater(snapshot.spread, 0)
        self.assertGreater(snapshot.microprice, 0)
        self.assertGreaterEqual(snapshot.order_book_imbalance, -1.0)
        self.assertLessEqual(snapshot.order_book_imbalance, 1.0)

    def test_block_trades_filtering(self):
        all_trades = self.engine.get_large_block_trades()
        self.assertGreater(len(all_trades), 3)

        crude_trades = self.engine.get_large_block_trades(underlying="CRUDEOIL")
        for t in crude_trades:
            self.assertEqual(t["underlying"], "CRUDEOIL")

        bullish_trades = self.engine.get_large_block_trades(sentiment="BULLISH_FLOW")
        for t in bullish_trades:
            self.assertEqual(t["flow_sentiment"], "BULLISH_FLOW")

    def test_add_simulated_trade_to_tape(self):
        initial_count = len(self.engine.block_trades_log)
        trade = self.engine.add_simulated_trade(
            symbol="CRUDEOIL24OCT9100CE",
            underlying="CRUDEOIL",
            strike=9100.0,
            option_type="CE",
            price=120.0,
            qty=2500,
            side="BUY",
            ttype="SWEEP"
        )
        self.assertEqual(len(self.engine.block_trades_log), initial_count + 1)
        self.assertEqual(trade["side"], "BUY")
        self.assertEqual(trade["flow_sentiment"], "BULLISH_FLOW")
        self.assertTrue(trade["is_unusual"])

    def test_strike_cvd_footprint(self):
        cvd_data = self.engine.get_strike_cvd_footprint(underlying="CRUDEOIL")
        self.assertGreater(len(cvd_data), 10)
        first_item = cvd_data[0]
        self.assertIn("strike", first_item)
        self.assertIn("cvd", first_item)
        self.assertIn("cvd_pct", first_item)
        self.assertIn("net_sentiment", first_item)


if __name__ == '__main__':
    unittest.main()

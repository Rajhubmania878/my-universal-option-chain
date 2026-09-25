import unittest
from backend.app.api.routes.order_flow import (
    get_order_book_depth,
    get_block_trades,
    simulate_trade_execution,
    get_strike_cvd,
    SimulateTradeRequest
)


class TestOrderFlowRoutes(unittest.TestCase):
    def test_get_order_book_depth_route(self):
        res = get_order_book_depth(symbol="CRUDEOIL24OCT8900CE", levels=5)
        self.assertEqual(res["status"], "success")
        data = res["data"]
        self.assertEqual(data["symbol"], "CRUDEOIL24OCT8900CE")
        self.assertEqual(len(data["bids"]), 5)
        self.assertEqual(len(data["asks"]), 5)
        self.assertIn("microprice", data)
        self.assertIn("order_book_imbalance", data)

    def test_get_block_trades_route(self):
        res = get_block_trades(underlying="CRUDEOIL", min_turnover=0.0, sentiment="ALL")
        self.assertEqual(res["status"], "success")
        self.assertGreater(res["count"], 0)
        self.assertIsInstance(res["data"], list)

    def test_simulate_trade_execution_route(self):
        req = SimulateTradeRequest(
            symbol="NIFTY24OCT23500PE",
            underlying="NIFTY",
            strike=23500.0,
            option_type="PE",
            price=110.0,
            quantity=1500,
            side="BUY",
            trade_type="SWEEP"
        )
        res = simulate_trade_execution(req)
        self.assertEqual(res["status"], "success")
        data = res["data"]
        self.assertEqual(data["symbol"], "NIFTY24OCT23500PE")
        self.assertEqual(data["side"], "BUY")
        self.assertEqual(data["flow_sentiment"], "BEARISH_FLOW")

    def test_get_strike_cvd_route(self):
        res = get_strike_cvd(underlying="CRUDEOIL")
        self.assertEqual(res["status"], "success")
        self.assertGreater(res["count"], 5)
        self.assertIsInstance(res["data"], list)


if __name__ == '__main__':
    unittest.main()

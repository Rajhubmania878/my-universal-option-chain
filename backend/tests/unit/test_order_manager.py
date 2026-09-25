import unittest
from backend.app.services.trading.order_manager import (
    PaperTradingEngine,
    OrderType,
    OrderAction,
    OrderStatus
)

class TestPaperTradingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = PaperTradingEngine(initial_capital=500000.0)

    def test_initial_portfolio_state(self):
        summary = self.engine.update_live_pnl({})
        self.assertEqual(summary["initial_capital"], 500000.0)
        self.assertEqual(summary["available_cash"], 500000.0)
        self.assertEqual(summary["active_positions_count"], 0)

    def test_single_buy_order_execution(self):
        res = self.engine.place_order(
            symbol="CRUDEOIL24OCT8900CE",
            token="654321",
            underlying="CRUDEOIL",
            transaction_type=OrderAction.BUY,
            quantity=100,
            price=240.50
        )
        self.assertEqual(res["status"], OrderStatus.COMPLETE)
        self.assertEqual(res["quantity"], 100)
        self.assertEqual(res["net_qty"], 100)
        # Margin deducted: 100 * 240.50 = 24050
        self.assertAlmostEqual(res["available_cash"], 500000.0 - 24050.0)

    def test_margin_rejection_on_excess_order(self):
        res = self.engine.place_order(
            symbol="NIFTY24OCT23000CE",
            token="12345",
            underlying="NIFTY",
            transaction_type=OrderAction.BUY,
            quantity=3000,
            price=200.0  # Required: 600,000 > 500,000 capital
        )
        self.assertEqual(res["status"], OrderStatus.REJECTED)
        self.assertIn("Insufficient margin", res["reason"])

    def test_multi_leg_strategy_execution(self):
        legs = [
            {
                "symbol": "CRUDEOIL24OCT8900CE",
                "token": "654321",
                "transaction_type": OrderAction.SELL,
                "quantity": 100,
                "price": 240.0
            },
            {
                "symbol": "CRUDEOIL24OCT8900PE",
                "token": "654322",
                "transaction_type": OrderAction.SELL,
                "quantity": 100,
                "price": 235.0
            }
        ]
        strat_res = self.engine.place_multi_leg_strategy(
            strategy_name="ATM Short Straddle",
            underlying="CRUDEOIL",
            legs=legs
        )
        self.assertEqual(strat_res["strategy_name"], "ATM Short Straddle")
        self.assertEqual(strat_res["legs_count"], 2)
        self.assertEqual(len(strat_res["legs"]), 2)

    def test_mark_to_market_pnl_calculation(self):
        self.engine.place_order(
            symbol="CRUDEOIL24OCT8900CE",
            token="654321",
            underlying="CRUDEOIL",
            transaction_type=OrderAction.BUY,
            quantity=100,
            price=200.0
        )
        # Price increases to 250
        quotes = {"CRUDEOIL24OCT8900CE": 250.0}
        pnl = self.engine.update_live_pnl(quotes)
        self.assertEqual(pnl["total_unrealized_pnl"], 5000.0)

    def test_square_off_all_positions(self):
        self.engine.place_order(
            symbol="CRUDEOIL24OCT8900CE",
            token="654321",
            underlying="CRUDEOIL",
            transaction_type=OrderAction.BUY,
            quantity=50,
            price=150.0
        )
        self.assertEqual(self.engine.positions["CRUDEOIL24OCT8900CE_INTRADAY"]["net_qty"], 50)
        
        sq = self.engine.square_off_all_positions()
        self.assertEqual(sq["squared_off_count"], 1)
        self.assertEqual(self.engine.positions["CRUDEOIL24OCT8900CE_INTRADAY"]["net_qty"], 0)

if __name__ == "__main__":
    unittest.main()

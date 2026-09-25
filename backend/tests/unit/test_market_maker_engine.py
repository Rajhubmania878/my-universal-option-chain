import unittest
from backend.app.services.analytics.market_maker_engine import (
    MarketMakerEngine,
    market_maker_engine
)


class TestMarketMakerEngine(unittest.TestCase):
    def setUp(self):
        self.engine = MarketMakerEngine()

    def test_calculate_as_quotes_neutral(self):
        quotes = self.engine.calculate_as_quotes(
            symbol="CRUDEOIL26FEB8900CE",
            underlying="CRUDEOIL",
            strike=8900.0,
            option_type="CE",
            mid_price=125.0,
            inventory_q=0,
            gamma=0.1,
            kappa=1.5,
            sigma=0.28,
            time_to_close_hours=4.0
        )
        self.assertEqual(quotes.mid_price, 125.0)
        self.assertEqual(quotes.reservation_price, 125.0)
        self.assertLess(quotes.optimal_bid, quotes.mid_price)
        self.assertGreater(quotes.optimal_ask, quotes.mid_price)
        self.assertEqual(quotes.quote_status, "ACTIVE_QUOTING")

    def test_calculate_as_quotes_long_inventory_lean(self):
        # Long inventory -> reservation price drops below mid -> bids drop, asks drop to liquidate
        quotes = self.engine.calculate_as_quotes(
            symbol="CRUDEOIL26FEB8900CE",
            mid_price=125.0,
            inventory_q=10,
            gamma=0.2,
            kappa=1.0,
            sigma=0.30
        )
        self.assertLess(quotes.reservation_price, 125.0)
        self.assertEqual(quotes.quote_status, "LEAN_ASK")
        self.assertGreater(quotes.ask_size, quotes.bid_size)

    def test_generate_fix_message(self):
        fix_d = self.engine.generate_fix_message(
            msg_type="D",
            cl_ord_id="MM-100",
            symbol="CRUDEOIL8900CE",
            side="1",
            price=124.5,
            qty=100
        )
        self.assertEqual(fix_d.msg_type, "35=D")
        self.assertIn("35=D", fix_d.raw_fix_string)
        self.assertIn("10=", fix_d.raw_fix_string)
        self.assertEqual(fix_d.side, "BUY")


if __name__ == '__main__':
    unittest.main()

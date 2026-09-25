import unittest
from backend.app.api.routes.market_maker import (
    calculate_quotes,
    generate_fix,
    get_colo_telemetry,
    QuotingRequest,
    FixMessageRequest
)


class TestMarketMakerRoutes(unittest.TestCase):
    def test_calculate_quotes_route(self):
        req = QuotingRequest(
            symbol="CRUDEOIL8900CE",
            underlying="CRUDEOIL",
            strike=8900.0,
            option_type="CE",
            mid_price=125.0,
            inventory_q=2,
            gamma=0.1,
            kappa=1.5,
            sigma=0.28,
            time_to_close_hours=3.5
        )
        res = calculate_quotes(req)
        self.assertEqual(res["status"], "success")
        self.assertIn("reservation_price", res["data"])
        self.assertIn("optimal_bid", res["data"])
        self.assertIn("optimal_ask", res["data"])

    def test_generate_fix_route(self):
        req = FixMessageRequest(
            msg_type="8",
            cl_ord_id="MM-200",
            symbol="CRUDEOIL8900CE",
            side="2",
            price=126.0,
            qty=200
        )
        res = generate_fix(req)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["data"]["msg_type"], "35=8")
        self.assertIn("raw_fix_string", res["data"])

    def test_get_colo_telemetry_route(self):
        res = get_colo_telemetry()
        self.assertEqual(res["status"], "success")
        self.assertIn("total_tick_to_trade_micros", res)


if __name__ == '__main__':
    unittest.main()

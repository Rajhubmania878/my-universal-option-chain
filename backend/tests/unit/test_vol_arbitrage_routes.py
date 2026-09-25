import unittest
from backend.app.api.routes.vol_arbitrage import (
    get_calendar_spreads,
    scan_custom_calendar_spreads,
    get_parity_arbitrage,
    CalendarSpreadScanRequest
)


class TestVolatilityArbitrageRoutes(unittest.TestCase):
    def test_get_calendar_spreads_route(self):
        res = get_calendar_spreads(underlying="CRUDEOIL", spot=8908.0)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["underlying"], "CRUDEOIL")
        self.assertGreater(res["count"], 0)
        self.assertIsInstance(res["data"], list)

    def test_scan_custom_calendar_spreads_route(self):
        req = CalendarSpreadScanRequest(
            underlying="NIFTY",
            spot=23540.0,
            strikes=[23500.0, 23550.0]
        )
        res = scan_custom_calendar_spreads(req)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["count"], 2)

    def test_get_parity_arbitrage_route(self):
        res = get_parity_arbitrage(underlying="CRUDEOIL", spot=8908.0, risk_free_rate=0.07)
        self.assertEqual(res["status"], "success")
        self.assertGreater(res["count"], 0)


if __name__ == '__main__':
    unittest.main()

import unittest
from backend.app.api.routes.pin_risk_settlement import (
    get_pin_risk,
    scan_custom_pin_risk,
    calculate_tax_breakdown,
    get_delivery_margin_schedule,
    PinRiskScanRequest,
    TaxCalculationRequest
)


class TestPinRiskSettlementRoutes(unittest.TestCase):
    def test_get_pin_risk_route(self):
        res = get_pin_risk(spot=8908.0, iv=0.28, hours_to_cutoff=2.5)
        self.assertEqual(res["status"], "success")
        self.assertGreater(res["count"], 0)
        self.assertIsInstance(res["data"], list)

    def test_scan_custom_pin_risk_route(self):
        req = PinRiskScanRequest(
            spot=23500.0,
            strikes=[23450.0, 23500.0, 23550.0],
            iv=0.15,
            hours_to_cutoff=1.0
        )
        res = scan_custom_pin_risk(req)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["count"], 3)

    def test_calculate_tax_breakdown_route(self):
        req = TaxCalculationRequest(
            underlying="CRUDEOIL",
            strike=8900.0,
            option_type="CE",
            action="EXERCISE_ITM",
            quantity=100,
            execution_price=120.0,
            spot_at_expiry=8950.0
        )
        res = calculate_tax_breakdown(req)
        self.assertEqual(res["status"], "success")
        self.assertIn("total_statutory_charges", res["data"])

    def test_get_delivery_margin_schedule_route(self):
        res = get_delivery_margin_schedule(spot=8908.0, lot_size=100)
        self.assertEqual(res["status"], "success")
        self.assertEqual(len(res["schedule"]), 5)


if __name__ == '__main__':
    unittest.main()

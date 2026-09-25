import unittest
from backend.app.services.analytics.pin_risk_settlement_engine import (
    PinRiskAndSettlementEngine,
    pin_risk_settlement_engine
)


class TestPinRiskAndSettlementEngine(unittest.TestCase):
    def setUp(self):
        self.engine = PinRiskAndSettlementEngine()

    def test_calculate_pin_risk(self):
        results = self.engine.calculate_pin_risk(
            spot=8908.0,
            strikes=[8800.0, 8900.0, 9000.0],
            iv=0.28,
            hours_to_cutoff=2.0
        )
        self.assertEqual(len(results), 3)
        atm_item = results[1]
        self.assertEqual(atm_item.strike, 8900.0)
        self.assertGreater(atm_item.pin_probability_pct, 0.0)
        self.assertGreater(atm_item.call_itm_probability_pct, 0.0)
        self.assertGreater(atm_item.put_itm_probability_pct, 0.0)
        self.assertIn(atm_item.risk_level, ["EXTREME_PIN_RISK", "ELEVATED", "MODERATE", "NEGLIGIBLE"])

    def test_compute_settlement_taxes_crudeoil(self):
        breakdown = self.engine.compute_settlement_taxes(
            underlying="CRUDEOIL",
            strike=8900.0,
            option_type="CE",
            action="EXERCISE_ITM",
            quantity=100,
            execution_price=120.0,
            spot_at_expiry=8950.0
        )
        self.assertEqual(breakdown.underlying, "CRUDEOIL")
        self.assertEqual(breakdown.settlement_type, "FUTURES_DEVOLUTION")
        self.assertGreater(breakdown.total_statutory_charges, 0)
        self.assertGreater(breakdown.net_settlement_cashflow, 0)

    def test_compute_settlement_taxes_stock_stt_trap(self):
        breakdown = self.engine.compute_settlement_taxes(
            underlying="RELIANCE",
            strike=2800.0,
            option_type="CE",
            action="EXERCISE_ITM",
            quantity=250,
            execution_price=5.0,
            spot_at_expiry=2802.0
        )
        self.assertEqual(breakdown.settlement_type, "PHYSICAL_DELIVERY")
        # STT on 2802 * 250 @ 0.125% = 875.625
        self.assertGreater(breakdown.stt_ctt_tax, 500)

    def test_physical_margin_schedule(self):
        schedule = self.engine.get_physical_margin_schedule(spot=8908.0, lot_size=100)
        self.assertEqual(len(schedule), 5)
        self.assertEqual(schedule[0].mandatory_delivery_margin_pct, 10.0)
        self.assertEqual(schedule[3].mandatory_delivery_margin_pct, 100.0)


if __name__ == '__main__':
    unittest.main()

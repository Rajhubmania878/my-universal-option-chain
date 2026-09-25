import unittest
from backend.app.services.trading.algo_execution import (
    AlgorithmicExecutionEngine,
    EXCHANGE_FREEZE_LIMITS
)


class TestAlgorithmicExecutionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = AlgorithmicExecutionEngine()

    def test_freeze_slicing_under_limit(self):
        # 1000 qty of NIFTY when limit is 1800 should result in 1 slice
        plan = self.engine.calculate_freeze_slicing_plan(
            underlying="NIFTY",
            symbol="NIFTY24OCT23500CE",
            quantity=1000
        )
        self.assertEqual(plan.num_slices, 1)
        self.assertEqual(plan.slice_size, 1000)
        self.assertEqual(plan.residual_size, 0)
        self.assertEqual(len(plan.slices), 1)

    def test_freeze_slicing_over_limit_with_residual(self):
        # 5000 qty of NIFTY when limit is 1800:
        # 5000 // 1800 = 2 full slices of 1800 (3600) + 1 residual slice of 1400 = 3 slices
        plan = self.engine.calculate_freeze_slicing_plan(
            underlying="NIFTY",
            symbol="NIFTY24OCT23500CE",
            quantity=5000
        )
        self.assertEqual(plan.num_slices, 3)
        self.assertEqual(plan.slice_size, 1800)
        self.assertEqual(plan.residual_size, 1400)
        self.assertEqual(len(plan.slices), 3)
        self.assertEqual(plan.slices[0]["quantity"], 1800)
        self.assertEqual(plan.slices[1]["quantity"], 1800)
        self.assertEqual(plan.slices[2]["quantity"], 1400)

    def test_freeze_slicing_exact_multiple(self):
        # 3600 qty of NIFTY: exactly 2 slices of 1800, residual 0
        plan = self.engine.calculate_freeze_slicing_plan(
            underlying="NIFTY",
            symbol="NIFTY24OCT23500CE",
            quantity=3600
        )
        self.assertEqual(plan.num_slices, 2)
        self.assertEqual(plan.residual_size, 0)
        self.assertEqual(len(plan.slices), 2)

    def test_twap_execution_initialization(self):
        # 1000 qty over 5 slices
        session = self.engine.start_twap_execution(
            underlying="CRUDEOIL",
            symbol="CRUDEOIL24OCT8900CE",
            action="BUY",
            total_quantity=1000,
            duration_seconds=120,
            num_slices=5,
            price_override=240.0
        )
        self.assertEqual(session.algo_type, "TWAP")
        self.assertEqual(session.total_quantity, 1000)
        self.assertEqual(len(session.slices), 5)
        # First slice executed immediately
        self.assertEqual(session.slices[0].status, "FILLED")
        self.assertEqual(session.filled_quantity, 200)
        self.assertEqual(session.remaining_quantity, 800)
        self.assertEqual(session.status, "RUNNING")

    def test_iceberg_execution_initialization(self):
        # 2000 total with peak 500
        session = self.engine.start_iceberg_execution(
            underlying="CRUDEOIL",
            symbol="CRUDEOIL24OCT8900PE",
            action="SELL",
            total_quantity=2000,
            peak_size=500,
            price_override=220.0
        )
        self.assertEqual(session.algo_type, "ICEBERG")
        self.assertEqual(len(session.slices), 4)
        self.assertEqual(session.slices[0].quantity, 500)
        self.assertEqual(session.filled_quantity, 500)
        self.assertEqual(session.remaining_quantity, 1500)
        self.assertEqual(session.status, "RUNNING")

    def test_step_algo_session_progress(self):
        session = self.engine.start_twap_execution(
            underlying="NIFTY",
            symbol="NIFTY24OCT23500CE",
            action="BUY",
            total_quantity=600,
            num_slices=3,
            price_override=150.0
        )
        self.assertEqual(session.filled_quantity, 200)

        # Step 2
        updated_s2 = self.engine.update_session_progress(session.session_id)
        self.assertEqual(updated_s2.filled_quantity, 400)
        self.assertEqual(updated_s2.status, "RUNNING")

        # Step 3 (final)
        updated_s3 = self.engine.update_session_progress(session.session_id)
        self.assertEqual(updated_s3.filled_quantity, 600)
        self.assertEqual(updated_s3.remaining_quantity, 0)
        self.assertEqual(updated_s3.status, "COMPLETED")

    def test_execute_multi_leg_basket(self):
        legs = [
            {"symbol": "CRUDEOIL24OCT8900CE", "action": "BUY", "quantity": 100, "price": 250.0},
            {"symbol": "CRUDEOIL24OCT9100CE", "action": "SELL", "quantity": 100, "price": 160.0}
        ]
        result = self.engine.execute_multi_leg_basket(
            strategy_name="BULL_CALL_SPREAD",
            underlying="CRUDEOIL",
            legs=legs,
            slippage_tolerance_pts=1.5
        )
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["total_legs"], 2)
        self.assertEqual(len(result["executed_legs"]), 2)
        self.assertEqual(result["legging_risk_status"], "ZERO_LEGGING_RISK_ATOMIC_COMPLETE")

    def test_execution_analytics(self):
        analytics = self.engine.get_execution_analytics()
        self.assertIn("total_algo_sessions", analytics)
        self.assertIn("total_quantity_executed", analytics)
        self.assertIn("fill_rate_pct", analytics)
        self.assertGreater(analytics["fill_rate_pct"], 90.0)


if __name__ == '__main__':
    unittest.main()

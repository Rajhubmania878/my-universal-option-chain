import unittest
from backend.app.api.routes.algo_execution import (
    get_freeze_slicing_plan,
    start_twap_execution,
    start_iceberg_execution,
    execute_multi_leg_basket,
    get_algo_sessions,
    step_algo_session,
    get_algo_analytics,
    SlicingPlanRequest,
    StartTWAPRequest,
    StartIcebergRequest,
    MultiLegBasketRequest
)


class TestAlgoExecutionRoutes(unittest.TestCase):
    def test_freeze_slicing_plan_route(self):
        req = SlicingPlanRequest(
            underlying="NIFTY",
            symbol="NIFTY24OCT23500CE",
            quantity=5000
        )
        res = get_freeze_slicing_plan(req)
        self.assertEqual(res["status"], "success")
        data = res["data"]
        self.assertEqual(data["num_slices"], 3)
        self.assertEqual(data["freeze_limit"], 1800)

    def test_start_twap_route(self):
        req = StartTWAPRequest(
            underlying="CRUDEOIL",
            symbol="CRUDEOIL24OCT8900CE",
            action="BUY",
            total_quantity=500,
            duration_seconds=60,
            num_slices=5,
            price_override=200.0
        )
        res = start_twap_execution(req)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["data"]["algo_type"], "TWAP")
        self.assertEqual(res["data"]["filled_quantity"], 100)

    def test_start_iceberg_route(self):
        req = StartIcebergRequest(
            underlying="CRUDEOIL",
            symbol="CRUDEOIL24OCT8900PE",
            action="SELL",
            total_quantity=1000,
            peak_size=250,
            price_override=180.0
        )
        res = start_iceberg_execution(req)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["data"]["algo_type"], "ICEBERG")
        self.assertEqual(res["data"]["filled_quantity"], 250)

    def test_execute_multi_leg_basket_route(self):
        req = MultiLegBasketRequest(
            strategy_name="SHORT_STRADDLE",
            underlying="CRUDEOIL",
            legs=[
                {"symbol": "CRUDEOIL24OCT8900CE", "action": "SELL", "quantity": 100, "price": 250.0},
                {"symbol": "CRUDEOIL24OCT8900PE", "action": "SELL", "quantity": 100, "price": 240.0}
            ],
            slippage_tolerance_pts=2.0
        )
        res = execute_multi_leg_basket(req)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["data"]["status"], "COMPLETED")

    def test_get_sessions_and_step_route(self):
        sessions_res = get_algo_sessions()
        self.assertEqual(sessions_res["status"], "success")
        self.assertGreater(sessions_res["count"], 0)

        # Step the first running session
        running = next((s for s in sessions_res["data"] if s["status"] == "RUNNING"), None)
        if running:
            step_res = step_algo_session(running["session_id"])
            self.assertEqual(step_res["status"], "success")

    def test_get_algo_analytics_route(self):
        res = get_algo_analytics()
        self.assertEqual(res["status"], "success")
        self.assertIn("total_quantity_executed", res["data"])


if __name__ == '__main__':
    unittest.main()

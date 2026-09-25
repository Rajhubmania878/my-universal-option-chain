import unittest
from backend.app.api.routes.risk_hedging import (
    analyze_portfolio_risk,
    get_live_portfolio_risk,
    execute_hedge_order,
    AnalyzePortfolioRiskRequest,
    PositionItemSchema,
    ExecuteHedgeRequest
)


class TestRiskHedgingRoutes(unittest.TestCase):
    def test_analyze_portfolio_risk_endpoint(self):
        req = AnalyzePortfolioRiskRequest(
            underlying="CRUDEOIL",
            positions=[
                PositionItemSchema(
                    symbol="CRUDEOIL24OCT8900CE",
                    underlying="CRUDEOIL",
                    netQty=100,
                    ltp=250.0
                )
            ],
            capital=1000000.0,
            spot_override=8900.0
        )
        res = analyze_portfolio_risk(req)
        self.assertEqual(res["status"], "success")
        data = res["data"]
        self.assertIn("greeks", data)
        self.assertIn("hedging_recommendations", data)
        self.assertIn("stress_scenarios", data)
        self.assertGreater(data["greeks"]["net_delta"], 0.0)

    def test_get_live_portfolio_risk_endpoint(self):
        res = get_live_portfolio_risk("CRUDEOIL", capital=1000000.0)
        self.assertEqual(res["status"], "success")
        self.assertIn("greeks", res["data"])

    def test_execute_hedge_order_endpoint(self):
        req = ExecuteHedgeRequest(
            underlying="CRUDEOIL",
            symbol="CRUDEOIL-FUT",
            action="SELL",
            quantity=100
        )
        res = execute_hedge_order(req)
        self.assertEqual(res["status"], "success")
        self.assertIn("order", res)
        self.assertEqual(res["order"]["status"], "COMPLETE")
        self.assertEqual(res["order"]["quantity"], 100)


if __name__ == '__main__':
    unittest.main()

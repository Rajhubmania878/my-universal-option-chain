"""
API endpoint routers for health, status, authentication, instruments, market data, and analytics.
"""
try:
    from fastapi import APIRouter
except ImportError:
    class APIRouter:
        def __init__(self, *args, **kwargs):
            self.routes = []
        def get(self, *args, **kwargs):
            def decorator(f):
                return f
            return decorator
        def post(self, *args, **kwargs):
            def decorator(f):
                return f
            return decorator
        def include_router(self, *args, **kwargs):
            pass

from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.status import router as status_router
from backend.app.api.routes.auth import router as auth_router
from backend.app.api.routes.instruments import router as instruments_router
from backend.app.api.routes.subscriptions import router as subscriptions_router
from backend.app.api.routes.quotes import router as quotes_router
from backend.app.api.routes.option_chain import router as option_chain_router
from backend.app.api.routes.greeks import router as greeks_router
from backend.app.api.routes.analytics import router as analytics_router
from backend.app.api.routes.alerts import router as alerts_router
from backend.app.api.routes.sheets import router as sheets_router
from backend.app.api.routes.trading import router as trading_router
from backend.app.api.routes.payoff import router as payoff_router
from backend.app.api.routes.snapshots import router as snapshots_router
from backend.app.api.routes.risk_hedging import router as risk_hedging_router
from backend.app.api.routes.algo_execution import router as algo_execution_router
from backend.app.api.routes.screener_backtest import router as screener_backtest_router
from backend.app.api.routes.order_flow import router as order_flow_router
from backend.app.api.routes.sensitivity_stress import router as sensitivity_stress_router
from backend.app.api.routes.vol_arbitrage import router as vol_arbitrage_router
from backend.app.api.routes.pin_risk_settlement import router as pin_risk_settlement_router
from backend.app.api.routes.market_maker import router as market_maker_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["Health"])
api_router.include_router(status_router, tags=["Status"])
api_router.include_router(auth_router, tags=["Angel One Authentication"])
api_router.include_router(instruments_router, tags=["Instrument Master"])
api_router.include_router(subscriptions_router, tags=["Token Subscriptions & WebSocket"])
api_router.include_router(quotes_router, tags=["Quote Engine & Live State"])
api_router.include_router(option_chain_router, tags=["Option Chain Matrix"])
api_router.include_router(greeks_router, tags=["Black-Scholes Greeks & IV Engine"])
api_router.include_router(analytics_router, tags=["Strategy & Multi-Strike Analytics"])
api_router.include_router(alerts_router, tags=["Alerts & Threshold Monitoring"])
api_router.include_router(sheets_router, tags=["Google Sheets & External Export Engine"])
api_router.include_router(trading_router, tags=["Paper Trading & Order Execution"])
api_router.include_router(payoff_router, tags=["Strategy Payoff & Risk Profile"])
api_router.include_router(snapshots_router, tags=["Historical Snapshots & Market Replay"])
api_router.include_router(risk_hedging_router, tags=["Portfolio Greeks, Risk & Hedging Engine"])
api_router.include_router(algo_execution_router, tags=["Algorithmic Order Slicing & Execution Engine"])
api_router.include_router(screener_backtest_router, tags=["Options Screener & Quantitative Strategy Backtester Engine"])
api_router.include_router(order_flow_router, tags=["Order Book Microstructure & Institutional Flow Scanner"])
api_router.include_router(sensitivity_stress_router, tags=["Greeks Sensitivity & Stress Scenario Engine"])
api_router.include_router(vol_arbitrage_router, tags=["Volatility Arbitrage & Calendar Spreads Engine"])
api_router.include_router(pin_risk_settlement_router, tags=["Pin-Risk & Institutional Settlement Engine"])
api_router.include_router(market_maker_router, tags=["Institutional Market Maker & FIX Gateway Engine"])

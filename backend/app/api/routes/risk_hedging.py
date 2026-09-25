from typing import Dict, Any, List, Optional

try:
    from fastapi import APIRouter, Query, HTTPException, Body
    from pydantic import BaseModel, Field
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
    def Query(*args, **kwargs):
        return kwargs.get('default', Ellipsis)
    def Body(*args, **kwargs):
        return kwargs.get('default', Ellipsis)
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            self.status_code = status_code
            self.detail = detail
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        def dict(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
    def Field(*args, **kwargs):
        return kwargs.get("default", None)

from backend.app.services.trading.risk_and_hedging import risk_hedging_engine
from backend.app.services.trading.order_manager import PaperTradingEngine

# Use singleton paper trading engine if imported or instance
_paper_engine = PaperTradingEngine(initial_capital=1000000.0)

router = APIRouter(prefix="/risk", tags=["Portfolio Greeks, Risk & Hedging Engine"])


class PositionItemSchema(BaseModel):
    symbol: str
    underlying: str
    netQty: int
    ltp: float = 0.0
    buyAvg: float = 0.0
    sellAvg: float = 0.0


class AnalyzePortfolioRiskRequest(BaseModel):
    underlying: str = "CRUDEOIL"
    positions: List[PositionItemSchema] = []
    capital: float = 1000000.0
    spot_override: Optional[float] = None


class ExecuteHedgeRequest(BaseModel):
    underlying: str
    symbol: str
    action: str  # "BUY" or "SELL"
    quantity: int
    product_type: str = "INTRADAY"


@router.post("/analyze", summary="Analyze Net Greeks, VaR, Hedging, and Stress Tests")
def analyze_portfolio_risk(req: AnalyzePortfolioRiskRequest) -> Dict[str, Any]:
    """
    Computes Net Portfolio Greeks (Delta, Gamma, Theta, Vega),
    1-day Parametric Value-at-Risk (VaR 99%),
    delta/vega hedge suggestions (Futures or Options),
    and 6 Macro Stress-Testing Shock scenarios.
    """
    try:
        positions_dicts = [p.dict() for p in req.positions]
        analysis = risk_hedging_engine.analyze_portfolio_risk(
            underlying=req.underlying,
            positions=positions_dicts,
            capital=req.capital,
            spot_override=req.spot_override
        )
        return {
            "status": "success",
            "data": analysis.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/portfolio/{underlying}", summary="Analyze Active Paper Trading Portfolio Risk")
def get_live_portfolio_risk(
    underlying: str,
    capital: float = Query(default=1000000.0, description="Trading Capital in ₹")
) -> Dict[str, Any]:
    """
    Pulls live open positions from the Paper Trading engine
    and computes the portfolio risk & hedge dashboard.
    """
    try:
        # Pull active positions from paper trading engine
        active_pos_list = list(_paper_engine.positions.values())
        analysis = risk_hedging_engine.analyze_portfolio_risk(
            underlying=underlying,
            positions=active_pos_list,
            capital=capital
        )
        return {
            "status": "success",
            "data": analysis.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/hedge/execute", summary="Execute Recommended Hedge Order")
def execute_hedge_order(req: ExecuteHedgeRequest) -> Dict[str, Any]:
    """
    Places an automated hedge order (Futures or Options) into the Paper Trading engine
    to neutralize portfolio Delta or Vega exposure.
    """
    try:
        order_res = _paper_engine.place_order(
            symbol=req.symbol,
            token="HEDGE_TOKEN",
            underlying=req.underlying,
            transaction_type=req.action,
            quantity=req.quantity,
            product_type=req.product_type
        )
        return {
            "status": "success",
            "message": f"Hedge order {req.action} {req.quantity}x {req.symbol} placed.",
            "order": order_res
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

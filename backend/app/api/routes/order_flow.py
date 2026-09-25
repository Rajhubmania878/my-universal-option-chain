"""
Real-Time Options Order Book Microstructure, Liquidity Depth & Institutional Flow Routes (Phase 21).

Endpoints:
- GET /order-flow/depth/{symbol} : Get 5-depth / 20-depth Order Book with Microprice & Imbalance
- GET /order-flow/block-trades : Get Institutional Block & Sweep Trades Tape
- POST /order-flow/simulate-trade : Inject a simulated trade event onto the tape
- GET /order-flow/strike-cvd/{underlying} : Get Cumulative Volume Delta (CVD) footprint by strike
"""
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

from backend.app.services.analytics.order_flow_engine import order_flow_engine

router = APIRouter(prefix="/order-flow", tags=["Order Book Microstructure & Institutional Flow Scanner"])


class SimulateTradeRequest(BaseModel):
    symbol: str = "CRUDEOIL24OCT8900CE"
    underlying: str = "CRUDEOIL"
    strike: float = 8900.0
    option_type: str = "CE"
    price: float = 148.5
    quantity: int = 1000
    side: str = "BUY"
    trade_type: str = "SWEEP"


@router.get("/depth/{symbol}", summary="Get Level-2 Order Book Depth & Microstructure Imbalance")
def get_order_book_depth(
    symbol: str,
    levels: int = Query(default=5, ge=1, le=20, description="Depth levels (5 or 20)")
) -> Dict[str, Any]:
    """
    Returns live Bid/Ask depth ladder, spread, microprice fair value, and order book imbalance (OBI).
    """
    try:
        depth = order_flow_engine.get_order_book_depth(symbol=symbol, depth_levels=levels)
        return {
            "status": "success",
            "data": depth.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/block-trades", summary="Get Institutional Block & Sweep Trades Tape")
def get_block_trades(
    underlying: Optional[str] = Query(default="ALL", description="Filter by underlying symbol"),
    min_turnover: float = Query(default=0.0, description="Minimum turnover in INR"),
    sentiment: Optional[str] = Query(default="ALL", description="Filter by flow sentiment")
) -> Dict[str, Any]:
    """
    Returns real-time options tape highlighting large blocks, sweeps, and institutional aggression.
    """
    try:
        trades = order_flow_engine.get_large_block_trades(
            underlying=underlying,
            min_turnover=min_turnover,
            sentiment=sentiment
        )
        return {
            "status": "success",
            "count": len(trades),
            "data": trades
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/simulate-trade", summary="Simulate Tape Execution Event")
def simulate_trade_execution(req: SimulateTradeRequest) -> Dict[str, Any]:
    """
    Injects a real-time trade event onto the institutional flow tape.
    """
    try:
        event = order_flow_engine.add_simulated_trade(
            symbol=req.symbol,
            underlying=req.underlying,
            strike=req.strike,
            option_type=req.option_type,
            price=req.price,
            qty=req.quantity,
            side=req.side,
            ttype=req.trade_type
        )
        return {
            "status": "success",
            "data": event
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/strike-cvd/{underlying}", summary="Get Cumulative Volume Delta (CVD) Footprint by Strike")
def get_strike_cvd(
    underlying: str = "CRUDEOIL"
) -> Dict[str, Any]:
    """
    Returns strike-by-strike cumulative volume delta (CVD) to visualize net institutional aggression.
    """
    try:
        cvd_data = order_flow_engine.get_strike_cvd_footprint(underlying=underlying)
        return {
            "status": "success",
            "underlying": underlying,
            "count": len(cvd_data),
            "data": cvd_data
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

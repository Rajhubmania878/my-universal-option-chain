"""
REST API routes for Paper Trading, Multi-Leg Orders, Live P&L, and Portfolio Positions.
"""
from typing import Dict, Any, List, Optional
try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
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
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            self.status_code = status_code
            self.detail = detail
    class BaseModel:
        pass

from backend.app.services.trading.order_manager import (
    paper_trading_engine,
    OrderType,
    OrderAction
)

router = APIRouter(prefix="/trading", tags=["Paper Trading & Execution"])

class SingleOrderRequest(BaseModel):
    symbol: str
    token: str = "0"
    underlying: str
    transaction_type: str  # BUY or SELL
    quantity: int
    order_type: str = "MARKET"
    price: float = 0.0
    stoploss: Optional[float] = None
    target: Optional[float] = None
    product_type: str = "INTRADAY"

class StrategyOrderRequest(BaseModel):
    strategy_name: str
    underlying: str
    legs: List[Dict[str, Any]]
    product_type: str = "INTRADAY"

class PnlUpdateRequest(BaseModel):
    quotes: Dict[str, float]

@router.get("/portfolio")
def get_portfolio_summary():
    """
    Get current cash balance, portfolio value, active positions count, and position book.
    """
    return paper_trading_engine.update_live_pnl({})

@router.post("/order")
def place_order(req: SingleOrderRequest):
    """
    Execute a single-leg paper order with margin verification and risk controls.
    """
    try:
        result = paper_trading_engine.place_order(
            symbol=req.symbol,
            token=req.token,
            underlying=req.underlying,
            transaction_type=req.transaction_type,
            quantity=req.quantity,
            order_type=req.order_type,
            price=req.price,
            stoploss=req.stoploss,
            target=req.target,
            product_type=req.product_type
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/strategy")
def place_strategy(req: StrategyOrderRequest):
    """
    Execute a multi-leg options strategy (Straddle, Strangle, Iron Condor, Bull Call Spread).
    """
    if not req.legs:
        raise HTTPException(status_code=400, detail="Strategy must contain at least one leg")

    return paper_trading_engine.place_multi_leg_strategy(
        strategy_name=req.strategy_name,
        underlying=req.underlying,
        legs=req.legs,
        product_type=req.product_type
    )

@router.post("/pnl")
def recalculate_pnl(req: PnlUpdateRequest):
    """
    Update mark-to-market live P&L given a map of symbol/token to current market LTP.
    """
    return paper_trading_engine.update_live_pnl(req.quotes)

@router.post("/square-off-all")
def emergency_square_off():
    """
    Emergency square-off all active open positions.
    """
    return paper_trading_engine.square_off_all_positions()

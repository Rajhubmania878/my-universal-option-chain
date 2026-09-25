"""
Strategy Payoff & Risk Profile API Routes (Phase 16).
Provides:
- Custom multi-leg strategy payoff evaluation
- Pre-built option strategy templates (Straddles, Strangles, Spreads, Condors)
- Mark-to-market T+N target pricing curves
- 2D Spot vs IV What-If Scenario Matrix
"""
from typing import List, Optional, Dict, Any
try:
    from fastapi import APIRouter, HTTPException, Query
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
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            self.status_code = status_code
            self.detail = detail
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    def Field(*args, **kwargs):
        return kwargs.get("default", None)
    def Query(default=None, **kwargs):
        return default

from backend.app.services.analytics.payoff_simulator import (
    strategy_payoff_engine,
    StrategyLeg
)
from backend.app.services.market.quote_engine import quote_engine
from backend.app.services.angel.instrument_master import instrument_master

router = APIRouter(prefix="/analytics/payoff", tags=["Strategy Payoff & Risk Profile"])

class LegInput(BaseModel):
    symbol: str
    option_type: str = Field(..., description="CE or PE")
    strike: float
    action: str = Field(..., description="BUY or SELL")
    quantity: int = Field(..., gt=0)
    entry_price: float = Field(..., ge=0.0)
    iv: float = Field(default=20.0, description="Implied Volatility in percentage, e.g. 19.5")

class PayoffEvaluationRequest(BaseModel):
    strategy_name: str = "Custom Strategy"
    underlying: str = "CRUDEOIL"
    current_spot: Optional[float] = None
    legs: List[LegInput]
    tte_days: float = Field(default=7.0, ge=0.01)
    target_days: float = Field(default=0.0, ge=0.0, description="T+N days forward from now (0 = T+0)")
    iv_shift_pct: float = Field(default=0.0, description="What-if IV adjustment, e.g. +2.0 or -3.0")
    range_pct: float = Field(default=0.10, ge=0.01, le=0.50, description="Spot curve range +/- pct")

@router.post("/evaluate")
async def evaluate_custom_payoff(request: PayoffEvaluationRequest) -> Dict[str, Any]:
    """
    Evaluate payoff curves, breakevens, max profit/loss, POP, net Greeks,
    and 2D What-If Scenario matrix for custom multi-leg strategy.
    """
    spot = request.current_spot
    if spot is None or spot <= 0:
        quote = quote_engine.get_underlying_quote(request.underlying)
        spot = quote.get("ltp", 8908.0) if quote else 8908.0

    domain_legs = [
        StrategyLeg(
            symbol=leg.symbol,
            option_type=leg.option_type.upper(),
            strike=leg.strike,
            action=leg.action.upper(),
            quantity=leg.quantity,
            entry_price=leg.entry_price,
            iv=leg.iv
        )
        for leg in request.legs
    ]

    try:
        result = strategy_payoff_engine.evaluate_strategy_payoff(
            strategy_name=request.strategy_name,
            underlying=request.underlying,
            current_spot=spot,
            legs=domain_legs,
            tte_days=request.tte_days,
            target_days=request.target_days,
            iv_shift_pct=request.iv_shift_pct,
            range_pct=request.range_pct
        )
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/template")
async def get_strategy_template_payoff(
    template_name: str = Query("short_straddle", description="short_straddle, bull_call_spread, bear_put_spread, iron_condor"),
    underlying: str = Query("CRUDEOIL", description="Underlying symbol"),
    spot: Optional[float] = Query(None, description="Underlying spot price"),
    step: Optional[float] = Query(None, description="Strike step distance"),
    target_days: float = Query(0.0, description="T+N days from now"),
    iv_shift: float = Query(0.0, description="What-if IV shift pct")
) -> Dict[str, Any]:
    """
    Generate instant payoff and what-if simulation for standard options strategy templates.
    """
    u_symbol = underlying.upper()
    quote = quote_engine.get_underlying_quote(u_symbol)
    cur_spot = spot or (quote.get("ltp") if quote else (8908.0 if u_symbol == "CRUDEOIL" else 23500.0))

    cur_step = step or (100.0 if u_symbol in ["CRUDEOIL", "BANKNIFTY", "SENSEX"] else 50.0)
    atm_strike = round(cur_spot / cur_step) * cur_step

    t_name = template_name.lower().strip()

    if t_name == "short_straddle":
        legs = strategy_payoff_engine.create_short_straddle(
            underlying=u_symbol,
            atm_strike=atm_strike,
            premium_ce=round(cur_spot * 0.027, 1),
            premium_pe=round(cur_spot * 0.026, 1),
            iv=20.0,
            qty=100
        )
        s_name = f"{u_symbol} ATM Short Straddle"
    elif t_name == "bull_call_spread":
        legs = strategy_payoff_engine.create_bull_call_spread(
            underlying=u_symbol,
            atm_strike=atm_strike,
            step=cur_step,
            buy_ce_price=round(cur_spot * 0.028, 1),
            sell_ce_price=round(cur_spot * 0.016, 1),
            iv=20.0,
            qty=100
        )
        s_name = f"{u_symbol} Bull Call Spread"
    elif t_name == "bear_put_spread":
        legs = strategy_payoff_engine.create_bear_put_spread(
            underlying=u_symbol,
            atm_strike=atm_strike,
            step=cur_step,
            buy_pe_price=round(cur_spot * 0.028, 1),
            sell_pe_price=round(cur_spot * 0.016, 1),
            iv=20.0,
            qty=100
        )
        s_name = f"{u_symbol} Bear Put Spread"
    elif t_name == "iron_condor":
        legs = strategy_payoff_engine.create_iron_condor(
            underlying=u_symbol,
            atm_strike=atm_strike,
            step=cur_step,
            otm_call_short=round(cur_spot * 0.018, 1),
            otm_call_long=round(cur_spot * 0.011, 1),
            otm_put_short=round(cur_spot * 0.017, 1),
            otm_put_long=round(cur_spot * 0.010, 1),
            iv=21.0,
            qty=100
        )
        s_name = f"{u_symbol} Iron Condor"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported template: {template_name}")

    result = strategy_payoff_engine.evaluate_strategy_payoff(
        strategy_name=s_name,
        underlying=u_symbol,
        current_spot=cur_spot,
        legs=legs,
        tte_days=7.0,
        target_days=target_days,
        iv_shift_pct=iv_shift
    )

    return {"status": "success", "data": result}

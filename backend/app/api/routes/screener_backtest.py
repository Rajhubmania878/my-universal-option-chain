"""
Options Screener & Quantitative Strategy Backtester API Routes (Phase 20).
Endpoints:
- POST /screener/query : Filter options across criteria
- POST /backtest/run : Run quantitative strategy backtest simulation
- GET /backtest/presets : Get standard predefined strategy configurations
- GET /screener/tags : Get available screener tags
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

from backend.app.services.analytics.screener_backtest import screener_backtest_engine

router = APIRouter(prefix="/screener-backtest", tags=["Options Screener & Quantitative Strategy Backtester Engine"])


class ScreenerQueryRequest(BaseModel):
    underlying: Optional[str] = "CRUDEOIL"
    min_iv_rank: Optional[float] = None
    max_iv_rank: Optional[float] = None
    min_oi_chg_pct: Optional[float] = None
    min_volume: Optional[int] = None
    option_type: Optional[str] = "ALL"  # "CE", "PE", "ALL"
    min_delta: Optional[float] = None
    max_delta: Optional[float] = None
    tag_filter: Optional[str] = "ALL"
    sort_by: str = "screener_score"
    sort_desc: bool = True


class BacktestRunRequest(BaseModel):
    strategy_name: str = "IRON_CONDOR"
    underlying: str = "CRUDEOIL"
    start_date: str = "2024-01-01"
    end_date: str = "2024-06-30"
    initial_capital: float = 1000000.0
    profit_target_pct: float = 50.0
    stop_loss_pct: float = 100.0
    dte_entry: int = 30
    dte_exit: int = 5


@router.post("/screener/query", summary="Run Multi-Factor Options Screener Query")
def query_options_screener(req: ScreenerQueryRequest) -> Dict[str, Any]:
    """
    Screens options universe based on IV Rank, OI Buildup, Greeks, and liquidity criteria.
    """
    try:
        results = screener_backtest_engine.run_screener_query(
            underlying=req.underlying,
            min_iv_rank=req.min_iv_rank,
            max_iv_rank=req.max_iv_rank,
            min_oi_chg_pct=req.min_oi_chg_pct,
            min_volume=req.min_volume,
            option_type=req.option_type,
            min_delta=req.min_delta,
            max_delta=req.max_delta,
            tag_filter=req.tag_filter,
            sort_by=req.sort_by,
            sort_desc=req.sort_desc
        )
        return {
            "status": "success",
            "count": len(results),
            "data": results
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/backtest/run", summary="Execute Quantitative Strategy Backtest")
def run_strategy_backtest(req: BacktestRunRequest) -> Dict[str, Any]:
    """
    Simulates strategy historical performance with equity curve, drawdown, win-rate, and Sharpe ratio.
    """
    try:
        result = screener_backtest_engine.run_strategy_backtest(
            strategy_name=req.strategy_name,
            underlying=req.underlying,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=req.initial_capital,
            profit_target_pct=req.profit_target_pct,
            stop_loss_pct=req.stop_loss_pct,
            dte_entry=req.dte_entry,
            dte_exit=req.dte_exit
        )
        return {
            "status": "success",
            "data": result.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/presets", summary="Get Quantitative Strategy Presets")
def get_strategy_presets() -> Dict[str, Any]:
    """
    Returns pre-configured strategies for rapid backtesting.
    """
    presets = [
        {
            "id": "IRON_CONDOR",
            "name": "Delta-Neutral Iron Condor (4-Leg)",
            "description": "Sells OTM Put and OTM Call wings with long protection wings. Captures theta decay in rangebound markets.",
            "target_iv_rank": "> 50 (High Vol)",
            "ideal_regime": "Low / Moderate Historical Vol",
            "recommended_dte": "30-45 DTE"
        },
        {
            "id": "SHORT_STRADDLE",
            "name": "ATM Short Straddle (Premium Harvesting)",
            "description": "Simultaneously sells ATM Call and ATM Put to harvest rapid theta decay approaching expiry.",
            "target_iv_rank": "> 70 (Elevated Vol)",
            "ideal_regime": "Mean Reverting Flat Market",
            "recommended_dte": "7-14 DTE"
        },
        {
            "id": "BULL_CALL_SPREAD",
            "name": "Bull Call Debit Spread",
            "description": "Long ATM Call financed by selling higher strike OTM Call. Directional upside with bounded risk.",
            "target_iv_rank": "< 40 (Low Vol)",
            "ideal_regime": "Trending Bullish",
            "recommended_dte": "20-40 DTE"
        },
        {
            "id": "BEAR_PUT_SPREAD",
            "name": "Bear Put Debit Spread",
            "description": "Long ATM Put financed by selling lower strike OTM Put. Directional downside with bounded risk.",
            "target_iv_rank": "< 40 (Low Vol)",
            "ideal_regime": "Trending Bearish",
            "recommended_dte": "20-40 DTE"
        },
        {
            "id": "CALENDAR_SPREAD",
            "name": "Time Horizon Calendar Spread",
            "description": "Sells near-month expiry option while buying far-month option at identical strike.",
            "target_iv_rank": "Term Structure Contango",
            "ideal_regime": "Low Realized Vol",
            "recommended_dte": "Near: 7 DTE, Far: 35 DTE"
        },
        {
            "id": "JADE_LIZARD",
            "name": "Jade Lizard (Skew Harvesting)",
            "description": "Combines a short OTM Put with a Bear Call Spread. Zero upside risk when total credit exceeds call spread width.",
            "target_iv_rank": "> 60 (High Skew)",
            "ideal_regime": "Neutral to Bullish Skew",
            "recommended_dte": "30-45 DTE"
        }
    ]
    return {
        "status": "success",
        "data": presets
    }

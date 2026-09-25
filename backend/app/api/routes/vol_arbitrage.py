"""
FastAPI Route Handlers for Volatility Arbitrage & Calendar Spreads Engine (Phase 23).
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
        return kwargs.get('default', None)

from backend.app.services.analytics.vol_arbitrage_engine import (
    volatility_arbitrage_engine,
    CalendarSpreadOpportunity,
    ParityArbitrageSignal
)

router = APIRouter(prefix="/vol-arbitrage", tags=["Volatility & Calendar Arbitrage Engine"])


class CalendarSpreadScanRequest(BaseModel):
    underlying: str = Field(default="CRUDEOIL", description="Underlying symbol (e.g. CRUDEOIL, NIFTY, BANKNIFTY)")
    spot: float = Field(default=8908.0, description="Current underlying spot/futures price")
    strikes: Optional[List[float]] = Field(default=None, description="Optional custom list of strikes")


class ParityArbitrageScanRequest(BaseModel):
    underlying: str = Field(default="CRUDEOIL", description="Underlying symbol")
    spot: float = Field(default=8908.0, description="Current underlying spot price")
    strikes: Optional[List[float]] = Field(default=None, description="Strikes to check")
    risk_free_rate: float = Field(default=0.07, description="Risk-free interest rate (e.g. 0.07 for 7%)")


@router.get("/calendar-spreads", summary="Scan Calendar Spread Opportunities")
def get_calendar_spreads(
    underlying: str = Query(default="CRUDEOIL"),
    spot: float = Query(default=8908.0)
) -> Dict[str, Any]:
    results = volatility_arbitrage_engine.scan_calendar_spreads(underlying=underlying, spot=spot)
    return {
        "status": "success",
        "underlying": underlying,
        "count": len(results),
        "data": [r.to_dict() for r in results]
    }


@router.post("/calendar-spreads/scan", summary="Custom Calendar Spread Scan")
def scan_custom_calendar_spreads(req: CalendarSpreadScanRequest = Body(...)) -> Dict[str, Any]:
    results = volatility_arbitrage_engine.scan_calendar_spreads(
        underlying=req.underlying,
        spot=req.spot,
        strikes=req.strikes
    )
    return {
        "status": "success",
        "underlying": req.underlying,
        "count": len(results),
        "data": [r.to_dict() for r in results]
    }


@router.get("/parity-arbitrage", summary="Scan Put-Call Parity Mispricings")
def get_parity_arbitrage(
    underlying: str = Query(default="CRUDEOIL"),
    spot: float = Query(default=8908.0),
    risk_free_rate: float = Query(default=0.07)
) -> Dict[str, Any]:
    results = volatility_arbitrage_engine.scan_parity_arbitrage(
        underlying=underlying,
        spot=spot,
        risk_free_rate=risk_free_rate
    )
    return {
        "status": "success",
        "underlying": underlying,
        "count": len(results),
        "data": [r.to_dict() for r in results]
    }

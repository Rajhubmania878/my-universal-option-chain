from typing import Dict, Any, Optional

try:
    from fastapi import APIRouter, Query, HTTPException, Path
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
    def Path(*args, **kwargs):
        return kwargs.get('default', Ellipsis)

from backend.app.services.analytics.straddle_engine import straddle_engine
from backend.app.services.analytics.max_pain_engine import max_pain_engine
from backend.app.services.analytics.volatility_engine import volatility_engine
from backend.app.services.analytics.buildup_tracker import buildup_tracker

router = APIRouter(prefix="/analytics", tags=["Strategy & Multi-Strike Analytics"])

@router.get("/straddle/{underlying}", summary="Get ATM Straddle Premium & Breakevens")
def get_atm_straddle(
    underlying: str,
    expiry: Optional[str] = Query(default=None, description="Contract expiry (e.g. 19FEB2026)"),
    exchange: Optional[str] = Query(default=None, description="Exchange (NFO or MCX)")
) -> Dict[str, Any]:
    """
    Computes ATM Straddle analytics:
    - Combined Straddle Premium (CE LTP + PE LTP)
    - Lot Cost (Premium * Lot Size)
    - Upper and Lower Breakevens
    - Implied Move Percentage (+/- %)
    - Combined Portfolio Greeks (Net Delta, Gamma, Theta, Vega)
    """
    try:
        details = straddle_engine.calculate_atm_straddle(
            underlying=underlying,
            expiry=expiry,
            exchange=exchange
        )
        return {
            "status": "success",
            "data": details.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/strangle/{underlying}", summary="Get Strangle Strategy Details (OTM Offsets)")
def get_strangle(
    underlying: str,
    expiry: Optional[str] = Query(default=None),
    otm_offset: int = Query(default=1, ge=1, le=10, description="OTM strike offset from ATM"),
    exchange: Optional[str] = Query(default=None)
) -> Dict[str, Any]:
    """
    Computes Strangle Strategy:
    - OTM Call Strike & OTM Put Strike
    - Combined Strangle Premium
    - Strangle Lot Cost
    - Upper & Lower Breakevens
    - Combined Greeks
    """
    try:
        details = straddle_engine.calculate_strangle(
            underlying=underlying,
            expiry=expiry,
            otm_offset=otm_offset,
            exchange=exchange
        )
        return {
            "status": "success",
            "data": details.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/multi-strike/{underlying}", summary="Get Multi-Strike Comparative Analytics")
def get_multi_strike_comparison(
    underlying: str,
    expiry: Optional[str] = Query(default=None),
    strike_window: int = Query(default=5, ge=1, le=20, description="Strikes around ATM"),
    exchange: Optional[str] = Query(default=None)
) -> Dict[str, Any]:
    """
    Compares synthetic straddles across multiple strikes around ATM:
    - Strike, Combined Premium, Combined OI, PCR, Net Delta, Net Theta, Implied Move %
    - Highlights Cheapest Straddle Strike & Maximum OI Strike
    """
    try:
        analysis = straddle_engine.multi_strike_comparison(
            underlying=underlying,
            expiry=expiry,
            strike_window=strike_window,
            exchange=exchange
        )
        return {
            "status": "success",
            "data": analysis.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/max-pain/{underlying}", summary="Get Max Pain Strike & Payout Loss Curve")
def get_max_pain(
    underlying: str,
    expiry: Optional[str] = Query(default=None, description="Expiry date"),
    exchange: Optional[str] = Query(default=None, description="Exchange (NFO or MCX)")
) -> Dict[str, Any]:
    """
    Computes Max Pain analysis:
    - Strike minimizing cumulative cash loss for option writers at expiry
    - Cash loss curve across all candidate strikes
    - Distance to spot price and distance percentage
    - Complete PCR suite and sentiment classification
    """
    try:
        analysis = max_pain_engine.calculate_max_pain(
            underlying=underlying,
            expiry=expiry,
            exchange=exchange
        )
        return {
            "status": "success",
            "data": analysis.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/pcr/{underlying}", summary="Get Put-Call Ratio (PCR) Suite & Market Sentiment")
def get_pcr_suite(
    underlying: str,
    expiry: Optional[str] = Query(default=None),
    exchange: Optional[str] = Query(default=None)
) -> Dict[str, Any]:
    """
    Computes comprehensive PCR analytics:
    - OI PCR (Total Put OI / Total Call OI)
    - Volume PCR (Total Put Volume / Total Call Volume)
    - OI Change PCR
    - Market sentiment tag and qualitative interpretation
    """
    try:
        analysis = max_pain_engine.calculate_max_pain(
            underlying=underlying,
            expiry=expiry,
            exchange=exchange
        )
        return {
            "status": "success",
            "data": {
                "underlying": analysis.underlying,
                "expiry": analysis.expiry,
                "spot_price": analysis.spot_price,
                "pcr_suite": analysis.pcr_suite.to_dict(),
                "total_call_oi": analysis.total_call_oi,
                "total_put_oi": analysis.total_put_oi
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/volatility/{underlying}", summary="Get Historical Volatility, IV Rank, and Regime")
def get_volatility_analysis(
    underlying: str,
    expiry: Optional[str] = Query(default=None, description="Expiry date"),
    exchange: Optional[str] = Query(default=None, description="Exchange (NFO or MCX)")
) -> Dict[str, Any]:
    """
    Computes Volatility Analysis:
    - Realized Close-to-Close Historical Volatility (HV 10d, 20d, 30d)
    - Parkinson High-Low Realized Volatility (20d)
    - 52-Week IV Rank & IV Percentile
    - Volatility Risk Premium (VRP = Current ATM IV - Realized HV 20d)
    - Volatility Regime classification and option strategy recommendations
    """
    try:
        analysis = volatility_engine.analyze_volatility(
            underlying=underlying,
            expiry=expiry,
            exchange=exchange
        )
        return {
            "status": "success",
            "data": analysis.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/buildup/{underlying}", summary="Get OI Buildup Classification, Spurts & Volume Spikes")
def get_buildup_analysis(
    underlying: str,
    expiry: Optional[str] = Query(default=None, description="Expiry date"),
    strike_window: int = Query(default=10, ge=1, le=25, description="Strike window around ATM"),
    exchange: Optional[str] = Query(default=None, description="Exchange (NFO or MCX)")
) -> Dict[str, Any]:
    """
    Classifies real-time option contract positioning:
    - Long Buildup (Price UP, OI UP)
    - Short Buildup (Price DOWN, OI UP)
    - Long Unwinding (Price DOWN, OI DOWN)
    - Short Covering (Price UP, OI DOWN)
    - Abnormal OI Spurts (> 15% change) & Relative Volume Spikes (> 2x average)
    - Top OI Gainers, Losers, and Volume Active contracts
    """
    try:
        analysis = buildup_tracker.analyze_buildup(
            underlying=underlying,
            expiry=expiry,
            strike_window=strike_window,
            exchange=exchange
        )
        return {
            "status": "success",
            "data": analysis.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))




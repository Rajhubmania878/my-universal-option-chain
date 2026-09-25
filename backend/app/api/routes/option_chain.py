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

from backend.app.services.analytics.option_chain_builder import option_chain_builder

router = APIRouter(prefix="/option-chain", tags=["Option Chain Matrix"])

@router.get("/{underlying}", summary="Get Full Option Chain Matrix (ATM ± N Strikes)")
def get_option_chain(
    underlying: str,
    expiry: Optional[str] = Query(default=None, description="Expiry date string (e.g. 19FEB2026, 26MAR2026)"),
    strike_window: int = Query(default=10, ge=1, le=50, description="Strikes above and below ATM to include"),
    exchange: Optional[str] = Query(default=None, description="Exchange segment (NFO, MCX, BFO)")
) -> Dict[str, Any]:
    """
    Returns unified Option Chain Matrix:
    - Strike ascending alignment
    - Call side (LTP, Volume, OI, OI change, Bid/Ask, Moneyness, Greeks placeholder)
    - Put side (LTP, Volume, OI, OI change, Bid/Ask, Moneyness, Greeks placeholder)
    - Summary (Spot, ATM, Lot size, Total Call OI, Total Put OI, PCR, Max OI strikes)
    """
    matrix = option_chain_builder.build(
        underlying=underlying,
        expiry=expiry,
        strike_window=strike_window,
        exchange=exchange
    )
    return {
        "status": "success",
        "data": matrix.to_dict()
    }

@router.get("/{underlying}/summary", summary="Get Fast Summary Metrics for Underlying")
def get_option_chain_summary(
    underlying: str,
    expiry: Optional[str] = Query(default=None),
    exchange: Optional[str] = Query(default=None)
) -> Dict[str, Any]:
    """Returns rapid summary (PCR, Spot, ATM, Max Call/Put OI Resistance & Support) without all strike rows."""
    matrix = option_chain_builder.build(
        underlying=underlying,
        expiry=expiry,
        strike_window=5,
        exchange=exchange
    )
    return {
        "status": "success",
        "summary": matrix.summary.to_dict()
    }

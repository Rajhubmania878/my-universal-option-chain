from typing import List, Optional, Dict, Any

try:
    from fastapi import APIRouter, Query, HTTPException
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

try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        def dict(self):
            return self.__dict__
    def Field(*args, **kwargs):
        return kwargs.get('default', Ellipsis)

from backend.app.services.angel.instrument_master import instrument_master

router = APIRouter(prefix="/instruments", tags=["Instrument Master"])

class OptionMatrixItem(BaseModel):
    strike: float
    exchange: str
    lot_size: int
    tick_size: float
    ce_token: Optional[str] = None
    ce_symbol: Optional[str] = None
    pe_token: Optional[str] = None
    pe_symbol: Optional[str] = None

class OptionChainMatrixResponse(BaseModel):
    underlying: str
    expiry: str
    exchange: str
    total_strikes: int
    chain: List[OptionMatrixItem]

@router.get("/underlyings", summary="List Supported Underlying Assets")
def get_underlyings() -> List[Dict[str, Any]]:
    """
    Returns dynamically discovered underlying assets (Index, Equity F&O, Commodity).
    Never hardcoded.
    """
    return instrument_master.get_supported_underlyings()

@router.get("/expiries", summary="Get Available Expiries for an Underlying")
def get_expiries(
    underlying: str = Query(..., description="Underlying symbol, e.g. NIFTY, CRUDEOIL, BANKNIFTY"),
    exchange: Optional[str] = Query(None, description="Exchange segment, e.g. NFO, MCX")
) -> List[str]:
    """
    Returns chronologically sorted expiries for the given underlying asset.
    """
    return instrument_master.get_expiries(underlying, exchange)

@router.get("/strikes", summary="Get Available Strikes for Underlying & Expiry")
def get_strikes(
    underlying: str = Query(..., description="Underlying symbol"),
    expiry: str = Query(..., description="Expiry date, e.g. 19FEB2026, 26MAR2026"),
    exchange: Optional[str] = Query(None, description="Exchange segment")
) -> List[float]:
    """
    Returns numerically sorted strike prices for the chosen underlying and expiry.
    """
    return instrument_master.get_strikes(underlying, expiry, exchange)

@router.get("/chain-matrix", response_model=OptionChainMatrixResponse, summary="Get Dynamic Option Chain Tokens Matrix")
def get_chain_matrix(
    underlying: str = Query(..., description="Underlying symbol"),
    expiry: str = Query(..., description="Expiry date"),
    exchange: Optional[str] = Query(None, description="Exchange segment")
) -> OptionChainMatrixResponse:
    """
    Returns complete strike matrix mapped with CE & PE tokens, symbols, lot size, and tick size.
    Ready for WebSocket batch subscriptions.
    """
    matrix = instrument_master.get_option_chain_tokens(underlying, expiry, exchange)
    exch = exchange or (matrix[0]["exchange"] if matrix else "NFO")
    
    return OptionChainMatrixResponse(
        underlying=underlying.upper(),
        expiry=expiry.upper(),
        exchange=exch,
        total_strikes=len(matrix),
        chain=[OptionMatrixItem(**item) for item in matrix]
    )

@router.get("/search", summary="Search Instruments by Symbol or Name")
def search_instruments(
    q: str = Query(..., description="Search query string"),
    limit: int = Query(20, description="Max results to return")
) -> List[Dict[str, Any]]:
    """
    Fast prefix/fuzzy search across all indexed instruments.
    """
    return instrument_master.search(q, limit)

@router.get("/token/{token}", summary="Lookup Instrument by Token")
def get_by_token(token: str) -> Dict[str, Any]:
    inst = instrument_master.get_instrument_by_token(token)
    if not inst:
        return {"error": "Instrument not found", "token": token}
    return inst.to_dict()

@router.post("/refresh", summary="Trigger Instrument Master Download & Refresh")
def refresh_master() -> Dict[str, Any]:
    count = instrument_master.load_from_url()
    return {
        "success": True,
        "total_instruments": count,
        "last_loaded": instrument_master.last_loaded_time
    }

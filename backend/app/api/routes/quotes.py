from typing import List, Dict, Any, Optional

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

from backend.app.services.market.quote_engine import quote_engine

router = APIRouter(prefix="/quotes", tags=["Quote Engine & Live State"])

class BatchQuotesRequest(BaseModel):
    tokens: List[str]
    max_age_seconds: Optional[float] = None

@router.get("/summary", summary="Get Quote Engine Health & Metrics")
def get_quote_engine_summary() -> Dict[str, Any]:
    return quote_engine.get_stats()

@router.get("/underlying/{underlying}", summary="Get Latest Quote for Underlying Spot / Future")
def get_underlying_quote(underlying: str) -> Dict[str, Any]:
    quote = quote_engine.get_underlying_quote(underlying)
    if not quote:
        return {
            "status": "not_found",
            "message": f"No active quote found for underlying {underlying.upper()}",
            "underlying": underlying.upper()
        }
    return {
        "status": "success",
        "quote": quote.to_dict()
    }

@router.get("/{token}", summary="Get Normalized Quote by Token")
def get_quote(
    token: str,
    max_age_seconds: Optional[float] = Query(default=None, description="Custom staleness threshold in seconds")
) -> Dict[str, Any]:
    quote = quote_engine.get_quote(token, max_age_seconds=max_age_seconds)
    if not quote:
        return {
            "status": "not_found",
            "token": token,
            "message": f"Quote for token {token} not found in state store"
        }
    return {
        "status": "success",
        "quote": quote.to_dict()
    }

@router.post("/batch", summary="Batch Fetch Normalized Quotes")
def get_batch_quotes(req: BatchQuotesRequest) -> Dict[str, Any]:
    results = quote_engine.get_quotes_batch(req.tokens, max_age_seconds=req.max_age_seconds)
    return {
        "count": len(req.tokens),
        "quotes": results
    }

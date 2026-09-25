from typing import List, Dict, Any, Optional

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

from backend.app.services.market.token_manager import token_manager, SubscriptionMode
from backend.app.services.market.websocket_manager import smart_websocket_manager

router = APIRouter(prefix="/subscriptions", tags=["Token Subscriptions & WebSocket"])

class SubscribeUnderlyingRequest(BaseModel):
    underlying: str
    expiry: str
    reference_price: float
    mode: int = SubscriptionMode.SNAPQUOTE
    exchange: Optional[str] = None

@router.get("/active", summary="Get Active Token Subscriptions")
def get_active_subscriptions() -> Dict[str, Any]:
    active = token_manager.get_active_tokens()
    return {
        "count": len(active),
        "subscriptions": active
    }

@router.get("/status", summary="Get WebSocket Stream & Token Manager Status")
def get_status() -> Dict[str, Any]:
    return {
        "websocket": smart_websocket_manager.get_status(),
        "token_manager": {
            "strike_window": token_manager.strike_window,
            "total_active": token_manager.get_subscription_count(),
            "atm_strikes": token_manager._current_atm_strikes,
            "expiries": token_manager._current_expiries,
        }
    }

@router.post("/subscribe-underlying", summary="Dynamically Subscribe Underlying ATM ± N Strikes")
def subscribe_underlying(req: SubscribeUnderlyingRequest) -> Dict[str, Any]:
    to_sub, to_unsub, atm = token_manager.update_underlying_subscriptions(
        underlying=req.underlying,
        expiry=req.expiry,
        reference_price=req.reference_price,
        mode=req.mode,
        exchange=req.exchange
    )
    return {
        "underlying": req.underlying.upper(),
        "atm_strike": atm,
        "subscribed_count": len(to_sub),
        "unsubscribed_count": len(to_unsub),
        "total_active": token_manager.get_subscription_count(),
    }

@router.post("/clear", summary="Clear All Subscriptions")
def clear_subscriptions() -> Dict[str, Any]:
    token_manager.clear()
    return {"message": "All active subscriptions cleared", "total_active": 0}

"""
Algorithmic Order Execution & Slicing API Routes (Phase 19).
Supports:
- SEBI / Exchange Freeze Limit Auto-Slicing Plan
- TWAP Execution Engine (Time-Weighted Average Price)
- Iceberg Orders (Dynamic Peak Replenishment)
- Atomic Multi-Leg Basket Execution with Chaser Protection
- Active Algo Sessions & Execution Quality Analytics
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

from backend.app.services.trading.algo_execution import algo_execution_engine

router = APIRouter(prefix="/algo", tags=["Algorithmic Order Slicing & Execution Engine"])


class SlicingPlanRequest(BaseModel):
    underlying: str = "NIFTY"
    symbol: str = "NIFTY24OCT23500CE"
    quantity: int = 5000
    custom_freeze_limit: Optional[int] = None


class StartTWAPRequest(BaseModel):
    underlying: str = "NIFTY"
    symbol: str = "NIFTY24OCT23500CE"
    action: str = "BUY"
    total_quantity: int = 5000
    duration_seconds: int = 300
    num_slices: int = 5
    price_override: Optional[float] = None


class StartIcebergRequest(BaseModel):
    underlying: str = "CRUDEOIL"
    symbol: str = "CRUDEOIL24OCT8900PE"
    action: str = "SELL"
    total_quantity: int = 2000
    peak_size: int = 500
    price_override: Optional[float] = None


class MultiLegBasketRequest(BaseModel):
    strategy_name: str = "IRON_CONDOR"
    underlying: str = "CRUDEOIL"
    legs: List[Dict[str, Any]] = []
    slippage_tolerance_pts: float = 2.0


@router.post("/slice/plan", summary="Generate Exchange-Compliant Freeze Limit Slicing Plan")
def get_freeze_slicing_plan(req: SlicingPlanRequest) -> Dict[str, Any]:
    """
    Computes exact child order sizing avoiding exchange freeze limit rejections.
    """
    try:
        plan = algo_execution_engine.calculate_freeze_slicing_plan(
            underlying=req.underlying,
            symbol=req.symbol,
            quantity=req.quantity,
            custom_freeze_limit=req.custom_freeze_limit
        )
        return {
            "status": "success",
            "data": plan.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/twap/start", summary="Start TWAP Order Algorithm")
def start_twap_execution(req: StartTWAPRequest) -> Dict[str, Any]:
    """
    Initializes a TWAP order algorithm distributed across a duration window.
    """
    try:
        session = algo_execution_engine.start_twap_execution(
            underlying=req.underlying,
            symbol=req.symbol,
            action=req.action,
            total_quantity=req.total_quantity,
            duration_seconds=req.duration_seconds,
            num_slices=req.num_slices,
            price_override=req.price_override
        )
        return {
            "status": "success",
            "data": session.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/iceberg/start", summary="Start Iceberg Order Algorithm")
def start_iceberg_execution(req: StartIcebergRequest) -> Dict[str, Any]:
    """
    Initializes an Iceberg order displaying only a visible peak size.
    """
    try:
        session = algo_execution_engine.start_iceberg_execution(
            underlying=req.underlying,
            symbol=req.symbol,
            action=req.action,
            total_quantity=req.total_quantity,
            peak_size=req.peak_size,
            price_override=req.price_override
        )
        return {
            "status": "success",
            "data": session.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/basket/execute", summary="Execute Multi-Leg Strategy Basket with Chaser Protection")
def execute_multi_leg_basket(req: MultiLegBasketRequest) -> Dict[str, Any]:
    """
    Executes a multi-leg options basket guaranteeing atomic fill protection.
    """
    try:
        res = algo_execution_engine.execute_multi_leg_basket(
            strategy_name=req.strategy_name,
            underlying=req.underlying,
            legs=req.legs,
            slippage_tolerance_pts=req.slippage_tolerance_pts
        )
        return {
            "status": "success",
            "data": res
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sessions", summary="Get All Active and Historical Algo Sessions")
def get_algo_sessions() -> Dict[str, Any]:
    """
    Returns list of all running and completed execution algorithms.
    """
    sessions = [s.to_dict() for s in algo_execution_engine.active_sessions.values()]
    return {
        "status": "success",
        "count": len(sessions),
        "data": sessions
    }


@router.post("/sessions/{session_id}/step", summary="Advance Slice Execution Step")
def step_algo_session(session_id: str) -> Dict[str, Any]:
    """
    Triggers next tranche execution for an active TWAP or Iceberg order.
    """
    session = algo_execution_engine.update_session_progress(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "status": "success",
        "data": session.to_dict()
    }


@router.get("/analytics", summary="Get Execution Quality & Slippage Analytics")
def get_algo_analytics() -> Dict[str, Any]:
    """
    Computes overall execution quality, average slippage in bps, and volume sliced.
    """
    return {
        "status": "success",
        "data": algo_execution_engine.get_execution_analytics()
    }

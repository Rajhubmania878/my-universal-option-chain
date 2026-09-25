"""
FastAPI Route Handlers for Pin-Risk & Institutional Settlement Engine (Phase 24).
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

from backend.app.services.analytics.pin_risk_settlement_engine import (
    pin_risk_settlement_engine,
    PinRiskAnalysis,
    SettlementCostBreakdown,
    PhysicalDeliveryMarginSchedule
)

router = APIRouter(prefix="/pin-risk-settlement", tags=["Pin-Risk & Institutional Settlement Engine"])


class PinRiskScanRequest(BaseModel):
    spot: float = Field(default=8908.0, description="Current spot price")
    strikes: Optional[List[float]] = Field(default=None, description="Strikes to analyze")
    iv: float = Field(default=0.28, description="Annualized IV")
    hours_to_cutoff: float = Field(default=2.5, description="Hours remaining until expiry settlement cutoff")


class TaxCalculationRequest(BaseModel):
    underlying: str = Field(default="CRUDEOIL", description="Underlying symbol")
    strike: float = Field(default=8900.0, description="Option Strike price")
    option_type: str = Field(default="CE", description="CE or PE")
    action: str = Field(default="EXERCISE_ITM", description="EXERCISE_ITM, EXPIRE_OTM, SQUARE_OFF")
    quantity: int = Field(default=100, description="Quantity")
    execution_price: float = Field(default=120.0, description="Option premium price")
    spot_at_expiry: float = Field(default=8950.0, description="Spot price at expiry")


@router.get("/pin-risk", summary="Compute Pin Risk on Expiry Day")
def get_pin_risk(
    spot: float = Query(default=8908.0),
    iv: float = Query(default=0.28),
    hours_to_cutoff: float = Query(default=2.5)
) -> Dict[str, Any]:
    results = pin_risk_settlement_engine.calculate_pin_risk(
        spot=spot,
        iv=iv,
        hours_to_cutoff=hours_to_cutoff
    )
    return {
        "status": "success",
        "spot": spot,
        "hours_to_cutoff": hours_to_cutoff,
        "count": len(results),
        "data": [r.to_dict() for r in results]
    }


@router.post("/pin-risk/scan", summary="Custom Pin Risk Scan")
def scan_custom_pin_risk(req: PinRiskScanRequest = Body(...)) -> Dict[str, Any]:
    results = pin_risk_settlement_engine.calculate_pin_risk(
        spot=req.spot,
        strikes=req.strikes,
        iv=req.iv,
        hours_to_cutoff=req.hours_to_cutoff
    )
    return {
        "status": "success",
        "spot": req.spot,
        "hours_to_cutoff": req.hours_to_cutoff,
        "count": len(results),
        "data": [r.to_dict() for r in results]
    }


@router.post("/tax-breakdown", summary="Compute STT/CTT & Settlement Costs")
def calculate_tax_breakdown(req: TaxCalculationRequest = Body(...)) -> Dict[str, Any]:
    breakdown = pin_risk_settlement_engine.compute_settlement_taxes(
        underlying=req.underlying,
        strike=req.strike,
        option_type=req.option_type,
        action=req.action,
        quantity=req.quantity,
        execution_price=req.execution_price,
        spot_at_expiry=req.spot_at_expiry
    )
    return {
        "status": "success",
        "data": breakdown.to_dict()
    }


@router.get("/margin-schedule", summary="Get 4-Day Physical Delivery Margin Schedule")
def get_delivery_margin_schedule(
    spot: float = Query(default=8908.0),
    lot_size: int = Query(default=100)
) -> Dict[str, Any]:
    schedule = pin_risk_settlement_engine.get_physical_margin_schedule(spot=spot, lot_size=lot_size)
    return {
        "status": "success",
        "spot": spot,
        "lot_size": lot_size,
        "schedule": [s.to_dict() for s in schedule]
    }

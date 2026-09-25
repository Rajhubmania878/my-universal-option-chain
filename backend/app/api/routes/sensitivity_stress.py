"""
Live Option Greeks Sensitivity Stress-Tester & 2D/3D Scenario Matrix Routes (Phase 22).

Endpoints:
- POST /sensitivity-stress/cross-greeks : Computes Higher-Order Greeks (Vanna, Volga, Charm, Color, Speed)
- POST /sensitivity-stress/gamma-scalp : Simulates dynamic delta hedging & Gamma vs Theta PnL
- POST /sensitivity-stress/stress-test : Runs full portfolio stress scenarios (Flash Crash, Geopolitical Spike, IV Crush)
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

from backend.app.services.analytics.sensitivity_stress_engine import sensitivity_stress_engine

router = APIRouter(prefix="/sensitivity-stress", tags=["Greeks Sensitivity & Stress Scenario Engine"])


class CrossGreeksRequest(BaseModel):
    spot: float = 8908.0
    strike: float = 8900.0
    dte_days: float = 25.0
    iv: float = 0.28
    risk_free_rate: float = 0.07
    is_call: bool = True


class GammaScalpRequest(BaseModel):
    underlying: str = "CRUDEOIL"
    strike: float = 8900.0
    option_type: str = "CE"
    entry_spot: float = 8908.0
    entry_iv: float = 0.28
    realized_volatility: float = 0.35
    rebalance_threshold_delta: float = 0.15
    days_simulated: int = 10
    lot_size: int = 100


class PortfolioStressTestRequest(BaseModel):
    underlying_spot: float = 8908.0
    custom_spot_shock_pct: float = -5.0
    custom_iv_shock_pct: float = 10.0
    custom_days_decay: int = 2
    positions: Optional[List[Dict[str, Any]]] = None


@router.post("/cross-greeks", summary="Calculate Higher-Order Cross-Greeks")
def calculate_cross_greeks(req: CrossGreeksRequest) -> Dict[str, Any]:
    """
    Computes Vanna, Volga, Charm, Color, Speed for a specific option contract.
    """
    try:
        t_years = max(0.001, req.dte_days / 365.0)
        higher_order = sensitivity_stress_engine.calculate_higher_order_greeks(
            spot=req.spot,
            strike=req.strike,
            time_to_expiry_years=t_years,
            iv=req.iv,
            risk_free_rate=req.risk_free_rate,
            is_call=req.is_call
        )
        return {
            "status": "success",
            "data": higher_order.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/gamma-scalp", summary="Run Gamma Scalping Rebalancing Simulation")
def simulate_gamma_scalping(req: GammaScalpRequest) -> Dict[str, Any]:
    """
    Simulates discrete dynamic rebalancing and Gamma PnL vs Theta Bleed.
    """
    try:
        sim_result = sensitivity_stress_engine.simulate_gamma_scalp(
            underlying=req.underlying,
            strike=req.strike,
            option_type=req.option_type,
            entry_spot=req.entry_spot,
            entry_iv=req.entry_iv,
            realized_vol=req.realized_volatility,
            rebalance_threshold_delta=req.rebalance_threshold_delta,
            days_simulated=req.days_simulated,
            lot_size=req.lot_size
        )
        return {
            "status": "success",
            "data": sim_result.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/stress-test", summary="Run Portfolio Tail Risk Stress Scenarios")
def run_stress_test(req: PortfolioStressTestRequest) -> Dict[str, Any]:
    """
    Simulates portfolio MTM and Greek shifts under extreme Black Swan and custom shock scenarios.
    """
    try:
        results = sensitivity_stress_engine.run_portfolio_stress_test(
            positions=req.positions or [],
            underlying_spot=req.underlying_spot,
            custom_spot_shock_pct=req.custom_spot_shock_pct,
            custom_iv_shock_pct=req.custom_iv_shock_pct,
            custom_days_decay=req.custom_days_decay
        )
        return {
            "status": "success",
            "count": len(results),
            "data": [r.to_dict() for r in results]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

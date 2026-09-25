from typing import Dict, Any, Optional

try:
    from fastapi import APIRouter, HTTPException
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

from backend.app.services.analytics.greeks_engine import greeks_engine

router = APIRouter(prefix="/greeks", tags=["Black-Scholes Greeks & IV Engine"])

class GreeksCalculationRequest(BaseModel):
    market_price: float = Field(..., description="Observed market price (LTP)")
    spot: float = Field(..., description="Underlying spot or futures price")
    strike: float = Field(..., description="Option strike price")
    expiry: str = Field(..., description="Expiry date string (e.g. 19FEB2026, 26MAR2026)")
    option_type: str = Field(..., description="'CE' or 'PE'")
    exchange: str = Field(default="NFO", description="Exchange: NFO or MCX")
    risk_free_rate: Optional[float] = Field(default=None, description="Risk-free rate (e.g. 0.065 for 6.5%)")

class BSPriceRequest(BaseModel):
    spot: float
    strike: float
    tte_years: float
    volatility_pct: float
    rate: float = 0.065
    option_type: str

@router.post("/calculate", summary="Calculate Implied Volatility & Full Greeks Suite")
def calculate_greeks(req: GreeksCalculationRequest) -> Dict[str, Any]:
    """
    Computes analytical Black-Scholes Greeks:
    - Implied Volatility (IV) via Newton-Raphson & Bisection
    - Delta (0 to 1 for Call, -1 to 0 for Put)
    - Gamma (same for Call & Put)
    - Theta (calendar day time decay)
    - Vega (sensitivity per 1% change in IV)
    - Rho (sensitivity per 1% change in interest rate)
    - Theoretical price, intrinsic value, and time value
    """
    try:
        greeks = greeks_engine.calculate_greeks(
            market_price=req.market_price,
            spot=req.spot,
            strike=req.strike,
            expiry=req.expiry,
            option_type=req.option_type,
            exchange=req.exchange,
            risk_free_rate=req.risk_free_rate
        )
        return {
            "status": "success",
            "greeks": greeks.to_dict()
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@router.post("/bs-price", summary="Black-Scholes Theoretical Pricing Given Volatility")
def calculate_bs_price(req: BSPriceRequest) -> Dict[str, Any]:
    vol = req.volatility_pct / 100.0
    price = greeks_engine.bs_price(
        spot=req.spot,
        strike=req.strike,
        tte=req.tte_years,
        volatility=vol,
        rate=req.rate,
        option_type=req.option_type
    )
    vega = greeks_engine.bs_vega(
        spot=req.spot,
        strike=req.strike,
        tte=req.tte_years,
        volatility=vol,
        rate=req.rate
    )
    return {
        "status": "success",
        "theoretical_price": round(price, 4),
        "annualized_vega": round(vega, 4)
    }

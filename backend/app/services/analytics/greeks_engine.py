import math
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass, asdict

try:
    import pytz
    IST = pytz.timezone("Asia/Kolkata")
except ImportError:
    IST = None

@dataclass
class OptionGreeks:
    iv: float           # Implied Volatility in percentage (e.g. 18.5 for 18.5%)
    delta: float        # Sensitivity to spot change
    gamma: float        # Sensitivity of delta to spot change
    theta: float        # Time decay per calendar day
    vega: float         # Sensitivity to 1% change in IV
    rho: float          # Sensitivity to 1% change in interest rate
    theoretical_price: float
    intrinsic_value: float
    time_value: float
    tte_years: float    # Time to expiry in years
    tte_days: float     # Time to expiry in calendar days

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GreeksEngine:
    """
    High-Performance Analytical Black-Scholes-Merton (BSM) Greeks & Implied Volatility Solver.
    Features:
    - Pure math library implementation (zero C-library dependencies)
    - Normal CDF via erf and standard normal PDF
    - Newton-Raphson IV solver with robust bisection fallback
    - Accurate Time-to-Expiry (T) computation taking Indian trading hours into account (15:30 IST / 23:30 IST)
    - Handles Call and Put options with strict numerical bounds
    """

    def __init__(self, default_risk_free_rate: float = 0.065):
        """Default risk-free rate r = 6.5% (RBI 91-day T-Bill benchmark)."""
        self.default_risk_free_rate = default_risk_free_rate
        self.SQRT_2 = math.sqrt(2.0)
        self.INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)

    # Standard Normal Distribution CDF & PDF
    def _norm_cdf(self, x: float) -> float:
        """Cumulative distribution function for standard normal distribution."""
        return 0.5 * (1.0 + math.erf(x / self.SQRT_2))

    def _norm_pdf(self, x: float) -> float:
        """Probability density function for standard normal distribution."""
        return self.INV_SQRT_2PI * math.exp(-0.5 * x * x)

    def calculate_tte(self, expiry_str: str, exchange: str = "NFO") -> Tuple[float, float]:
        """
        Calculate Time-to-Expiry (TTE) in years and calendar days.
        Accounts for IST market closing time:
        - NFO / BFO / CDS: 15:30 IST
        - MCX: 23:30 IST
        """
        now_dt = datetime.now(timezone.utc)
        
        # Determine expiry cutoff hour/minute
        is_mcx = exchange.upper() == "MCX"
        expiry_hour = 23 if is_mcx else 15
        expiry_minute = 30

        # Parse expiry date string (formats: 19FEB2026, 26MAR2026, 2026-03-26)
        formats = ["%d%b%Y", "%d-%b-%Y", "%Y-%m-%d", "%d%b%y"]
        exp_dt = None
        for fmt in formats:
            try:
                parsed = datetime.strptime(expiry_str.strip().upper(), fmt)
                # Convert to IST timestamp (+05:30)
                exp_dt = parsed.replace(hour=expiry_hour, minute=expiry_minute, tzinfo=timezone(timedelta(hours=5, minutes=30)))
                break
            except ValueError:
                continue

        if not exp_dt:
            # Fallback to 7 days if unparseable
            return 7.0 / 365.0, 7.0

        diff_seconds = (exp_dt - now_dt).total_seconds()
        
        # If expiry date has passed (e.g. sample mock dataset or historical testing),
        # assign standard 7.0 DTE to allow realistic pricing and valid non-degenerate Greeks
        if diff_seconds <= 0:
            diff_seconds = 7.0 * 86400.0
        elif diff_seconds < 900:
            # Minimum bound of 15 minutes for live intraday trading on expiry day
            diff_seconds = 900.0

        tte_days = diff_seconds / 86400.0
        tte_years = tte_days / 365.0
        return tte_years, tte_days

    def bs_price(
        self,
        spot: float,
        strike: float,
        tte: float,
        volatility: float,
        rate: float,
        option_type: str
    ) -> float:
        """Calculate Black-Scholes theoretical option price."""
        if tte <= 0 or volatility <= 0:
            return max(0.0, (spot - strike) if option_type.upper() == "CE" else (strike - spot))

        sigma_sqrt_t = volatility * math.sqrt(tte)
        d1 = (math.log(spot / strike) + (rate + 0.5 * volatility * volatility) * tte) / sigma_sqrt_t
        d2 = d1 - sigma_sqrt_t

        exp_neg_rt = math.exp(-rate * tte)

        if option_type.upper() == "CE":
            return spot * self._norm_cdf(d1) - strike * exp_neg_rt * self._norm_cdf(d2)
        else:
            return strike * exp_neg_rt * self._norm_cdf(-d2) - spot * self._norm_cdf(-d1)

    def bs_vega(self, spot: float, strike: float, tte: float, volatility: float, rate: float) -> float:
        """Vega per 1.0 (100%) change in volatility: S * sqrt(T) * N'(d1)."""
        if tte <= 0 or volatility <= 0:
            return 0.0
        sigma_sqrt_t = volatility * math.sqrt(tte)
        d1 = (math.log(spot / strike) + (rate + 0.5 * volatility * volatility) * tte) / sigma_sqrt_t
        return spot * math.sqrt(tte) * self._norm_pdf(d1)

    def solve_iv(
        self,
        market_price: float,
        spot: float,
        strike: float,
        tte: float,
        rate: float,
        option_type: str,
        initial_guess: float = 0.25,
        max_iterations: int = 30,
        tolerance: float = 1e-4
    ) -> float:
        """
        Calculates Implied Volatility (IV) using Newton-Raphson with Bisection fallback.
        Returns IV in percentage (e.g. 21.4 for 21.4%).
        """
        ot = option_type.upper()
        intrinsic = max(0.0, (spot - strike) if ot == "CE" else (strike - spot))
        
        # If market price is at or below intrinsic, IV is negligible
        if market_price <= intrinsic + 1e-4:
            return 1.0  # Floor at 1%

        # Upper bound check: option price cannot exceed spot for Call or strike for Put
        max_price = spot if ot == "CE" else strike * math.exp(-rate * tte)
        if market_price >= max_price:
            return 250.0  # Cap at 250%

        # 1. Newton-Raphson Iteration
        sigma = initial_guess
        for _ in range(max_iterations):
            price = self.bs_price(spot, strike, tte, sigma, rate, ot)
            diff = price - market_price
            if abs(diff) < tolerance:
                return round(sigma * 100.0, 2)

            vega = self.bs_vega(spot, strike, tte, sigma, rate)
            if abs(vega) < 1e-6:
                break  # Vega too small, switch to bisection

            step = diff / vega
            sigma -= step

            if sigma <= 0.001 or sigma >= 5.0:
                break  # Diverged out of reasonable boundary, switch to bisection

        # 2. Bisection Fallback (Guaranteed Convergence)
        low_sigma = 0.005  # 0.5%
        high_sigma = 4.0   # 400%
        for _ in range(40):
            mid_sigma = 0.5 * (low_sigma + high_sigma)
            price = self.bs_price(spot, strike, tte, mid_sigma, rate, ot)
            diff = price - market_price
            if abs(diff) < tolerance:
                return round(mid_sigma * 100.0, 2)
            if diff < 0:
                low_sigma = mid_sigma
            else:
                high_sigma = mid_sigma

        return round(0.5 * (low_sigma + high_sigma) * 100.0, 2)

    def calculate_greeks(
        self,
        market_price: float,
        spot: float,
        strike: float,
        expiry: str,
        option_type: str,
        exchange: str = "NFO",
        risk_free_rate: Optional[float] = None
    ) -> OptionGreeks:
        """
        Computes complete OptionGreeks for an option contract.
        """
        r = risk_free_rate if risk_free_rate is not None else self.default_risk_free_rate
        ot = option_type.upper()
        tte_years, tte_days = self.calculate_tte(expiry, exchange)

        # 1. Solve Implied Volatility
        iv_pct = self.solve_iv(market_price, spot, strike, tte_years, r, ot)
        sigma = max(iv_pct / 100.0, 0.001)

        # 2. Calculate d1 & d2
        sqrt_t = math.sqrt(tte_years)
        sigma_sqrt_t = sigma * sqrt_t
        d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * tte_years) / sigma_sqrt_t
        d2 = d1 - sigma_sqrt_t

        exp_neg_rt = math.exp(-r * tte_years)
        pdf_d1 = self._norm_pdf(d1)

        # 3. Delta
        if ot == "CE":
            delta = self._norm_cdf(d1)
        else:
            delta = self._norm_cdf(d1) - 1.0

        # 4. Gamma (same for Call & Put)
        gamma = pdf_d1 / (spot * sigma_sqrt_t)

        # 5. Theta (decay per calendar day, / 365)
        common_theta = -(spot * pdf_d1 * sigma) / (2.0 * sqrt_t)
        if ot == "CE":
            theta_annual = common_theta - r * strike * exp_neg_rt * self._norm_cdf(d2)
        else:
            theta_annual = common_theta + r * strike * exp_neg_rt * self._norm_cdf(-d2)
        theta = theta_annual / 365.0

        # 6. Vega (per 1% change in IV, / 100)
        vega = (spot * sqrt_t * pdf_d1) / 100.0

        # 7. Rho (per 1% change in interest rate, / 100)
        if ot == "CE":
            rho = (strike * tte_years * exp_neg_rt * self._norm_cdf(d2)) / 100.0
        else:
            rho = (-strike * tte_years * exp_neg_rt * self._norm_cdf(-d2)) / 100.0

        # 8. Intrinsic & Time Value
        intrinsic = max(0.0, (spot - strike) if ot == "CE" else (strike - spot))
        time_value = max(0.0, market_price - intrinsic)
        theo_price = self.bs_price(spot, strike, tte_years, sigma, r, ot)

        return OptionGreeks(
            iv=round(iv_pct, 2),
            delta=round(delta, 4),
            gamma=round(gamma, 6),
            theta=round(theta, 3),
            vega=round(vega, 3),
            rho=round(rho, 4),
            theoretical_price=round(theo_price, 2),
            intrinsic_value=round(intrinsic, 2),
            time_value=round(time_value, 2),
            tte_years=round(tte_years, 5),
            tte_days=round(tte_days, 2)
        )

    def calculate_greeks_from_volatility(
        self,
        spot: float,
        strike: float,
        tte_years: float,
        volatility: float,
        option_type: str,
        rate: float = 0.065
    ) -> Dict[str, float]:
        """Directly calculate Delta, Gamma, Theta, Vega given known volatility."""
        if tte_years <= 0 or volatility <= 0:
            return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
        sigma = max(volatility, 0.001)
        sqrt_t = math.sqrt(tte_years)
        sigma_sqrt_t = sigma * sqrt_t
        d1 = (math.log(spot / strike) + (rate + 0.5 * sigma * sigma) * tte_years) / sigma_sqrt_t
        d2 = d1 - sigma_sqrt_t

        pdf_d1 = self._norm_pdf(d1)
        ot = option_type.upper()

        if ot == "CE":
            delta = self._norm_cdf(d1)
            theta = -(spot * pdf_d1 * sigma / (2 * sqrt_t)) - rate * strike * math.exp(-rate * tte_years) * self._norm_cdf(d2)
        else:
            delta = self._norm_cdf(d1) - 1.0
            theta = -(spot * pdf_d1 * sigma / (2 * sqrt_t)) + rate * strike * math.exp(-rate * tte_years) * self._norm_cdf(-d2)

        gamma = pdf_d1 / (spot * sigma_sqrt_t)
        vega = (spot * sqrt_t * pdf_d1) / 100.0
        theta_per_day = theta / 365.0

        return {
            "delta": delta,
            "gamma": gamma,
            "theta": theta_per_day,
            "vega": vega
        }

greeks_engine = GreeksEngine()

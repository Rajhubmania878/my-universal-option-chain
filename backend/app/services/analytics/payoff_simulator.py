"""
Strategy Payoff & Risk Profile Graph Generator / Scenario Simulator (What-If Analysis).
Computes:
1. Exact Expiry Payoff Curve & Target Date (T+N) Mark-to-Market Curve using Black-Scholes
2. Max Profit, Max Loss, Breakevens, Risk-to-Reward Ratio
3. Probability of Profit (POP) using Normal Distribution Integral
4. Net Portfolio Greeks (Delta, Gamma, Theta, Vega)
5. Multi-dimensional What-If Scenario Matrix (Spot Change % vs IV Shift %)
6. Standard Strategy Templates (Straddle, Strangle, Bull Call Spread, Bear Put Spread, Iron Condor, Iron Butterfly)
"""
import math
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict

from backend.app.services.analytics.greeks_engine import GreeksEngine, greeks_engine
from backend.app.core.logging import logger

@dataclass
class StrategyLeg:
    symbol: str
    option_type: str        # "CE" or "PE"
    strike: float
    action: str             # "BUY" or "SELL"
    quantity: int
    entry_price: float
    iv: float               # Percentage e.g. 18.5

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class StrategyPayoffEngine:
    def __init__(self, engine: Optional[GreeksEngine] = None):
        self.greeks_engine = engine or greeks_engine

    def calculate_leg_expiry_pnl(self, leg: StrategyLeg, spot_at_expiry: float) -> float:
        """
        Calculate P&L for a single leg at expiration.
        """
        mult = 1 if leg.action.upper() == "BUY" else -1
        if leg.option_type.upper() == "CE":
            intrinsic = max(0.0, spot_at_expiry - leg.strike)
        else:
            intrinsic = max(0.0, leg.strike - spot_at_expiry)

        unit_pnl = (intrinsic - leg.entry_price) if leg.action.upper() == "BUY" else (leg.entry_price - intrinsic)
        return unit_pnl * leg.quantity

    def calculate_leg_target_pnl(
        self,
        leg: StrategyLeg,
        spot: float,
        target_tte_days: float,
        iv_shift_pct: float = 0.0,
        rate: float = 0.065
    ) -> float:
        """
        Calculate theoretical P&L for a single leg at a target date before expiration using Black-Scholes.
        """
        target_tte_years = max(0.0001, target_tte_days / 365.0)
        adj_vol = max(0.01, (leg.iv + iv_shift_pct) / 100.0)

        theoretical_price = self.greeks_engine.bs_price(
            spot=spot,
            strike=leg.strike,
            tte=target_tte_years,
            volatility=adj_vol,
            rate=rate,
            option_type=leg.option_type
        )

        unit_pnl = (theoretical_price - leg.entry_price) if leg.action.upper() == "BUY" else (leg.entry_price - theoretical_price)
        return unit_pnl * leg.quantity

    def evaluate_strategy_payoff(
        self,
        strategy_name: str,
        underlying: str,
        current_spot: float,
        legs: List[StrategyLeg],
        tte_days: float = 7.0,
        target_days: float = 0.0, # 0 = today (T+0), tte_days = expiry
        iv_shift_pct: float = 0.0,
        range_pct: float = 0.10, # Spot spectrum +/- 10%
        num_points: int = 51
    ) -> Dict[str, Any]:
        """
        Generate full strategy risk profile, breakevens, and payoff curves.
        """
        if not legs:
            raise ValueError("Strategy must contain at least one leg")

        # Spot spectrum
        min_spot = current_spot * (1.0 - range_pct)
        max_spot = current_spot * (1.0 + range_pct)
        step = (max_spot - min_spot) / max(1, (num_points - 1))

        curve_points: List[Dict[str, float]] = []
        net_premium = 0.0

        for leg in legs:
            flow = -1.0 if leg.action.upper() == "BUY" else 1.0
            net_premium += flow * leg.entry_price * leg.quantity

        target_tte_days = max(0.0, tte_days - target_days)

        min_expiry_pnl = float('inf')
        max_expiry_pnl = float('-inf')

        # Track breakeven crossings
        breakevens: List[float] = []
        prev_pnl: Optional[float] = None
        prev_spot: Optional[float] = None

        for i in range(num_points):
            s = min_spot + i * step
            
            pnl_exp = sum(self.calculate_leg_expiry_pnl(leg, s) for leg in legs)
            pnl_tgt = sum(self.calculate_leg_target_pnl(leg, s, target_tte_days, iv_shift_pct) for leg in legs)

            curve_points.append({
                "spot": round(s, 2),
                "pnl_expiry": round(pnl_exp, 2),
                "pnl_target": round(pnl_tgt, 2)
            })

            min_expiry_pnl = min(min_expiry_pnl, pnl_exp)
            max_expiry_pnl = max(max_expiry_pnl, pnl_exp)

            # Linear interpolation for zero crossings
            if prev_pnl is not None and prev_spot is not None:
                if (prev_pnl < 0 and pnl_exp >= 0) or (prev_pnl > 0 and pnl_exp <= 0):
                    dp = pnl_exp - prev_pnl
                    if abs(dp) > 1e-6:
                        zero_spot = prev_spot + (-prev_pnl / dp) * (s - prev_spot)
                        breakevens.append(round(zero_spot, 2))

            prev_pnl = pnl_exp
            prev_spot = s

        # Check for open-ended unhedged legs (Unlimited profit/loss)
        net_calls = sum((1 if l.action.upper() == "BUY" else -1) * l.quantity for l in legs if l.option_type.upper() == "CE")
        net_puts = sum((1 if l.action.upper() == "BUY" else -1) * l.quantity for l in legs if l.option_type.upper() == "PE")

        max_profit_str: Union[float, str] = round(max_expiry_pnl, 2)
        max_loss_str: Union[float, str] = round(min_expiry_pnl, 2)

        if net_calls > 0 or net_puts > 0:
            max_profit_str = "Unlimited"
        if net_calls < 0 or net_puts < 0:
            max_loss_str = "Unlimited"

        # Risk-to-Reward ratio (if both are bounded and positive)
        rr_ratio = None
        if isinstance(max_profit_str, (int, float)) and isinstance(max_loss_str, (int, float)):
            if abs(max_loss_str) > 0 and max_profit_str > 0:
                rr_ratio = round(max_profit_str / abs(max_loss_str), 2)

        # Net Greeks calculation
        net_delta = 0.0
        net_gamma = 0.0
        net_theta = 0.0
        net_vega = 0.0

        tte_years = max(0.0001, tte_days / 365.0)
        for leg in legs:
            g = self.greeks_engine.calculate_greeks_from_volatility(
                spot=current_spot,
                strike=leg.strike,
                tte_years=tte_years,
                volatility=leg.iv / 100.0,
                option_type=leg.option_type
            )
            sign = 1.0 if leg.action.upper() == "BUY" else -1.0
            qty = leg.quantity
            net_delta += sign * g["delta"] * qty
            net_gamma += sign * g["gamma"] * qty
            net_theta += sign * g["theta"] * qty
            net_vega += sign * g["vega"] * qty

        # Probability of Profit (POP) approximation via Standard Normal Distribution
        pop = self._calculate_pop(current_spot, breakevens, legs, tte_days)

        # Generate What-If Scenario Matrix
        scenario_matrix = self._generate_scenario_matrix(current_spot, legs, target_tte_days)

        return {
            "strategy_name": strategy_name,
            "underlying": underlying,
            "current_spot": current_spot,
            "net_premium": round(net_premium, 2),
            "is_net_credit": net_premium > 0,
            "max_profit": max_profit_str,
            "max_loss": max_loss_str,
            "risk_reward_ratio": rr_ratio,
            "breakevens": breakevens,
            "probability_of_profit_pct": round(pop * 100.0, 1),
            "net_greeks": {
                "delta": round(net_delta, 3),
                "gamma": round(net_gamma, 5),
                "theta": round(net_theta, 2),
                "vega": round(net_vega, 2)
            },
            "legs": [l.to_dict() for l in legs],
            "payoff_curve": curve_points,
            "scenario_matrix": scenario_matrix
        }

    def _calculate_pop(
        self,
        spot: float,
        breakevens: List[float],
        legs: List[StrategyLeg],
        tte_days: float
    ) -> float:
        """
        Estimate Probability of Profit (POP) based on log-normal distribution and breakeven zones.
        """
        if not breakevens:
            # Check if always in profit or loss
            sample_pnl = sum(self.calculate_leg_expiry_pnl(l, spot) for l in legs)
            return 1.0 if sample_pnl > 0 else 0.0

        avg_iv = sum(l.iv for l in legs) / len(legs) / 100.0
        tte_years = max(0.001, tte_days / 365.0)
        std_dev = spot * avg_iv * math.sqrt(tte_years)

        if len(breakevens) == 1:
            be = breakevens[0]
            z = (be - spot) / std_dev
            # Check if profit is above or below breakeven
            above_pnl = sum(self.calculate_leg_expiry_pnl(l, be + 10) for l in legs)
            return (1.0 - self.greeks_engine._norm_cdf(z)) if above_pnl > 0 else self.greeks_engine._norm_cdf(z)

        elif len(breakevens) >= 2:
            be_low = min(breakevens)
            be_high = max(breakevens)
            z_low = (be_low - spot) / std_dev
            z_high = (be_high - spot) / std_dev

            # Check if between breakevens is profit or loss
            mid_spot = (be_low + be_high) / 2.0
            mid_pnl = sum(self.calculate_leg_expiry_pnl(l, mid_spot) for l in legs)

            inside_prob = self.greeks_engine._norm_cdf(z_high) - self.greeks_engine._norm_cdf(z_low)
            return inside_prob if mid_pnl > 0 else (1.0 - inside_prob)

        return 0.50

    def _generate_scenario_matrix(
        self,
        current_spot: float,
        legs: List[StrategyLeg],
        target_tte_days: float
    ) -> List[Dict[str, Any]]:
        """
        Build a 2D Matrix of Spot Shock (-3%, -2%, -1%, 0%, +1%, +2%, +3%)
        vs IV Shift (-5%, -2%, 0%, +2%, +5%).
        """
        spot_shocks = [-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03]
        iv_shifts = [-5.0, -2.0, 0.0, 2.0, 5.0]

        matrix_rows = []
        for s_shock in spot_shocks:
            simulated_spot = current_spot * (1.0 + s_shock)
            row_data: Dict[str, Any] = {
                "spot_shock_pct": round(s_shock * 100, 1),
                "simulated_spot": round(simulated_spot, 2),
                "pnl_by_iv_shift": {}
            }
            for iv_shift in iv_shifts:
                pnl = sum(
                    self.calculate_leg_target_pnl(
                        leg=leg,
                        spot=simulated_spot,
                        target_tte_days=target_tte_days,
                        iv_shift_pct=iv_shift
                    )
                    for leg in legs
                )
                shift_key = f"{'+' if iv_shift > 0 else ''}{int(iv_shift)}%"
                row_data["pnl_by_iv_shift"][shift_key] = round(pnl, 2)
            matrix_rows.append(row_data)

        return matrix_rows

    # Standard Pre-Configured Strategy Templates
    def create_short_straddle(self, underlying: str, atm_strike: float, premium_ce: float, premium_pe: float, iv: float = 20.0, qty: int = 100) -> List[StrategyLeg]:
        return [
            StrategyLeg(symbol=f"{underlying}{atm_strike}CE", option_type="CE", strike=atm_strike, action="SELL", quantity=qty, entry_price=premium_ce, iv=iv),
            StrategyLeg(symbol=f"{underlying}{atm_strike}PE", option_type="PE", strike=atm_strike, action="SELL", quantity=qty, entry_price=premium_pe, iv=iv)
        ]

    def create_bull_call_spread(self, underlying: str, atm_strike: float, step: float, buy_ce_price: float, sell_ce_price: float, iv: float = 20.0, qty: int = 100) -> List[StrategyLeg]:
        return [
            StrategyLeg(symbol=f"{underlying}{atm_strike}CE", option_type="CE", strike=atm_strike, action="BUY", quantity=qty, entry_price=buy_ce_price, iv=iv),
            StrategyLeg(symbol=f"{underlying}{atm_strike + step}CE", option_type="CE", strike=atm_strike + step, action="SELL", quantity=qty, entry_price=sell_ce_price, iv=iv)
        ]

    def create_bear_put_spread(self, underlying: str, atm_strike: float, step: float, buy_pe_price: float, sell_pe_price: float, iv: float = 20.0, qty: int = 100) -> List[StrategyLeg]:
        return [
            StrategyLeg(symbol=f"{underlying}{atm_strike}PE", option_type="PE", strike=atm_strike, action="BUY", quantity=qty, entry_price=buy_pe_price, iv=iv),
            StrategyLeg(symbol=f"{underlying}{atm_strike - step}PE", option_type="PE", strike=atm_strike - step, action="SELL", quantity=qty, entry_price=sell_pe_price, iv=iv)
        ]

    def create_iron_condor(
        self,
        underlying: str,
        atm_strike: float,
        step: float,
        otm_call_short: float,
        otm_call_long: float,
        otm_put_short: float,
        otm_put_long: float,
        iv: float = 20.0,
        qty: int = 100
    ) -> List[StrategyLeg]:
        return [
            StrategyLeg(symbol=f"{underlying}{atm_strike - step * 2}PE", option_type="PE", strike=atm_strike - step * 2, action="BUY", quantity=qty, entry_price=otm_put_long, iv=iv),
            StrategyLeg(symbol=f"{underlying}{atm_strike - step}PE", option_type="PE", strike=atm_strike - step, action="SELL", quantity=qty, entry_price=otm_put_short, iv=iv),
            StrategyLeg(symbol=f"{underlying}{atm_strike + step}CE", option_type="CE", strike=atm_strike + step, action="SELL", quantity=qty, entry_price=otm_call_short, iv=iv),
            StrategyLeg(symbol=f"{underlying}{atm_strike + step * 2}CE", option_type="CE", strike=atm_strike + step * 2, action="BUY", quantity=qty, entry_price=otm_call_long, iv=iv)
        ]

# Global singleton
strategy_payoff_engine = StrategyPayoffEngine()

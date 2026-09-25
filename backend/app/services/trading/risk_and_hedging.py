"""
Portfolio Risk & Hedging Engine (Phase 18).
Aggregates Net Portfolio Greeks (Delta, Gamma, Theta, Vega, Rho),
computes 1-day Parametric Value-at-Risk (VaR 99%),
calculates dynamic Delta/Vega hedging quantities (Futures or Options),
and conducts institutional stress-testing shock scenarios.
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
import math

from backend.app.core.logging import logger
from backend.app.services.analytics.greeks_engine import greeks_engine
from backend.app.services.market.quote_engine import quote_engine
from backend.app.services.angel.instrument_master import instrument_master


@dataclass
class PortfolioGreeks:
    net_delta: float
    net_delta_cash: float
    net_gamma: float
    gamma_cash_1pct: float
    net_theta_daily: float
    net_vega: float
    net_rho: float
    var_99_1day: float
    margin_utilization_pct: float
    estimated_margin_required: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HedgeRecommendation:
    hedge_type: str            # "DELTA" or "VEGA"
    target_value: float
    current_value: float
    discrepancy: float
    recommended_action: str    # "BUY" or "SELL" or "BALANCED"
    recommended_instrument: str
    recommended_symbol: str
    recommended_qty: int
    recommended_lots: int
    projected_new_value: float
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StressScenarioResult:
    scenario_id: str
    scenario_name: str
    spot_shock_pct: float
    spot_shock_pts: float
    iv_shock_pct: float
    time_horizon_days: float
    projected_pnl: float
    projected_pnl_pct_capital: float
    risk_level: str             # "LOW", "MODERATE", "SEVERE", "CRITICAL"
    margin_call_risk: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PortfolioRiskAnalysis:
    underlying: str
    spot_price: float
    total_positions_count: int
    total_open_qty: int
    greeks: PortfolioGreeks
    hedging_recommendations: List[HedgeRecommendation]
    stress_scenarios: List[StressScenarioResult]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "underlying": self.underlying,
            "spot_price": self.spot_price,
            "total_positions_count": self.total_positions_count,
            "total_open_qty": self.total_open_qty,
            "greeks": self.greeks.to_dict(),
            "hedging_recommendations": [h.to_dict() for h in self.hedging_recommendations],
            "stress_scenarios": [s.to_dict() for s in self.stress_scenarios]
        }


class PortfolioRiskAndHedgingEngine:
    def __init__(self):
        logger.info("Initialized PortfolioRiskAndHedgingEngine (Phase 18)")

    def analyze_portfolio_risk(
        self,
        underlying: str,
        positions: List[Dict[str, Any]],
        capital: float = 1000000.0,
        spot_override: Optional[float] = None
    ) -> PortfolioRiskAnalysis:
        """
        Computes the complete portfolio risk profile, Net Greeks,
        hedge suggestions, and stress-test shock scenarios.
        """
        underlying = underlying.upper()

        # Determine spot price
        spot_price = spot_override
        if spot_price is None:
            underlying_quote = quote_engine.get_quote(underlying)
            if underlying_quote and underlying_quote.ltp > 0:
                spot_price = underlying_quote.ltp
            else:
                spot_price = 8908.0 if underlying == "CRUDEOIL" else 23500.0

        # Filter positions matching this underlying
        relevant_positions = [
            p for p in positions
            if p.get("underlying", "").upper() == underlying or underlying in p.get("symbol", "").upper()
        ]

        # Extract lot size
        lot_size = 100 if underlying == "CRUDEOIL" else 50

        # Default IV estimate
        base_iv = 0.22 if underlying == "CRUDEOIL" else 0.14

        net_delta = 0.0
        net_gamma = 0.0
        net_theta = 0.0
        net_vega = 0.0
        net_rho = 0.0
        total_open_qty = 0
        total_short_margin = 0.0
        total_long_premium = 0.0

        for pos in relevant_positions:
            qty = pos.get("netQty", pos.get("quantity", 0))
            if qty == 0:
                continue

            total_open_qty += abs(qty)
            symbol = pos.get("symbol", "")
            ltp = pos.get("ltp", pos.get("price", 100.0))

            # Deduce if Call, Put, or Future
            is_call = "CE" in symbol.upper()
            is_put = "PE" in symbol.upper()
            is_future = not is_call and not is_put

            if is_future:
                # 1 Future contract has Delta = 1.0 per unit
                delta_per_unit = 1.0
                gamma_per_unit = 0.0
                theta_per_unit = 0.0
                vega_per_unit = 0.0
                rho_per_unit = 0.0
            else:
                # Extract strike
                strike = self._extract_strike_from_symbol(symbol, spot_price)
                opt_type = "CE" if is_call else "PE"

                # Calculate Black-76 Greeks
                exchange = "MCX" if underlying == "CRUDEOIL" else "NFO"
                greeks = greeks_engine.calculate_greeks(
                    market_price=ltp,
                    spot=spot_price,
                    strike=strike,
                    expiry="24OCT2024",
                    option_type=opt_type,
                    exchange=exchange
                )
                delta_per_unit = greeks.delta
                gamma_per_unit = greeks.gamma
                theta_per_unit = greeks.theta
                vega_per_unit = greeks.vega
                rho_per_unit = greeks.rho

            # Aggregate Greeks multiplied by signed quantity
            net_delta += delta_per_unit * qty
            net_gamma += gamma_per_unit * qty
            net_theta += theta_per_unit * qty
            net_vega += vega_per_unit * qty
            net_rho += rho_per_unit * qty

            # Margin estimation: approx 15% SPAN per short contract
            if qty < 0:
                total_short_margin += abs(qty) * spot_price * 0.15
            else:
                total_long_premium += qty * ltp

        total_margin_required = total_short_margin + total_long_premium
        margin_util_pct = min(100.0, round((total_margin_required / max(1.0, capital)) * 100, 2))

        # Cash Delta Exposure = Net Delta * Spot Price
        net_delta_cash = net_delta * spot_price

        # Gamma Cash per 1% move = 0.5 * Gamma * (0.01 * Spot)^2
        gamma_cash_1pct = 0.5 * net_gamma * ((0.01 * spot_price) ** 2)

        # Parametric Value-at-Risk (VaR 99% 1-day)
        # 2.33 std dev * Daily Volatility * Delta Cash
        daily_vol = base_iv / math.sqrt(252)
        var_99_1day = round(2.326 * abs(net_delta_cash) * daily_vol, 2)

        portfolio_greeks = PortfolioGreeks(
            net_delta=round(net_delta, 3),
            net_delta_cash=round(net_delta_cash, 2),
            net_gamma=round(net_gamma, 5),
            gamma_cash_1pct=round(gamma_cash_1pct, 2),
            net_theta_daily=round(net_theta, 2),
            net_vega=round(net_vega, 2),
            net_rho=round(net_rho, 2),
            var_99_1day=var_99_1day,
            margin_utilization_pct=margin_util_pct,
            estimated_margin_required=round(total_margin_required, 2)
        )

        # Generate Hedging Recommendations
        hedging_recs = self._calculate_hedges(
            underlying=underlying,
            net_delta=net_delta,
            net_vega=net_vega,
            spot_price=spot_price,
            lot_size=lot_size
        )

        # Run Stress Testing Scenarios
        stress_results = self._run_stress_scenarios(
            spot_price=spot_price,
            net_delta=net_delta,
            net_gamma=net_gamma,
            net_theta=net_theta,
            net_vega=net_vega,
            capital=capital
        )

        return PortfolioRiskAnalysis(
            underlying=underlying,
            spot_price=spot_price,
            total_positions_count=len(relevant_positions),
            total_open_qty=total_open_qty,
            greeks=portfolio_greeks,
            hedging_recommendations=hedging_recs,
            stress_scenarios=stress_results
        )

    def _calculate_hedges(
        self,
        underlying: str,
        net_delta: float,
        net_vega: float,
        spot_price: float,
        lot_size: int
    ) -> List[HedgeRecommendation]:
        """
        Determines the exact contracts and quantities required to neutralize Delta and Vega.
        """
        recommendations = []

        # Delta Hedge via Futures
        # If Net Delta > 0, we are net long -> need to SELL Futures
        # If Net Delta < 0, we are net short -> need to BUY Futures
        delta_tol = 0.5 * lot_size
        if abs(net_delta) > delta_tol:
            action = "SELL" if net_delta > 0 else "BUY"
            raw_qty = abs(net_delta)
            lots = max(1, round(raw_qty / lot_size))
            recommended_qty = lots * lot_size

            projected_delta = net_delta - (recommended_qty if action == "SELL" else -recommended_qty)

            recommendations.append(HedgeRecommendation(
                hedge_type="DELTA_FUTURES",
                target_value=0.0,
                current_value=round(net_delta, 2),
                discrepancy=round(net_delta, 2),
                recommended_action=action,
                recommended_instrument="FUTURES",
                recommended_symbol=f"{underlying}-FUT",
                recommended_qty=recommended_qty,
                recommended_lots=lots,
                projected_new_value=round(projected_delta, 2),
                notes=f"Neutralize directional exposure by {action}ing {lots} lot(s) ({recommended_qty} units) of {underlying} Futures."
            ))
        else:
            recommendations.append(HedgeRecommendation(
                hedge_type="DELTA_FUTURES",
                target_value=0.0,
                current_value=round(net_delta, 2),
                discrepancy=round(net_delta, 2),
                recommended_action="BALANCED",
                recommended_instrument="FUTURES",
                recommended_symbol=f"{underlying}-FUT",
                recommended_qty=0,
                recommended_lots=0,
                projected_new_value=round(net_delta, 2),
                notes="Portfolio Delta is within balanced threshold (±0.5 lot)."
            ))

        # Delta Hedge via ATM Options
        atm_strike = round(spot_price / 100) * 100 if underlying == "CRUDEOIL" else round(spot_price / 50) * 50
        if abs(net_delta) > delta_tol:
            # Option delta is ~0.50 for ATM
            # To neutralize positive delta, we can BUY ATM PE (Delta ~ -0.5) or SELL ATM CE (Delta ~ +0.5)
            if net_delta > 0:
                opt_action = "BUY"
                opt_type = "PE"
                needed_units = round(abs(net_delta) / 0.5)
            else:
                opt_action = "BUY"
                opt_type = "CE"
                needed_units = round(abs(net_delta) / 0.5)

            lots = max(1, round(needed_units / lot_size))
            opt_qty = lots * lot_size
            projected_delta = net_delta + ((-0.5 if opt_type == "PE" else 0.5) * opt_qty * (1 if opt_action == "BUY" else -1))

            recommendations.append(HedgeRecommendation(
                hedge_type="DELTA_OPTIONS",
                target_value=0.0,
                current_value=round(net_delta, 2),
                discrepancy=round(net_delta, 2),
                recommended_action=opt_action,
                recommended_instrument=f"ATM {opt_type}",
                recommended_symbol=f"{underlying}{int(atm_strike)}{opt_type}",
                recommended_qty=opt_qty,
                recommended_lots=lots,
                projected_new_value=round(projected_delta, 2),
                notes=f"{opt_action} {lots} lot(s) ({opt_qty} qty) of {int(atm_strike)} {opt_type} to hedge directional delta without futures margin risk."
            ))

        return recommendations

    def _run_stress_scenarios(
        self,
        spot_price: float,
        net_delta: float,
        net_gamma: float,
        net_theta: float,
        net_vega: float,
        capital: float
    ) -> List[StressScenarioResult]:
        """
        Computes Taylor expansion second-order P&L shocks across macro market conditions.
        """
        scenarios = [
            {
                "id": "BULL_RALLY",
                "name": "Bull Surge (+3% Spot, -2% IV)",
                "spot_shock_pct": 3.0,
                "iv_shock_pct": -2.0,
                "days": 1.0
            },
            {
                "id": "BEAR_CORRECTION",
                "name": "Bear Dip (-3% Spot, +4% IV)",
                "spot_shock_pct": -3.0,
                "iv_shock_pct": 4.0,
                "days": 1.0
            },
            {
                "id": "FLASH_CRASH",
                "name": "Flash Crash (-7% Spot, +15% IV)",
                "spot_shock_pct": -7.0,
                "iv_shock_pct": 15.0,
                "days": 1.0
            },
            {
                "id": "BLACK_SWAN",
                "name": "Black Swan Collapse (-12% Spot, +30% IV)",
                "spot_shock_pct": -12.0,
                "iv_shock_pct": 30.0,
                "days": 1.0
            },
            {
                "id": "VOL_EXPLOSION",
                "name": "Pre-Event Vol Spike (0% Spot, +10% IV)",
                "spot_shock_pct": 0.0,
                "iv_shock_pct": 10.0,
                "days": 0.5
            },
            {
                "id": "VOL_CRUSH",
                "name": "Post-Expiry Vol Crush (0% Spot, -15% IV)",
                "spot_shock_pct": 0.0,
                "iv_shock_pct": -15.0,
                "days": 1.0
            }
        ]

        results = []
        for sc in scenarios:
            spot_shock_pts = (sc["spot_shock_pct"] / 100.0) * spot_price
            iv_shock_pts = sc["iv_shock_pct"]  # in vol points
            days = sc["days"]

            # Second-order Taylor expansion:
            # dP = Delta * dS + 0.5 * Gamma * dS^2 + Vega * dIV + Theta * dt
            delta_pnl = net_delta * spot_shock_pts
            gamma_pnl = 0.5 * net_gamma * (spot_shock_pts ** 2)
            vega_pnl = net_vega * iv_shock_pts
            theta_pnl = net_theta * days

            total_projected_pnl = round(delta_pnl + gamma_pnl + vega_pnl + theta_pnl, 2)
            pnl_pct_capital = round((total_projected_pnl / max(1.0, capital)) * 100, 2)

            # Classify risk level
            if pnl_pct_capital < -25.0:
                risk_level = "CRITICAL"
                margin_call = True
            elif pnl_pct_capital < -10.0:
                risk_level = "SEVERE"
                margin_call = True
            elif pnl_pct_capital < -4.0:
                risk_level = "MODERATE"
                margin_call = False
            else:
                risk_level = "LOW"
                margin_call = False

            results.append(StressScenarioResult(
                scenario_id=sc["id"],
                scenario_name=sc["name"],
                spot_shock_pct=sc["spot_shock_pct"],
                spot_shock_pts=round(spot_shock_pts, 2),
                iv_shock_pct=sc["iv_shock_pct"],
                time_horizon_days=days,
                projected_pnl=total_projected_pnl,
                projected_pnl_pct_capital=pnl_pct_capital,
                risk_level=risk_level,
                margin_call_risk=margin_call
            ))

        return results

    def _extract_strike_from_symbol(self, symbol: str, fallback_spot: float) -> float:
        """
        Extract numeric strike price from derivative symbol, e.g. CRUDEOIL24OCT8900CE -> 8900.0.
        """
        import re
        match = re.search(r'(\d{4,6})(?:CE|PE)?$', symbol)
        if match:
            try:
                return float(match.group(1))
            except Exception:
                pass
        return fallback_spot


# Global Singleton Instance
risk_hedging_engine = PortfolioRiskAndHedgingEngine()

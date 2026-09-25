import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field

from backend.app.services.angel.instrument_master import instrument_master
from backend.app.services.market.quote_engine import quote_engine
from backend.app.services.market.token_manager import token_manager
from backend.app.services.analytics.greeks_engine import greeks_engine, OptionGreeks
from backend.app.services.analytics.option_chain_builder import option_chain_builder, OptionChainMatrix

@dataclass
class CombinedGreeks:
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StraddleDetails:
    underlying: str
    expiry: str
    exchange: str
    spot_price: float
    strike: float
    call_ltp: float
    put_ltp: float
    straddle_premium: float
    lot_size: int
    straddle_lot_cost: float
    lower_breakeven: float
    upper_breakeven: float
    implied_move_pct: float
    call_oi: int
    put_oi: int
    total_oi: int
    call_volume: int
    put_volume: int
    combined_greeks: CombinedGreeks
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "combined_greeks": self.combined_greeks.to_dict()
        }


@dataclass
class StrangleDetails:
    underlying: str
    expiry: str
    exchange: str
    spot_price: float
    call_strike: float
    put_strike: float
    strike_width: float
    call_ltp: float
    put_ltp: float
    strangle_premium: float
    lot_size: int
    strangle_lot_cost: float
    lower_breakeven: float
    upper_breakeven: float
    implied_move_pct: float
    total_oi: int
    combined_greeks: CombinedGreeks
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "combined_greeks": self.combined_greeks.to_dict()
        }


@dataclass
class MultiStrikeRow:
    strike: float
    is_atm: bool
    call_ltp: float
    put_ltp: float
    straddle_premium: float
    call_oi: int
    put_oi: int
    total_oi: int
    pcr: float
    net_delta: float
    net_theta: float
    implied_move_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MultiStrikeAnalysis:
    underlying: str
    expiry: str
    spot_price: float
    atm_strike: float
    lot_size: int
    rows: List[MultiStrikeRow]
    cheapest_straddle_strike: float
    max_oi_strike: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "underlying": self.underlying,
            "expiry": self.expiry,
            "spot_price": self.spot_price,
            "atm_strike": self.atm_strike,
            "lot_size": self.lot_size,
            "cheapest_straddle_strike": self.cheapest_straddle_strike,
            "max_oi_strike": self.max_oi_strike,
            "rows": [r.to_dict() for r in self.rows]
        }


class StraddleEngine:
    """
    Straddle, Strangle, and Multi-Strike Analytics Engine:
    - Calculates ATM Straddle combined premiums, upper/lower breakevens, and implied move %
    - Strangle strategies across custom strike offsets (OTM 1, OTM 2, OTM 3)
    - Combined Portfolio Greeks (Net Delta, Net Gamma, Net Theta, Net Vega)
    - Multi-strike comparison matrix around ATM
    """

    def calculate_atm_straddle(
        self,
        underlying: str,
        expiry: Optional[str] = None,
        exchange: Optional[str] = None
    ) -> StraddleDetails:
        """Computes ATM straddle metrics, breakevens, and combined Greeks."""
        matrix = option_chain_builder.build(underlying, expiry=expiry, strike_window=2, exchange=exchange)
        summary = matrix.summary

        # Find ATM row
        atm_row = next((r for r in matrix.rows if r.is_atm), None)
        if not atm_row and matrix.rows:
            atm_row = min(matrix.rows, key=lambda r: abs(r.strike - summary.atm_strike))

        if not atm_row:
            raise ValueError(f"No strikes found for {underlying}")

        call_ltp = atm_row.call.ltp if atm_row.call else 0.0
        put_ltp = atm_row.put.ltp if atm_row.put else 0.0
        straddle_prem = round(call_ltp + put_ltp, 2)
        lot_size = summary.lot_size
        lot_cost = round(straddle_prem * lot_size, 2)

        lower_be = round(atm_row.strike - straddle_prem, 2)
        upper_be = round(atm_row.strike + straddle_prem, 2)
        implied_move = round((straddle_prem / summary.spot_price) * 100.0, 2) if summary.spot_price > 0 else 0.0

        c_oi = atm_row.call.open_interest if atm_row.call else 0
        p_oi = atm_row.put.open_interest if atm_row.put else 0
        c_vol = atm_row.call.volume if atm_row.call else 0
        p_vol = atm_row.put.volume if atm_row.put else 0

        # Aggregate Greeks
        c_delta = atm_row.call.delta if (atm_row.call and atm_row.call.delta is not None) else 0.5
        p_delta = atm_row.put.delta if (atm_row.put and atm_row.put.delta is not None) else -0.5
        c_gamma = atm_row.call.gamma if (atm_row.call and atm_row.call.gamma is not None) else 0.001
        p_gamma = atm_row.put.gamma if (atm_row.put and atm_row.put.gamma is not None) else 0.001
        c_theta = atm_row.call.theta if (atm_row.call and atm_row.call.theta is not None) else -10.0
        p_theta = atm_row.put.theta if (atm_row.put and atm_row.put.theta is not None) else -10.0
        c_vega = atm_row.call.vega if (atm_row.call and atm_row.call.vega is not None) else 15.0
        p_vega = atm_row.put.vega if (atm_row.put and atm_row.put.vega is not None) else 15.0

        combined_greeks = CombinedGreeks(
            net_delta=round(c_delta + p_delta, 4),
            net_gamma=round(c_gamma + p_gamma, 6),
            net_theta=round(c_theta + p_theta, 3),
            net_vega=round(c_vega + p_vega, 3)
        )

        return StraddleDetails(
            underlying=summary.underlying,
            expiry=summary.expiry,
            exchange=summary.exchange,
            spot_price=summary.spot_price,
            strike=atm_row.strike,
            call_ltp=call_ltp,
            put_ltp=put_ltp,
            straddle_premium=straddle_prem,
            lot_size=lot_size,
            straddle_lot_cost=lot_cost,
            lower_breakeven=lower_be,
            upper_breakeven=upper_be,
            implied_move_pct=implied_move,
            call_oi=c_oi,
            put_oi=p_oi,
            total_oi=c_oi + p_oi,
            call_volume=c_vol,
            put_volume=p_vol,
            combined_greeks=combined_greeks
        )

    def calculate_strangle(
        self,
        underlying: str,
        expiry: Optional[str] = None,
        otm_offset: int = 1,
        exchange: Optional[str] = None
    ) -> StrangleDetails:
        """
        Computes Strangle strategy by selecting OTM Call and OTM Put
        otm_offset = 1 -> 1 strike OTM Call & 1 strike OTM Put
        """
        offset = max(1, otm_offset)
        matrix = option_chain_builder.build(underlying, expiry=expiry, strike_window=offset + 3, exchange=exchange)
        summary = matrix.summary

        # Locate ATM index
        atm_idx = next((i for i, r in enumerate(matrix.rows) if r.is_atm), None)
        if atm_idx is None:
            atm_idx = len(matrix.rows) // 2

        put_idx = max(0, atm_idx - offset)
        call_idx = min(len(matrix.rows) - 1, atm_idx + offset)

        put_row = matrix.rows[put_idx]
        call_row = matrix.rows[call_idx]

        call_ltp = call_row.call.ltp if call_row.call else 0.0
        put_ltp = put_row.put.ltp if put_row.put else 0.0
        strangle_prem = round(call_ltp + put_ltp, 2)
        lot_size = summary.lot_size
        lot_cost = round(strangle_prem * lot_size, 2)

        lower_be = round(put_row.strike - strangle_prem, 2)
        upper_be = round(call_row.strike + strangle_prem, 2)
        implied_move = round((strangle_prem / summary.spot_price) * 100.0, 2) if summary.spot_price > 0 else 0.0

        c_oi = call_row.call.open_interest if call_row.call else 0
        p_oi = put_row.put.open_interest if put_row.put else 0

        # Greeks
        c_delta = call_row.call.delta if (call_row.call and call_row.call.delta is not None) else 0.3
        p_delta = put_row.put.delta if (put_row.put and put_row.put.delta is not None) else -0.3
        c_gamma = call_row.call.gamma if (call_row.call and call_row.call.gamma is not None) else 0.0008
        p_gamma = put_row.put.gamma if (put_row.put and put_row.put.gamma is not None) else 0.0008
        c_theta = call_row.call.theta if (call_row.call and call_row.call.theta is not None) else -7.0
        p_theta = put_row.put.theta if (put_row.put and put_row.put.theta is not None) else -7.0
        c_vega = call_row.call.vega if (call_row.call and call_row.call.vega is not None) else 10.0
        p_vega = put_row.put.vega if (put_row.put and put_row.put.vega is not None) else 10.0

        combined_greeks = CombinedGreeks(
            net_delta=round(c_delta + p_delta, 4),
            net_gamma=round(c_gamma + p_gamma, 6),
            net_theta=round(c_theta + p_theta, 3),
            net_vega=round(c_vega + p_vega, 3)
        )

        return StrangleDetails(
            underlying=summary.underlying,
            expiry=summary.expiry,
            exchange=summary.exchange,
            spot_price=summary.spot_price,
            call_strike=call_row.strike,
            put_strike=put_row.strike,
            strike_width=round(call_row.strike - put_row.strike, 2),
            call_ltp=call_ltp,
            put_ltp=put_ltp,
            strangle_premium=strangle_prem,
            lot_size=lot_size,
            strangle_lot_cost=lot_cost,
            lower_breakeven=lower_be,
            upper_breakeven=upper_be,
            implied_move_pct=implied_move,
            total_oi=c_oi + p_oi,
            combined_greeks=combined_greeks
        )

    def multi_strike_comparison(
        self,
        underlying: str,
        expiry: Optional[str] = None,
        strike_window: int = 5,
        exchange: Optional[str] = None
    ) -> MultiStrikeAnalysis:
        """
        Builds multi-strike comparative matrix:
        Compares synthetic straddle premiums, combined OI, PCR, Net Delta, and Implied Move %
        across ATM ± N strikes.
        """
        matrix = option_chain_builder.build(underlying, expiry=expiry, strike_window=strike_window, exchange=exchange)
        summary = matrix.summary

        rows: List[MultiStrikeRow] = []
        min_prem = float("inf")
        cheapest_strike = summary.atm_strike
        max_oi = -1
        max_oi_strike = summary.atm_strike

        for r in matrix.rows:
            c_ltp = r.call.ltp if r.call else 0.0
            p_ltp = r.put.ltp if r.put else 0.0
            prem = round(c_ltp + p_ltp, 2)

            c_oi = r.call.open_interest if r.call else 0
            p_oi = r.put.open_interest if r.put else 0
            tot_oi = c_oi + p_oi
            pcr = round(p_oi / c_oi, 2) if c_oi > 0 else 0.0

            c_delta = r.call.delta if (r.call and r.call.delta is not None) else 0.5
            p_delta = r.put.delta if (r.put and r.put.delta is not None) else -0.5
            net_delta = round(c_delta + p_delta, 4)

            c_theta = r.call.theta if (r.call and r.call.theta is not None) else -8.0
            p_theta = r.put.theta if (r.put and r.put.theta is not None) else -8.0
            net_theta = round(c_theta + p_theta, 3)

            imp_move = round((prem / summary.spot_price) * 100.0, 2) if summary.spot_price > 0 else 0.0

            if prem > 0 and prem < min_prem:
                min_prem = prem
                cheapest_strike = r.strike

            if tot_oi > max_oi:
                max_oi = tot_oi
                max_oi_strike = r.strike

            rows.append(MultiStrikeRow(
                strike=r.strike,
                is_atm=r.is_atm,
                call_ltp=c_ltp,
                put_ltp=p_ltp,
                straddle_premium=prem,
                call_oi=c_oi,
                put_oi=p_oi,
                total_oi=tot_oi,
                pcr=pcr,
                net_delta=net_delta,
                net_theta=net_theta,
                implied_move_pct=imp_move
            ))

        return MultiStrikeAnalysis(
            underlying=summary.underlying,
            expiry=summary.expiry,
            spot_price=summary.spot_price,
            atm_strike=summary.atm_strike,
            lot_size=summary.lot_size,
            rows=rows,
            cheapest_straddle_strike=cheapest_strike,
            max_oi_strike=max_oi_strike
        )

straddle_engine = StraddleEngine()

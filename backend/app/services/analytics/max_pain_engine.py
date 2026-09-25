import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field

from backend.app.services.angel.instrument_master import instrument_master
from backend.app.services.market.quote_engine import quote_engine
from backend.app.services.analytics.option_chain_builder import option_chain_builder, OptionChainMatrix

@dataclass
class StrikeLossPoint:
    strike: float
    call_loss: float
    put_loss: float
    total_loss: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PCRSuite:
    oi_pcr: float
    volume_pcr: float
    oi_change_pcr: float
    sentiment: str  # Extremely Bullish, Bullish, Neutral, Bearish, Extremely Bearish
    interpretation: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MaxPainAnalysis:
    underlying: str
    expiry: str
    exchange: str
    spot_price: float
    atm_strike: float
    max_pain_strike: float
    distance_to_spot: float
    distance_pct: float
    total_loss_at_max_pain: float
    pcr_suite: PCRSuite
    total_call_oi: int
    total_put_oi: int
    loss_curve: List[StrikeLossPoint]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "pcr_suite": self.pcr_suite.to_dict(),
            "loss_curve": [p.to_dict() for p in self.loss_curve]
        }


class MaxPainEngine:
    """
    Max Pain & Put-Call Ratio (PCR) Analytics Engine.
    
    Principles:
    1. Max Pain Theory: Option sellers (institutional writers) manipulate or pin the underlying price 
       towards the strike where cumulative option holder payouts are minimized at expiry.
       Total Loss(S) = sum_{K} max(0, S - K) * Call_OI(K) + sum_{K} max(0, K - S) * Put_OI(K)
       Max Pain = argmin_{S} Total Loss(S)
       
    2. Comprehensive PCR Suite:
       - Open Interest PCR = Total Put OI / Total Call OI
       - Volume PCR = Total Put Volume / Total Call Volume
       - Change in OI PCR = Net Put OI Change / Net Call OI Change
    """

    def calculate_max_pain(
        self,
        underlying: str,
        expiry: Optional[str] = None,
        exchange: Optional[str] = None
    ) -> MaxPainAnalysis:
        u = underlying.strip().upper()
        # Retrieve full option chain across wide strike window
        matrix = option_chain_builder.build(u, expiry=expiry, strike_window=20, exchange=exchange)
        summary = matrix.summary

        if not matrix.rows:
            raise ValueError(f"No option chain data available for {underlying}")

        strikes = [r.strike for r in matrix.rows]
        call_oi_map = {r.strike: (r.call.open_interest if r.call else 0) for r in matrix.rows}
        put_oi_map = {r.strike: (r.put.open_interest if r.put else 0) for r in matrix.rows}

        # Calculate Cumulative Writer Losses for every test strike S
        loss_curve: List[StrikeLossPoint] = []
        min_loss = float("inf")
        max_pain_strike = summary.atm_strike

        for s in strikes:
            call_loss = 0.0
            put_loss = 0.0

            for k in strikes:
                c_oi = call_oi_map.get(k, 0)
                p_oi = put_oi_map.get(k, 0)

                # If underlying expires at s:
                # Call holder receives max(0, s - k)
                if s > k and c_oi > 0:
                    call_loss += (s - k) * c_oi
                # Put holder receives max(0, k - s)
                if k > s and p_oi > 0:
                    put_loss += (k - s) * p_oi

            total_loss = call_loss + put_loss
            loss_curve.append(StrikeLossPoint(
                strike=s,
                call_loss=round(call_loss, 2),
                put_loss=round(put_loss, 2),
                total_loss=round(total_loss, 2)
            ))

            if total_loss < min_loss:
                min_loss = total_loss
                max_pain_strike = s

        dist = round(max_pain_strike - summary.spot_price, 2)
        dist_pct = round((dist / summary.spot_price) * 100.0, 2) if summary.spot_price > 0 else 0.0

        # Calculate Complete PCR Suite
        tot_call_oi = summary.total_call_oi
        tot_put_oi = summary.total_put_oi
        tot_call_vol = summary.total_call_volume
        tot_put_vol = summary.total_put_volume

        oi_pcr = round(tot_put_oi / tot_call_oi, 4) if tot_call_oi > 0 else 0.0
        vol_pcr = round(tot_put_vol / tot_call_vol, 4) if tot_call_vol > 0 else 0.0

        tot_call_oi_chg = sum((r.call.oi_change if r.call else 0) for r in matrix.rows)
        tot_put_oi_chg = sum((r.put.oi_change if r.put else 0) for r in matrix.rows)
        oi_chg_pcr = round(tot_put_oi_chg / tot_call_oi_chg, 4) if tot_call_oi_chg != 0 else oi_pcr

        sentiment, interpretation = self._classify_pcr_sentiment(oi_pcr)

        pcr_suite = PCRSuite(
            oi_pcr=oi_pcr,
            volume_pcr=vol_pcr,
            oi_change_pcr=oi_chg_pcr,
            sentiment=sentiment,
            interpretation=interpretation
        )

        return MaxPainAnalysis(
            underlying=summary.underlying,
            expiry=summary.expiry,
            exchange=summary.exchange,
            spot_price=summary.spot_price,
            atm_strike=summary.atm_strike,
            max_pain_strike=max_pain_strike,
            distance_to_spot=dist,
            distance_pct=dist_pct,
            total_loss_at_max_pain=round(min_loss, 2),
            pcr_suite=pcr_suite,
            total_call_oi=tot_call_oi,
            total_put_oi=tot_put_oi,
            loss_curve=loss_curve
        )

    def _classify_pcr_sentiment(self, pcr: float) -> Tuple[str, str]:
        """Classifies PCR sentiment with market positioning insights."""
        if pcr >= 1.40:
            return (
                "Extremely Bullish",
                "Substantial Put writing dominates. Strong floor/support; market participants expect upward continuation or bounce."
            )
        elif pcr >= 1.10:
            return (
                "Bullish",
                "Put writing exceeds Call writing. Upward bias with solid support levels."
            )
        elif pcr >= 0.90:
            return (
                "Neutral",
                "Balanced open interest distribution between Calls and Puts. Rangebound market expected."
            )
        elif pcr >= 0.65:
            return (
                "Bearish",
                "Call writing outpaces Put writing. Overhead resistance overhead capping upside."
            )
        else:
            return (
                "Extremely Bearish",
                "Aggressive Call writing dominance. Heavy selling pressure and weak put support below."
            )

max_pain_engine = MaxPainEngine()

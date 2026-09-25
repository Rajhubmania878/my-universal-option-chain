from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field

from backend.app.services.analytics.option_chain_builder import option_chain_builder, OptionChainMatrix, OptionChainRow

@dataclass
class ContractBuildup:
    symbol: str
    token: str
    strike: float
    option_type: str  # CE or PE
    ltp: float
    price_change: float
    price_change_pct: float
    open_interest: int
    oi_change: int
    oi_change_pct: float
    volume: int
    buildup_type: str       # "Long Buildup", "Short Buildup", "Long Unwinding", "Short Covering", "Neutral"
    bias: str               # "Bullish", "Bearish", "Neutral"
    is_oi_spurt: bool       # True if OI change > threshold
    is_volume_spike: bool   # True if volume is abnormally high

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BuildupSummary:
    total_long_buildup: int
    total_short_buildup: int
    total_long_unwinding: int
    total_short_covering: int
    dominant_market_bias: str  # "Bullish", "Bearish", "Indecisive"
    oi_spurts_count: int
    volume_spikes_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BuildupAnalysis:
    underlying: str
    expiry: str
    exchange: str
    spot_price: float
    atm_strike: float
    summary: BuildupSummary
    contracts: List[ContractBuildup]
    top_oi_gainers: List[ContractBuildup]
    top_oi_losers: List[ContractBuildup]
    top_volume_actives: List[ContractBuildup]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "summary": self.summary.to_dict(),
            "contracts": [c.to_dict() for c in self.contracts],
            "top_oi_gainers": [c.to_dict() for c in self.top_oi_gainers],
            "top_oi_losers": [c.to_dict() for c in self.top_oi_losers],
            "top_volume_actives": [c.to_dict() for c in self.top_volume_actives]
        }


class BuildupTracker:
    """
    Open Interest (OI) Spurts, Volume Spikes & Institutional Buildup Tracker:
    
    1. Long Buildup:
       Price UP + OI UP (Aggressive buying of contracts; institutional long positioning).
       Bias: Bullish
       
    2. Short Buildup:
       Price DOWN + OI UP (Aggressive writing/selling of contracts; short positioning).
       Bias: Bearish
       
    3. Long Unwinding:
       Price DOWN + OI DOWN (Liquidation/profit taking of existing long positions).
       Bias: Bearish (weakness)
       
    4. Short Covering:
       Price UP + OI DOWN (Writers panic buying back to cover short exposure; short squeeze).
       Bias: Bullish (relief/rally)
       
    5. OI Spurt:
       OI Change > 15% (or > 10,000 contracts for indices / > 1,000 for commodities)
       
    6. Volume Spike:
       Volume > 2.5x mean strike volume across the chain
    """

    def classify_buildup(self, price_change: float, oi_change: int) -> tuple[str, str]:
        """Classifies price and OI changes into the 4 classic technical buildup states."""
        # Thresholds to avoid noise
        min_p_chg = 0.05
        min_oi_chg = 10

        if price_change > min_p_chg and oi_change > min_oi_chg:
            return "Long Buildup", "Bullish"
        elif price_change < -min_p_chg and oi_change > min_oi_chg:
            return "Short Buildup", "Bearish"
        elif price_change < -min_p_chg and oi_change < -min_oi_chg:
            return "Long Unwinding", "Bearish"
        elif price_change > min_p_chg and oi_change < -min_oi_chg:
            return "Short Covering", "Bullish"
        else:
            return "Neutral", "Neutral"

    def analyze_buildup(
        self,
        underlying: str,
        expiry: Optional[str] = None,
        strike_window: int = 10,
        exchange: Optional[str] = None
    ) -> BuildupAnalysis:
        u = underlying.strip().upper()
        matrix = option_chain_builder.build(u, expiry=expiry, strike_window=strike_window, exchange=exchange)
        summary = matrix.summary

        all_contracts: List[ContractBuildup] = []

        # Calculate average volume for relative volume spikes
        total_vol = 0
        leg_count = 0
        for r in matrix.rows:
            if r.call:
                total_vol += r.call.volume
                leg_count += 1
            if r.put:
                total_vol += r.put.volume
                leg_count += 1
        avg_vol = (total_vol / leg_count) if leg_count > 0 else 1000

        # Process Calls and Puts across all strikes
        for r in matrix.rows:
            # Process Call Leg
            if r.call:
                c = r.call
                b_type, bias = self.classify_buildup(c.change, c.oi_change)
                prev_oi = c.open_interest - c.oi_change
                oi_pct = round((c.oi_change / prev_oi) * 100.0, 2) if prev_oi > 0 else 0.0
                is_spurt = abs(oi_pct) >= 15.0 or abs(c.oi_change) >= 10000
                is_vol_spike = c.volume >= max(5000, avg_vol * 2.0)

                all_contracts.append(ContractBuildup(
                    symbol=c.symbol,
                    token=c.token,
                    strike=r.strike,
                    option_type="CE",
                    ltp=c.ltp,
                    price_change=c.change,
                    price_change_pct=c.change_percent,
                    open_interest=c.open_interest,
                    oi_change=c.oi_change,
                    oi_change_pct=oi_pct,
                    volume=c.volume,
                    buildup_type=b_type,
                    bias=bias,
                    is_oi_spurt=is_spurt,
                    is_volume_spike=is_vol_spike
                ))

            # Process Put Leg
            if r.put:
                p = r.put
                b_type, bias = self.classify_buildup(p.change, p.oi_change)
                prev_p_oi = p.open_interest - p.oi_change
                p_oi_pct = round((p.oi_change / prev_p_oi) * 100.0, 2) if prev_p_oi > 0 else 0.0
                is_spurt = abs(p_oi_pct) >= 15.0 or abs(p.oi_change) >= 10000
                is_vol_spike = p.volume >= max(5000, avg_vol * 2.0)

                all_contracts.append(ContractBuildup(
                    symbol=p.symbol,
                    token=p.token,
                    strike=r.strike,
                    option_type="PE",
                    ltp=p.ltp,
                    price_change=p.change,
                    price_change_pct=p.change_percent,
                    open_interest=p.open_interest,
                    oi_change=p.oi_change,
                    oi_change_pct=p_oi_pct,
                    volume=p.volume,
                    buildup_type=b_type,
                    bias=bias,
                    is_oi_spurt=is_spurt,
                    is_volume_spike=is_vol_spike
                ))

        # Tally summary
        lb_count = sum(1 for c in all_contracts if c.buildup_type == "Long Buildup")
        sb_count = sum(1 for c in all_contracts if c.buildup_type == "Short Buildup")
        lu_count = sum(1 for c in all_contracts if c.buildup_type == "Long Unwinding")
        sc_count = sum(1 for c in all_contracts if c.buildup_type == "Short Covering")
        spurts = sum(1 for c in all_contracts if c.is_oi_spurt)
        vol_spikes = sum(1 for c in all_contracts if c.is_volume_spike)

        bullish_score = lb_count + sc_count
        bearish_score = sb_count + lu_count
        if bullish_score > bearish_score + 2:
            dominant_bias = "Bullish"
        elif bearish_score > bullish_score + 2:
            dominant_bias = "Bearish"
        else:
            dominant_bias = "Indecisive"

        buildup_summary = BuildupSummary(
            total_long_buildup=lb_count,
            total_short_buildup=sb_count,
            total_long_unwinding=lu_count,
            total_short_covering=sc_count,
            dominant_market_bias=dominant_bias,
            oi_spurts_count=spurts,
            volume_spikes_count=vol_spikes
        )

        # Rankings
        top_gainers = sorted(all_contracts, key=lambda c: c.oi_change, reverse=True)[:5]
        top_losers = sorted(all_contracts, key=lambda c: c.oi_change)[:5]
        top_volume = sorted(all_contracts, key=lambda c: c.volume, reverse=True)[:5]

        return BuildupAnalysis(
            underlying=summary.underlying,
            expiry=summary.expiry,
            exchange=summary.exchange,
            spot_price=summary.spot_price,
            atm_strike=summary.atm_strike,
            summary=buildup_summary,
            contracts=all_contracts,
            top_oi_gainers=top_gainers,
            top_oi_losers=top_losers,
            top_volume_actives=top_volume
        )

buildup_tracker = BuildupTracker()

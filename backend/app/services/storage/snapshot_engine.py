"""
Historical Snapshot Ingestion & Time-Travel Market Replay Engine (Phase 17).

Provides:
- Periodic snapshot archival of complete Option Chains (Strikes, LTP, OI, IV, Greeks)
- Time-travel market replay (reconstructing exact chain state at any historical timestamp)
- Strike-by-strike comparison against baseline (e.g. 09:15 AM Open vs current scrubber)
- Intraday OI migration and Max Pain shift tracking
"""
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import deque
import logging

logger = logging.getLogger("options_dashboard:snapshot_engine")

class OptionChainSnapshot:
    def __init__(
        self,
        snapshot_id: str,
        underlying: str,
        timestamp: float,
        market_time: str,
        spot_price: float,
        atm_strike: float,
        total_ce_oi: int,
        total_pe_oi: int,
        pcr_oi: float,
        pcr_volume: float,
        max_pain: float,
        atm_straddle_premium: float,
        strikes: List[Dict[str, Any]]
    ):
        self.snapshot_id = snapshot_id
        self.underlying = underlying.upper()
        self.timestamp = timestamp
        self.market_time = market_time
        self.spot_price = spot_price
        self.atm_strike = atm_strike
        self.total_ce_oi = total_ce_oi
        self.total_pe_oi = total_pe_oi
        self.pcr_oi = pcr_oi
        self.pcr_volume = pcr_volume
        self.max_pain = max_pain
        self.atm_straddle_premium = atm_straddle_premium
        self.strikes = strikes

    def to_dict(self, include_strikes: bool = True) -> Dict[str, Any]:
        data = {
            "snapshot_id": self.snapshot_id,
            "underlying": self.underlying,
            "timestamp": self.timestamp,
            "market_time": self.market_time,
            "spot_price": self.spot_price,
            "atm_strike": self.atm_strike,
            "total_ce_oi": self.total_ce_oi,
            "total_pe_oi": self.total_pe_oi,
            "pcr_oi": self.pcr_oi,
            "pcr_volume": self.pcr_volume,
            "max_pain": self.max_pain,
            "atm_straddle_premium": self.atm_straddle_premium,
            "strike_count": len(self.strikes)
        }
        if include_strikes:
            data["strikes"] = self.strikes
        return data


class SnapshotIngestionEngine:
    def __init__(self, max_snapshots_per_underlying: int = 500):
        self.max_snapshots = max_snapshots_per_underlying
        # underlying -> list of OptionChainSnapshot sorted by timestamp
        self._snapshots: Dict[str, List[OptionChainSnapshot]] = {
            "CRUDEOIL": [],
            "NIFTY": [],
            "BANKNIFTY": []
        }
        self._seed_default_intraday_history()

    def _seed_default_intraday_history(self):
        """Pre-seeds realistic intraday snapshots for today (09:15 to 15:30) for CRUDEOIL and NIFTY."""
        now = time.time()
        # Seed CRUDEOIL (MCX): 09:15 to current time, 15-minute intervals
        crude_base_spot = 8840.0
        crude_atm = 8800.0
        strikes_range = [8600, 8700, 8800, 8900, 9000, 9100, 9200]

        # 9 snapshots spanning intraday progression
        intervals = [
            ("09:15:00", 8840.0, 0.95, 8800.0, 520.0),
            ("09:30:00", 8855.0, 0.98, 8800.0, 505.0),
            ("10:00:00", 8872.0, 1.04, 8900.0, 485.0),
            ("10:30:00", 8890.0, 1.12, 8900.0, 460.0),
            ("11:30:00", 8895.0, 1.15, 8900.0, 440.0),
            ("12:30:00", 8880.0, 1.08, 8900.0, 415.0),
            ("13:30:00", 8910.0, 1.20, 8900.0, 395.0),
            ("14:30:00", 8925.0, 1.24, 8900.0, 370.0),
            ("15:15:00", 8908.0, 1.19, 8900.0, 350.0),
        ]

        base_time = now - (len(intervals) * 900)

        for i, (m_time, spot, pcr, max_pain, straddle_prem) in enumerate(intervals):
            ts = base_time + (i * 900)
            strikes = []
            tot_ce_oi = 0
            tot_pe_oi = 0

            for k in strikes_range:
                # Intraday OI accumulation effect
                accum_factor = 1.0 + (i * 0.12)
                ce_oi = int((12000 if k >= spot else 4500) * accum_factor + (k - 8900) * 2)
                pe_oi = int((14500 if k <= spot else 3800) * accum_factor * pcr)
                tot_ce_oi += ce_oi
                tot_pe_oi += pe_oi

                # Theoretical price
                dist = (spot - k)
                ce_ltp = max(5.0, 180.0 + dist * 0.55 - (i * 12.0))
                pe_ltp = max(5.0, 175.0 - dist * 0.45 - (i * 11.0))

                strikes.append({
                    "strike": float(k),
                    "ce": {
                        "ltp": round(ce_ltp, 2),
                        "oi": ce_oi,
                        "oi_change": int(ce_oi * 0.08 * i),
                        "volume": int(ce_oi * 1.5),
                        "iv": round(21.5 - i * 0.3, 1),
                        "delta": round(0.50 + dist * 0.001, 3)
                    },
                    "pe": {
                        "ltp": round(pe_ltp, 2),
                        "oi": pe_oi,
                        "oi_change": int(pe_oi * 0.11 * i),
                        "volume": int(pe_oi * 1.7),
                        "iv": round(21.0 - i * 0.25, 1),
                        "delta": round(-0.50 + dist * 0.001, 3)
                    }
                })

            snap = OptionChainSnapshot(
                snapshot_id=f"SNAP-CRUDE-{i+1:03d}",
                underlying="CRUDEOIL",
                timestamp=ts,
                market_time=m_time,
                spot_price=spot,
                atm_strike=round(spot / 100.0) * 100.0,
                total_ce_oi=tot_ce_oi,
                total_pe_oi=tot_pe_oi,
                pcr_oi=round(tot_pe_oi / max(1, tot_ce_oi), 2),
                pcr_volume=round(pcr, 2),
                max_pain=max_pain,
                atm_straddle_premium=straddle_prem,
                strikes=strikes
            )
            self._snapshots["CRUDEOIL"].append(snap)

    def capture_snapshot(
        self,
        underlying: str,
        spot_price: float,
        strikes_data: List[Dict[str, Any]],
        pcr_oi: float = 1.0,
        pcr_volume: float = 1.0,
        max_pain: Optional[float] = None,
        atm_straddle_premium: Optional[float] = None
    ) -> OptionChainSnapshot:
        """Captures and stores an Option Chain snapshot in the historical buffer."""
        u_symbol = underlying.upper()
        if u_symbol not in self._snapshots:
            self._snapshots[u_symbol] = []

        now = time.time()
        m_time = datetime.fromtimestamp(now).strftime("%H:%M:%S")
        atm_k = round(spot_price / 100.0) * 100.0 if u_symbol == "CRUDEOIL" else round(spot_price / 50.0) * 50.0

        tot_ce = sum(s.get("ce", {}).get("oi", 0) for s in strikes_data)
        tot_pe = sum(s.get("pe", {}).get("oi", 0) for s in strikes_data)

        mp = max_pain or atm_k
        straddle_p = atm_straddle_premium or 450.0

        snap_id = f"SNAP-{u_symbol}-{int(now)}"
        snapshot = OptionChainSnapshot(
            snapshot_id=snap_id,
            underlying=u_symbol,
            timestamp=now,
            market_time=m_time,
            spot_price=round(spot_price, 2),
            atm_strike=atm_k,
            total_ce_oi=tot_ce,
            total_pe_oi=tot_pe,
            pcr_oi=round(pcr_oi, 2),
            pcr_volume=round(pcr_volume, 2),
            max_pain=mp,
            atm_straddle_premium=round(straddle_p, 2),
            strikes=strikes_data
        )

        self._snapshots[u_symbol].append(snapshot)
        if len(self._snapshots[u_symbol]) > self.max_snapshots:
            self._snapshots[u_symbol].pop(0)

        logger.info(f"Captured snapshot {snap_id} for {u_symbol} @ ₹{spot_price:.2f} (PCR: {pcr_oi})")
        return snapshot

    def get_timeline(self, underlying: str) -> List[Dict[str, Any]]:
        """Returns metadata list of all available snapshots for scrubbing."""
        u_symbol = underlying.upper()
        snaps = self._snapshots.get(u_symbol, [])
        return [s.to_dict(include_strikes=False) for s in snaps]

    def get_snapshot_by_id(self, underlying: str, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Returns full snapshot details by snapshot_id."""
        u_symbol = underlying.upper()
        snaps = self._snapshots.get(u_symbol, [])
        for s in snaps:
            if s.snapshot_id == snapshot_id:
                return s.to_dict(include_strikes=True)
        return None

    def get_snapshot_at_or_before(self, underlying: str, target_timestamp: float) -> Optional[Dict[str, Any]]:
        """Finds nearest snapshot at or immediately preceding target_timestamp."""
        u_symbol = underlying.upper()
        snaps = self._snapshots.get(u_symbol, [])
        if not snaps:
            return None

        best = snaps[0]
        for s in snaps:
            if s.timestamp <= target_timestamp:
                best = s
            else:
                break
        return best.to_dict(include_strikes=True)

    def compare_snapshots(
        self,
        underlying: str,
        baseline_id: str,
        target_id: str
    ) -> Dict[str, Any]:
        """
        Computes strike-by-strike deltas between baseline and target snapshot.
        Essential for tracking OI buildup and premium decay across the trading session.
        """
        base_snap = self.get_snapshot_by_id(underlying, baseline_id)
        tgt_snap = self.get_snapshot_by_id(underlying, target_id)

        if not base_snap or not tgt_snap:
            raise ValueError("Invalid baseline or target snapshot ID")

        base_strikes_map = {s["strike"]: s for s in base_snap.get("strikes", [])}
        deltas = []

        for tgt_s in tgt_snap.get("strikes", []):
            k = tgt_s["strike"]
            base_s = base_strikes_map.get(k)

            if base_s:
                ce_oi_diff = tgt_s.get("ce", {}).get("oi", 0) - base_s.get("ce", {}).get("oi", 0)
                pe_oi_diff = tgt_s.get("pe", {}).get("oi", 0) - base_s.get("pe", {}).get("oi", 0)
                ce_ltp_diff = round(tgt_s.get("ce", {}).get("ltp", 0.0) - base_s.get("ce", {}).get("ltp", 0.0), 2)
                pe_ltp_diff = round(tgt_s.get("pe", {}).get("ltp", 0.0) - base_s.get("pe", {}).get("ltp", 0.0), 2)
                ce_iv_diff = round(tgt_s.get("ce", {}).get("iv", 0.0) - base_s.get("ce", {}).get("iv", 0.0), 2)
                pe_iv_diff = round(tgt_s.get("pe", {}).get("iv", 0.0) - base_s.get("pe", {}).get("iv", 0.0), 2)
            else:
                ce_oi_diff = tgt_s.get("ce", {}).get("oi", 0)
                pe_oi_diff = tgt_s.get("pe", {}).get("oi", 0)
                ce_ltp_diff = round(tgt_s.get("ce", {}).get("ltp", 0.0), 2)
                pe_ltp_diff = round(tgt_s.get("pe", {}).get("ltp", 0.0), 2)
                ce_iv_diff = 0.0
                pe_iv_diff = 0.0

            deltas.append({
                "strike": k,
                "ce": {
                    "baseline_oi": base_s.get("ce", {}).get("oi", 0) if base_s else 0,
                    "target_oi": tgt_s.get("ce", {}).get("oi", 0),
                    "oi_diff": ce_oi_diff,
                    "baseline_ltp": base_s.get("ce", {}).get("ltp", 0.0) if base_s else 0.0,
                    "target_ltp": tgt_s.get("ce", {}).get("ltp", 0.0),
                    "ltp_diff": ce_ltp_diff,
                    "iv_diff": ce_iv_diff
                },
                "pe": {
                    "baseline_oi": base_s.get("pe", {}).get("oi", 0) if base_s else 0,
                    "target_oi": tgt_s.get("pe", {}).get("oi", 0),
                    "oi_diff": pe_oi_diff,
                    "baseline_ltp": base_s.get("pe", {}).get("ltp", 0.0) if base_s else 0.0,
                    "target_ltp": tgt_s.get("pe", {}).get("ltp", 0.0),
                    "ltp_diff": pe_ltp_diff,
                    "iv_diff": pe_iv_diff
                }
            })

        return {
            "underlying": underlying.upper(),
            "baseline": {
                "id": base_snap["snapshot_id"],
                "time": base_snap["market_time"],
                "spot": base_snap["spot_price"],
                "pcr": base_snap["pcr_oi"],
                "straddle": base_snap["atm_straddle_premium"]
            },
            "target": {
                "id": tgt_snap["snapshot_id"],
                "time": tgt_snap["market_time"],
                "spot": tgt_snap["spot_price"],
                "pcr": tgt_snap["pcr_oi"],
                "straddle": tgt_snap["atm_straddle_premium"]
            },
            "spot_shift": round(tgt_snap["spot_price"] - base_snap["spot_price"], 2),
            "pcr_shift": round(tgt_snap["pcr_oi"] - base_snap["pcr_oi"], 2),
            "straddle_decay": round(tgt_snap["atm_straddle_premium"] - base_snap["atm_straddle_premium"], 2),
            "deltas": deltas
        }

snapshot_engine = SnapshotIngestionEngine()

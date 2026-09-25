"""
Real-Time Institutional Settlement, Physical Delivery Risk & Expiry Pin-Risk Engine (Phase 24).

Capabilities:
1. Expiry Day Pin-Risk Probability & Delta Jump Analyzer:
   - Computes probability of underlying pinning at a strike at expiry cutoff.
   - Calculates Delta cliff jump risk (discontinuous derivative shift at expiry).
2. Physical Delivery vs Cash Settlement Margin Escalation Model:
   - Indian Equity Stock Options (Physical delivery obligation & 4-day staged margin escalation).
   - Index Options (Cash-settled on NFO/BFO).
   - Commodity Options (MCX Crude Oil devolving into Commodity Futures).
3. Indian Regulatory Taxation & Transaction Cost Simulator (STT / CTT / SEBI / GST / Stamp Duty):
   - Handles the critical "STT Trap" on ITM exercised options (0.125% on full contract value).
   - Computes CTT for MCX Crude Oil options.
"""
from typing import Dict, Any, List, Optional
import math
from dataclasses import dataclass, asdict

from backend.app.core.logging import logger
from backend.app.services.analytics.greeks_engine import greeks_engine


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass
class PinRiskAnalysis:
    strike: float
    spot_price: float
    distance_pts: float
    distance_pct: float
    pin_probability_pct: float
    call_itm_probability_pct: float
    put_itm_probability_pct: float
    delta_jump_call: float  # Current Delta -> 1.0 (if ITM) or 0.0 (if OTM)
    delta_jump_put: float   # Current Delta -> -1.0 (if ITM) or 0.0 (if OTM)
    gamma_risk_multiplier: float
    risk_level: str  # "EXTREME_PIN_RISK", "ELEVATED", "MODERATE", "NEGLIGIBLE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strike": self.strike,
            "spot_price": round(self.spot_price, 2),
            "distance_pts": round(self.distance_pts, 2),
            "distance_pct": round(self.distance_pct, 2),
            "pin_probability_pct": round(self.pin_probability_pct, 2),
            "call_itm_probability_pct": round(self.call_itm_probability_pct, 2),
            "put_itm_probability_pct": round(self.put_itm_probability_pct, 2),
            "delta_jump_call": round(self.delta_jump_call, 3),
            "delta_jump_put": round(self.delta_jump_put, 3),
            "gamma_risk_multiplier": round(self.gamma_risk_multiplier, 1),
            "risk_level": self.risk_level
        }


@dataclass
class SettlementCostBreakdown:
    symbol: str
    underlying: str
    strike: float
    option_type: str
    action: str  # "EXERCISE_ITM", "EXPIRE_OTM", "SQUARE_OFF"
    quantity: int
    execution_price: float
    settlement_type: str  # "CASH_SETTLED", "PHYSICAL_DELIVERY", "FUTURES_DEVOLUTION"
    turnover_premium: float
    notional_contract_value: float
    stt_ctt_tax: float
    exchange_txn_charge: float
    sebi_turnover_fee: float
    stamp_duty: float
    gst_18_pct: float
    total_statutory_charges: float
    net_settlement_cashflow: float
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "underlying": self.underlying,
            "strike": self.strike,
            "option_type": self.option_type,
            "action": self.action,
            "quantity": self.quantity,
            "execution_price": round(self.execution_price, 2),
            "settlement_type": self.settlement_type,
            "turnover_premium": round(self.turnover_premium, 2),
            "notional_contract_value": round(self.notional_contract_value, 2),
            "stt_ctt_tax": round(self.stt_ctt_tax, 2),
            "exchange_txn_charge": round(self.exchange_txn_charge, 2),
            "sebi_turnover_fee": round(self.sebi_turnover_fee, 2),
            "stamp_duty": round(self.stamp_duty, 2),
            "gst_18_pct": round(self.gst_18_pct, 2),
            "total_statutory_charges": round(self.total_statutory_charges, 2),
            "net_settlement_cashflow": round(self.net_settlement_cashflow, 2),
            "notes": self.notes
        }


@dataclass
class PhysicalDeliveryMarginSchedule:
    days_to_expiry: int
    stage_name: str
    mandatory_delivery_margin_pct: float
    required_capital_per_lot: float
    action_required: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PinRiskAndSettlementEngine:
    """
    Engine for analyzing Pin-Risk on expiry day, Physical Delivery / Futures devolution, and Indian regulatory taxes.
    """
    def __init__(self):
        logger.info("Initialized PinRiskAndSettlementEngine (Phase 24)")

    def calculate_pin_risk(
        self,
        spot: float = 8908.0,
        strikes: Optional[List[float]] = None,
        iv: float = 0.28,
        hours_to_cutoff: float = 2.5
    ) -> List[PinRiskAnalysis]:
        """
        Calculates pin risk and ITM probabilities for near ATM strikes on expiry day.
        """
        if strikes is None:
            step = 100 if spot > 5000 else 50
            atm = round(spot / step) * step
            strikes = [atm - 2 * step, atm - step, atm, atm + step, atm + 2 * step]

        results: List[PinRiskAnalysis] = []
        t_years = max(0.0001, (hours_to_cutoff / 24.0) / 365.0)
        sigma_sqrt_t = iv * math.sqrt(t_years)

        for k in strikes:
            dist_pts = spot - k
            dist_pct = (dist_pts / spot) * 100.0

            d1 = (math.log(spot / k) + (0.07 + 0.5 * iv * iv) * t_years) / sigma_sqrt_t
            d2 = d1 - sigma_sqrt_t

            p_call_itm = _norm_cdf(d2) * 100.0
            p_put_itm = (1.0 - _norm_cdf(d2)) * 100.0

            # Pin density at strike K within +- 0.25% band
            pdf_val = _norm_pdf(d2)
            pin_prob = (pdf_val / (spot * sigma_sqrt_t)) * (spot * 0.005) * 100.0
            pin_prob = min(95.0, max(1.0, pin_prob))

            curr_delta_call = _norm_cdf(d1)
            curr_delta_put = curr_delta_call - 1.0

            target_delta_call = 1.0 if spot >= k else 0.0
            target_delta_put = -1.0 if spot <= k else 0.0

            delta_jump_call = abs(target_delta_call - curr_delta_call)
            delta_jump_put = abs(target_delta_put - curr_delta_put)

            # Gamma explodes as t -> 0 near ATM
            gamma_multiplier = 1.0 / math.sqrt(max(0.0001, t_years * 365.0))

            if abs(dist_pct) <= 0.3:
                risk = "EXTREME_PIN_RISK"
            elif abs(dist_pct) <= 0.8:
                risk = "ELEVATED"
            elif abs(dist_pct) <= 1.5:
                risk = "MODERATE"
            else:
                risk = "NEGLIGIBLE"

            results.append(PinRiskAnalysis(
                strike=k,
                spot_price=spot,
                distance_pts=dist_pts,
                distance_pct=dist_pct,
                pin_probability_pct=pin_prob,
                call_itm_probability_pct=p_call_itm,
                put_itm_probability_pct=p_put_itm,
                delta_jump_call=delta_jump_call,
                delta_jump_put=delta_jump_put,
                gamma_risk_multiplier=gamma_multiplier,
                risk_level=risk
            ))

        return results

    def compute_settlement_taxes(
        self,
        underlying: str = "CRUDEOIL",
        strike: float = 8900.0,
        option_type: str = "CE",
        action: str = "EXERCISE_ITM",
        quantity: int = 100,
        execution_price: float = 120.0,
        spot_at_expiry: float = 8950.0
    ) -> SettlementCostBreakdown:
        """
        Computes statutory Indian taxes (STT/CTT, Exchange Txn, SEBI, GST, Stamp Duty) on settlement.
        """
        is_mcx = underlying.upper() == "CRUDEOIL"
        is_index = underlying.upper() in ["NIFTY", "BANKNIFTY", "FINNIFTY"]

        settlement_type = "FUTURES_DEVOLUTION" if is_mcx else ("CASH_SETTLED" if is_index else "PHYSICAL_DELIVERY")
        turnover_prem = execution_price * quantity
        notional_val = (spot_at_expiry if action == "EXERCISE_ITM" else execution_price) * quantity

        # STT / CTT Calculation
        if is_mcx:
            # MCX CTT: 0.05% on Sell side of Option Premium, 0.01% on Futures devolution
            stt_ctt = turnover_prem * 0.0005 if action != "EXERCISE_ITM" else notional_val * 0.0001
        else:
            if action == "EXERCISE_ITM":
                # STT TRAP: 0.125% on entire settlement notional value for exercised stock options!
                stt_ctt = notional_val * 0.00125
            else:
                # Normal sale of options: 0.0625% on premium
                stt_ctt = turnover_prem * 0.000625

        # Exchange Transaction Charge (~0.05% on premium, or 0.003% on delivery)
        exchange_charge = turnover_prem * 0.0005
        # SEBI Turnover Fee (₹10 per crore = 0.0001%)
        sebi_fee = notional_val * 0.000001
        # Stamp Duty (0.003% on Buy premium)
        stamp_duty = turnover_prem * 0.00003
        # GST: 18% on (Exchange Charges + Brokerage ₹20)
        brokerage = 20.0
        gst = (exchange_charge + brokerage) * 0.18

        total_statutory = stt_ctt + exchange_charge + sebi_fee + stamp_duty + gst + brokerage
        intrinsic_val = max(0.0, (spot_at_expiry - strike) if option_type == "CE" else (strike - spot_at_expiry))
        gross_cashflow = intrinsic_val * quantity
        net_cashflow = gross_cashflow - total_statutory

        notes = "Standard cash settled option expiry" if is_index else (
            "Devolves into MCX Crude Oil 100-BBL Futures contract" if is_mcx else
            "Physical Delivery of underlying equity shares enforced with 100% margin"
        )

        return SettlementCostBreakdown(
            symbol=f"{underlying}{int(strike)}{option_type}",
            underlying=underlying,
            strike=strike,
            option_type=option_type,
            action=action,
            quantity=quantity,
            execution_price=execution_price,
            settlement_type=settlement_type,
            turnover_premium=turnover_prem,
            notional_contract_value=notional_val,
            stt_ctt_tax=stt_ctt,
            exchange_txn_charge=exchange_charge,
            sebi_turnover_fee=sebi_fee,
            stamp_duty=stamp_duty,
            gst_18_pct=gst,
            total_statutory_charges=total_statutory,
            net_settlement_cashflow=net_cashflow,
            notes=notes
        )

    def get_physical_margin_schedule(self, spot: float = 8908.0, lot_size: int = 100) -> List[PhysicalDeliveryMarginSchedule]:
        """
        Returns mandatory 4-day staged delivery margin escalation table for physically-settled contracts.
        """
        notional = spot * lot_size
        return [
            PhysicalDeliveryMarginSchedule(4, "Expiry E-4 (Monday)", 10.0, notional * 0.10, "Initial physical delivery risk alert issued"),
            PhysicalDeliveryMarginSchedule(3, "Expiry E-3 (Tuesday)", 25.0, notional * 0.25, "Delivery margin escalated to 25% of contract value"),
            PhysicalDeliveryMarginSchedule(2, "Expiry E-2 (Wednesday)", 50.0, notional * 0.50, "Delivery margin escalated to 50%; close ITM positions to avoid shortfall"),
            PhysicalDeliveryMarginSchedule(1, "Expiry E-1 (Thursday)", 100.0, notional * 1.00, "100% full delivery margin blocked; mandatory square-off if underfunded"),
            PhysicalDeliveryMarginSchedule(0, "Settlement Day (Friday)", 100.0, notional * 1.00, "Final delivery of underlying shares / devolution into futures")
        ]


# Global singleton instance
pin_risk_settlement_engine = PinRiskAndSettlementEngine()

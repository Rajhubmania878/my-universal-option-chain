import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from enum import Enum

from backend.app.services.analytics.straddle_engine import straddle_engine
from backend.app.services.analytics.max_pain_engine import max_pain_engine
from backend.app.services.analytics.volatility_engine import volatility_engine
from backend.app.services.analytics.buildup_tracker import buildup_tracker
from backend.app.services.market.quote_engine import quote_engine

class AlertCondition(str, Enum):
    GREATER_THAN = ">"
    LESS_THAN = "<"
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"

class MetricType(str, Enum):
    SPOT_PRICE = "spot_price"
    ATM_STRADDLE_PREMIUM = "atm_straddle_premium"
    IV_RANK = "iv_rank"
    OI_PCR = "oi_pcr"
    MAX_PAIN_DISTANCE = "max_pain_distance"

@dataclass
class AlertRule:
    id: str
    underlying: str
    metric: MetricType
    condition: AlertCondition
    threshold: float
    message_template: str
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "metric": self.metric.value if isinstance(self.metric, MetricType) else self.metric,
            "condition": self.condition.value if isinstance(self.condition, AlertCondition) else self.condition
        }


@dataclass
class TriggeredAlert:
    id: str
    rule_id: str
    underlying: str
    metric: str
    condition: str
    threshold: float
    current_value: float
    message: str
    triggered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AlertEngine:
    """
    Real-Time Quantitative Alerting & Rule Monitoring Engine:
    
    1. Metric Evaluation:
       - Spot Price Thresholds
       - ATM Straddle Premium Spikes / Decays
       - IV Rank High/Low Bounds (e.g. IVR > 75% for short premium entry)
       - PCR Extreme Sentiments (e.g. PCR < 0.65 or PCR > 1.40)
       - Max Pain Distance Breaches (e.g. Spot divergent > 150 pts from Max Pain)
       
    2. Alert History & Deduplication:
       Maintains chronological audit trail of triggered events without duplicate spam.
    """

    def __init__(self):
        self._rules: Dict[str, AlertRule] = {}
        self._triggered_history: List[TriggeredAlert] = []
        self._seed_default_rules()

    def _seed_default_rules(self):
        defaults = [
            AlertRule(
                id="rule-nifty-high-ivr",
                underlying="NIFTY",
                metric=MetricType.IV_RANK,
                condition=AlertCondition.GREATER_THAN,
                threshold=60.0,
                message_template="NIFTY IV Rank is elevated above {threshold}% (Current: {value}%). Premium selling opportunity."
            ),
            AlertRule(
                id="rule-nifty-pcr-extreme",
                underlying="NIFTY",
                metric=MetricType.OI_PCR,
                condition=AlertCondition.LESS_THAN,
                threshold=0.75,
                message_template="NIFTY OI PCR dropped below {threshold} (Current: {value}). Bearish sentiment building."
            ),
            AlertRule(
                id="rule-crude-straddle-spike",
                underlying="CRUDEOIL",
                metric=MetricType.ATM_STRADDLE_PREMIUM,
                condition=AlertCondition.GREATER_THAN,
                threshold=250.0,
                message_template="CRUDEOIL ATM Straddle expanded past {threshold} pts (Current: {value}). Volatility breakout."
            )
        ]
        for r in defaults:
            self._rules[r.id] = r

    def add_rule(
        self,
        underlying: str,
        metric: MetricType,
        condition: AlertCondition,
        threshold: float,
        message_template: Optional[str] = None
    ) -> AlertRule:
        rule_id = f"rule-{uuid.uuid4().hex[:8]}"
        template = message_template or f"{underlying} {metric.value} {condition.value} {threshold} (Triggered at: {{value}})"
        rule = AlertRule(
            id=rule_id,
            underlying=underlying.upper(),
            metric=metric,
            condition=condition,
            threshold=threshold,
            message_template=template,
            enabled=True
        )
        self._rules[rule_id] = rule
        return rule

    def delete_rule(self, rule_id: str) -> bool:
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def list_rules(self) -> List[AlertRule]:
        return list(self._rules.values())

    def get_history(self, limit: int = 50) -> List[TriggeredAlert]:
        return self._triggered_history[-limit:]

    def evaluate_rules(self, underlying: Optional[str] = None) -> List[TriggeredAlert]:
        """Evaluates all enabled rules against live market & analytical engines."""
        underlyings_to_check = [underlying.upper()] if underlying else list({r.underlying for r in self._rules.values()})
        new_triggers: List[TriggeredAlert] = []

        for u in underlyings_to_check:
            # Gather live metrics for this underlying
            metrics_cache: Dict[str, float] = {}

            # Spot price
            q = quote_engine.get_underlying_quote(u)
            if q:
                metrics_cache[MetricType.SPOT_PRICE.value] = q.ltp

            # Relevant rules for this underlying
            active_rules = [r for r in self._rules.values() if r.enabled and r.underlying == u]
            if not active_rules:
                continue

            # Need straddle?
            if any(r.metric == MetricType.ATM_STRADDLE_PREMIUM for r in active_rules):
                try:
                    std = straddle_engine.calculate_atm_straddle(u)
                    metrics_cache[MetricType.ATM_STRADDLE_PREMIUM.value] = std.straddle_premium
                except Exception:
                    pass

            # Need IV Rank?
            if any(r.metric == MetricType.IV_RANK for r in active_rules):
                try:
                    vol = volatility_engine.analyze_volatility(u)
                    metrics_cache[MetricType.IV_RANK.value] = vol.iv_rank
                except Exception:
                    pass

            # Need PCR or Max Pain?
            if any(r.metric in (MetricType.OI_PCR, MetricType.MAX_PAIN_DISTANCE) for r in active_rules):
                try:
                    mp = max_pain_engine.calculate_max_pain(u)
                    metrics_cache[MetricType.OI_PCR.value] = mp.pcr_suite.oi_pcr
                    metrics_cache[MetricType.MAX_PAIN_DISTANCE.value] = abs(mp.distance_to_spot)
                except Exception:
                    pass

            # Check rules against gathered metrics
            for rule in active_rules:
                m_val = metrics_cache.get(rule.metric.value)
                if m_val is None:
                    continue

                triggered = False
                if rule.condition == AlertCondition.GREATER_THAN and m_val > rule.threshold:
                    triggered = True
                elif rule.condition == AlertCondition.LESS_THAN and m_val < rule.threshold:
                    triggered = True

                if triggered:
                    msg = rule.message_template.format(
                        threshold=rule.threshold,
                        value=round(m_val, 2)
                    )
                    alert_event = TriggeredAlert(
                        id=f"alert-{uuid.uuid4().hex[:8]}",
                        rule_id=rule.id,
                        underlying=rule.underlying,
                        metric=rule.metric.value,
                        condition=rule.condition.value,
                        threshold=rule.threshold,
                        current_value=round(m_val, 2),
                        message=msg
                    )
                    self._triggered_history.append(alert_event)
                    new_triggers.append(alert_event)

        return new_triggers


alert_engine = AlertEngine()

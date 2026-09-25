from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field
import threading

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.services.angel.instrument_master import instrument_master

class SubscriptionMode:
    LTP = 1
    QUOTE = 2
    SNAPQUOTE = 3

@dataclass
class TokenSubscription:
    token: str
    symbol: str
    exchange: str
    exchange_type: int
    mode: int
    underlying: str
    strike: Optional[float] = None
    option_type: Optional[str] = None  # "CE", "PE", "FUT", "SPOT"

class TokenManager:
    """
    Manages active market-data subscriptions:
    - Calculates ATM strike from spot/future price.
    - Resolves ATM ± N strikes (configurable window, default ±10).
    - Generates dynamic token diffs when ATM shifts (subscribes new strikes, unsubscribes obsolete strikes).
    - Manages exchangeType mapping (NSE: 1, NFO: 2, BSE: 3, BFO: 4, MCX: 5).
    - Thread-safe tracking of subscribed tokens.
    """

    EXCHANGE_TYPE_MAP = {
        "NSE": 1,
        "NSE_CM": 1,
        "NFO": 2,
        "NSE_FO": 2,
        "BSE": 3,
        "BSE_CM": 3,
        "BFO": 4,
        "BSE_FO": 4,
        "MCX": 5,
        "MCX_FO": 5,
        "CDS": 13,
    }

    def __init__(self, strike_window: int = 10):
        self.strike_window = strike_window  # ±N strikes
        self._lock = threading.RLock()
        self._active_subscriptions: Dict[str, TokenSubscription] = {}  # token -> TokenSubscription
        self._current_atm_strikes: Dict[str, float] = {}  # underlying -> current ATM strike
        self._current_expiries: Dict[str, str] = {}  # underlying -> current expiry

    def get_exchange_type(self, exchange: str) -> int:
        return self.EXCHANGE_TYPE_MAP.get(exchange.upper(), 2)

    def calculate_atm_strike(self, underlying: str, reference_price: float, expiry: str, exchange: Optional[str] = None) -> float:
        """
        Dynamically determine ATM strike by finding the strike closest to reference_price.
        Never hard-codes strike steps.
        """
        strikes = instrument_master.get_strikes(underlying, expiry, exchange)
        if not strikes:
            # Fallback mathematical rounding
            step = 100.0 if underlying in ("CRUDEOIL", "BANKNIFTY") else (50.0 if underlying == "NIFTY" else 100.0)
            return round(reference_price / step) * step

        closest_strike = min(strikes, key=lambda s: abs(s - reference_price))
        return closest_strike

    def get_strike_window_contracts(
        self,
        underlying: str,
        expiry: str,
        atm_strike: float,
        window: Optional[int] = None,
        exchange: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get option contracts for ATM ± N strikes.
        Returns list of strike dicts with strike, ce_token, pe_token, exchange, etc.
        """
        w = window if window is not None else self.strike_window
        all_strikes = instrument_master.get_strikes(underlying, expiry, exchange)
        if not all_strikes:
            return []

        try:
            atm_idx = all_strikes.index(atm_strike)
        except ValueError:
            # Pick closest
            atm_idx = min(range(len(all_strikes)), key=lambda i: abs(all_strikes[i] - atm_strike))

        start_idx = max(0, atm_idx - w)
        end_idx = min(len(all_strikes), atm_idx + w + 1)
        selected_strikes = all_strikes[start_idx:end_idx]

        results = []
        for s in selected_strikes:
            ce = instrument_master.get_option_contract(underlying, expiry, s, "CE", exchange)
            pe = instrument_master.get_option_contract(underlying, expiry, s, "PE", exchange)
            results.append({
                "strike": s,
                "ce": ce,
                "pe": pe,
                "is_atm": abs(s - atm_strike) < 0.001
            })
        return results

    def build_subscription_plan(
        self,
        underlying: str,
        expiry: str,
        reference_price: float,
        mode: int = SubscriptionMode.SNAPQUOTE,
        exchange: Optional[str] = None
    ) -> Tuple[List[TokenSubscription], float]:
        """
        Build full list of TokenSubscriptions for underlying:
        - Future / Spot token
        - ATM ± N strikes (CE and PE)
        """
        atm_strike = self.calculate_atm_strike(underlying, reference_price, expiry, exchange)
        strike_rows = self.get_strike_window_contracts(underlying, expiry, atm_strike, self.strike_window, exchange)
        
        subscriptions = []
        exch_name = exchange or ("MCX" if underlying in ("CRUDEOIL", "GOLD", "SILVER") else "NFO")
        exch_type = self.get_exchange_type(exch_name)

        # 1. Underlying Future / Spot contract
        fut_inst = instrument_master.search(f"{underlying}{expiry[:7]}FUT", limit=1)
        if fut_inst:
            f = fut_inst[0]
            subscriptions.append(TokenSubscription(
                token=f["token"],
                symbol=f["symbol"],
                exchange=f["exch_seg"],
                exchange_type=self.get_exchange_type(f["exch_seg"]),
                mode=mode,
                underlying=underlying,
                option_type="FUT"
            ))

        # 2. Strike window options (CE & PE)
        for row in strike_rows:
            ce = row.get("ce")
            if ce:
                subscriptions.append(TokenSubscription(
                    token=ce.token,
                    symbol=ce.symbol,
                    exchange=ce.exch_seg,
                    exchange_type=self.get_exchange_type(ce.exch_seg),
                    mode=mode,
                    underlying=underlying,
                    strike=row["strike"],
                    option_type="CE"
                ))
            pe = row.get("pe")
            if pe:
                subscriptions.append(TokenSubscription(
                    token=pe.token,
                    symbol=pe.symbol,
                    exchange=pe.exch_seg,
                    exchange_type=self.get_exchange_type(pe.exch_seg),
                    mode=mode,
                    underlying=underlying,
                    strike=row["strike"],
                    option_type="PE"
                ))

        return subscriptions, atm_strike

    def update_underlying_subscriptions(
        self,
        underlying: str,
        expiry: str,
        reference_price: float,
        mode: int = SubscriptionMode.SNAPQUOTE,
        exchange: Optional[str] = None
    ) -> Tuple[List[TokenSubscription], List[TokenSubscription], float]:
        """
        Evaluates current ATM vs new ATM.
        If ATM shifted or first subscription:
        - returns (to_subscribe, to_unsubscribe, new_atm)
        - updates internal state atomically.
        """
        with self._lock:
            new_subs, new_atm = self.build_subscription_plan(underlying, expiry, reference_price, mode, exchange)
            new_token_set = {s.token: s for s in new_subs}

            # Find existing tokens for this underlying
            existing_for_underlying = {
                t: sub for t, sub in self._active_subscriptions.items()
                if sub.underlying == underlying
            }

            # Tokens to subscribe: in new but not in existing
            to_subscribe = [s for t, s in new_token_set.items() if t not in existing_for_underlying]

            # Tokens to unsubscribe: in existing but not in new
            to_unsubscribe = [s for t, s in existing_for_underlying.items() if t not in new_token_set]

            # Update active subscriptions map
            for sub in to_unsubscribe:
                self._active_subscriptions.pop(sub.token, None)
            for sub in to_subscribe:
                self._active_subscriptions[sub.token] = sub

            self._current_atm_strikes[underlying] = new_atm
            self._current_expiries[underlying] = expiry

            if to_subscribe or to_unsubscribe:
                logger.info(
                    f"ATM update for {underlying} (ATM: {new_atm}): "
                    f"+{len(to_subscribe)} subscribed, -{len(to_unsubscribe)} unsubscribed. "
                    f"Total active: {len(self._active_subscriptions)}"
                )

            return to_subscribe, to_unsubscribe, new_atm

    def format_smartapi_payload(self, subscriptions: List[TokenSubscription], action: int) -> Dict[str, Any]:
        """
        Format official SmartAPI WebSocket 2.0 subscription JSON message:
        action: 1 = Subscribe, 0 = Unsubscribe
        """
        # Group by exchangeType & mode
        grouped: Dict[Tuple[int, int], List[str]] = {}
        for sub in subscriptions:
            key = (sub.exchange_type, sub.mode)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(sub.token)

        # SmartAPI allows sending tokenList grouped by exchangeType
        # E.g. {"correlationID": "sub_1", "action": 1, "params": {"mode": mode, "tokenList": [{"exchangeType": 2, "tokens": [...]}]}}
        payloads = []
        for (exch_type, mode), tokens in grouped.items():
            payloads.append({
                "correlationID": f"req_{exch_type}_{mode}_{action}",
                "action": action,
                "params": {
                    "mode": mode,
                    "tokenList": [
                        {
                            "exchangeType": exch_type,
                            "tokens": tokens
                        }
                    ]
                }
            })
        return payloads[0] if len(payloads) == 1 else {"batch": payloads}

    def get_active_tokens(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "token": s.token,
                    "symbol": s.symbol,
                    "exchange": s.exchange,
                    "exchange_type": s.exchange_type,
                    "mode": s.mode,
                    "underlying": s.underlying,
                    "strike": s.strike,
                    "option_type": s.option_type
                }
                for s in self._active_subscriptions.values()
            ]

    def get_subscription_count(self) -> int:
        with self._lock:
            return len(self._active_subscriptions)

    def clear(self):
        with self._lock:
            self._active_subscriptions.clear()
            self._current_atm_strikes.clear()
            self._current_expiries.clear()

token_manager = TokenManager()

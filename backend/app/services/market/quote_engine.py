import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict, field
import threading

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.storage.redis_client import redis_client
from backend.app.services.market.websocket_manager import MarketTick, smart_websocket_manager
from backend.app.services.angel.instrument_master import instrument_master

@dataclass
class NormalizedQuote:
    token: str
    symbol: str
    exchange: str
    ltp: float
    change: float = 0.0
    change_percent: float = 0.0
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: int = 0
    open_interest: int = 0
    oi_change: int = 0
    best_bid_price: Optional[float] = None
    best_bid_qty: Optional[int] = None
    best_ask_price: Optional[float] = None
    best_ask_qty: Optional[int] = None
    last_traded_qty: Optional[int] = None
    avg_traded_price: Optional[float] = None
    spread: Optional[float] = None
    mid_price: Optional[float] = None
    timestamp: float = field(default_factory=time.time)
    received_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_stale: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class QuoteEngine:
    """
    Real-time Quote Engine & Normalized Live State Store:
    - Maintains latest quote per instrument token in Redis with in-memory thread-safe fallback.
    - Computes change, change_percent, bid-ask spread, and mid_price.
    - Tracks Open Interest changes across successive ticks.
    - Real-time stale quote detection (configurable max age, default 15s).
    - Batch query optimization.
    """

    def __init__(self, stale_threshold_seconds: float = 15.0):
        self.stale_threshold_seconds = stale_threshold_seconds
        self._lock = threading.RLock()
        self._quotes: Dict[str, NormalizedQuote] = {}
        self._previous_oi: Dict[str, int] = {}
        self.total_ticks_processed = 0

        # Preload synthetic benchmark quotes for discovered instruments so UI / API has immediate state
        self._seed_initial_quotes()

        # Connect tick listener to SmartWebSocketManager
        smart_websocket_manager.add_tick_listener(self.on_tick)

    def on_tick(self, tick: MarketTick):
        """Process incoming live MarketTick and update normalized state."""
        self.process_tick(tick)

    def process_tick(self, tick: MarketTick) -> NormalizedQuote:
        """Normalized tick processor."""
        with self._lock:
            token = str(tick.token).strip()
            inst = instrument_master.get_instrument_by_token(token)
            symbol = inst.symbol if inst else f"TOK_{token}"
            exchange = inst.exch_seg if inst else ("MCX" if "CRUDE" in token or "GOLD" in token else "NFO")

            prev_quote = self._quotes.get(token)
            close = tick.close_price or (prev_quote.close if prev_quote else None) or tick.ltp
            change = round(tick.ltp - close, 4) if close and close > 0 else 0.0
            change_percent = round((change / close) * 100.0, 4) if close and close > 0 else 0.0

            # Bid-ask spread and mid price
            bid = tick.best_buy_price or (prev_quote.best_bid_price if prev_quote else None)
            ask = tick.best_sell_price or (prev_quote.best_ask_price if prev_quote else None)
            spread = round(ask - bid, 4) if (bid is not None and ask is not None) else None
            mid_price = round((bid + ask) / 2.0, 4) if (bid is not None and ask is not None) else tick.ltp

            # OI & OI Change
            current_oi = tick.open_interest if tick.open_interest is not None else (prev_quote.open_interest if prev_quote else 0)
            prev_oi = self._previous_oi.get(token, current_oi)
            oi_change = current_oi - prev_oi if prev_oi is not None else 0
            if tick.open_interest is not None:
                self._previous_oi[token] = tick.open_interest

            now = time.time()
            quote = NormalizedQuote(
                token=token,
                symbol=symbol,
                exchange=exchange,
                ltp=tick.ltp,
                change=change,
                change_percent=change_percent,
                open=tick.open_price or (prev_quote.open if prev_quote else None),
                high=tick.high_price or (prev_quote.high if prev_quote else None),
                low=tick.low_price or (prev_quote.low if prev_quote else None),
                close=close,
                volume=tick.volume or (prev_quote.volume if prev_quote else 0),
                open_interest=current_oi,
                oi_change=oi_change,
                best_bid_price=bid,
                best_bid_qty=tick.best_buy_qty or (prev_quote.best_bid_qty if prev_quote else None),
                best_ask_price=ask,
                best_ask_qty=tick.best_sell_qty or (prev_quote.best_ask_qty if prev_quote else None),
                last_traded_qty=tick.last_traded_qty or (prev_quote.last_traded_qty if prev_quote else None),
                avg_traded_price=tick.avg_traded_price or (prev_quote.avg_traded_price if prev_quote else None),
                spread=spread,
                mid_price=mid_price,
                timestamp=now,
                received_at=datetime.now(timezone.utc).isoformat(),
                is_stale=False
            )

            # Store in local memory and Redis
            self._quotes[token] = quote
            self.total_ticks_processed += 1
            redis_client.set(f"quote:{token}", quote.to_dict())

            return quote

    def get_quote(self, token: str, max_age_seconds: Optional[float] = None) -> Optional[NormalizedQuote]:
        """Fetch quote for token, automatically detecting staleness."""
        token = str(token).strip()
        threshold = max_age_seconds if max_age_seconds is not None else self.stale_threshold_seconds

        with self._lock:
            quote = self._quotes.get(token)

            # If not in memory, check Redis
            if not quote:
                cached = redis_client.get(f"quote:{token}")
                if cached and isinstance(cached, dict):
                    quote = NormalizedQuote(**cached)
                    self._quotes[token] = quote

            if not quote:
                return None

            # Calculate staleness dynamically
            age = time.time() - quote.timestamp
            quote.is_stale = (age > threshold)
            return quote

    def get_quotes_batch(self, tokens: List[str], max_age_seconds: Optional[float] = None) -> Dict[str, Optional[Dict[str, Any]]]:
        """High-efficiency batch retrieval of quotes."""
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        for token in tokens:
            q = self.get_quote(token, max_age_seconds)
            results[token] = q.to_dict() if q else None
        return results

    def get_underlying_quote(self, underlying: str) -> Optional[NormalizedQuote]:
        """Look up latest quote for underlying future / spot."""
        u = underlying.strip().upper()
        # Look for matching token
        for q in self._quotes.values():
            if q.symbol.startswith(u) and ("FUT" in q.symbol or q.symbol == u):
                return q
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Return Quote Engine health and metrics."""
        with self._lock:
            now = time.time()
            total = len(self._quotes)
            stale_count = sum(1 for q in self._quotes.values() if (now - q.timestamp) > self.stale_threshold_seconds)
            return {
                "total_cached_quotes": total,
                "stale_quotes_count": stale_count,
                "fresh_quotes_count": total - stale_count,
                "total_ticks_processed": self.total_ticks_processed,
                "stale_threshold_seconds": self.stale_threshold_seconds,
            }

    def _seed_initial_quotes(self):
        """Seed realistic initial quotes for active underlyings and ATM options."""
        now = time.time()
        # Seed MCX CRUDEOIL
        self._quotes["MCX_CRUDE_FUT"] = NormalizedQuote(
            token="MCX_CRUDE_FUT",
            symbol="CRUDEOIL19FEB26FUT",
            exchange="MCX",
            ltp=8908.0,
            change=83.0,
            change_percent=0.94,
            open=8825.0,
            high=8934.0,
            low=8801.0,
            close=8825.0,
            volume=354200,
            open_interest=14520,
            oi_change=340,
            best_bid_price=8907.0,
            best_bid_qty=100,
            best_ask_price=8908.0,
            best_ask_qty=100,
            spread=1.0,
            mid_price=8907.5,
            timestamp=now
        )
        # Seed ATM Options: 8800, 8900, 9000
        self._quotes["MCX_CRUDE_8900_CE"] = NormalizedQuote(
            token="MCX_CRUDE_8900_CE",
            symbol="CRUDEOIL19FEB268900CE",
            exchange="MCX",
            ltp=498.0,
            change=53.5,
            change_percent=12.04,
            close=444.5,
            volume=457200,
            open_interest=176500,
            oi_change=100,
            best_bid_price=495.5,
            best_bid_qty=400,
            best_ask_price=496.7,
            best_ask_qty=100,
            spread=1.2,
            mid_price=496.1,
            timestamp=now
        )
        self._quotes["MCX_CRUDE_8900_PE"] = NormalizedQuote(
            token="MCX_CRUDE_8900_PE",
            symbol="CRUDEOIL19FEB268900PE",
            exchange="MCX",
            ltp=486.5,
            change=-30.4,
            change_percent=-5.88,
            close=516.9,
            volume=498000,
            open_interest=421000,
            oi_change=3100,
            best_bid_price=487.6,
            best_bid_qty=100,
            best_ask_price=489.0,
            best_ask_qty=400,
            spread=1.4,
            mid_price=488.3,
            timestamp=now
        )
        # Seed NIFTY
        self._quotes["26000"] = NormalizedQuote(
            token="26000",
            symbol="NIFTY26MAR26FUT",
            exchange="NFO",
            ltp=23045.50,
            change=124.50,
            change_percent=0.54,
            open=22950.0,
            high=23080.0,
            low=22910.0,
            close=22921.0,
            volume=854000,
            open_interest=12500000,
            oi_change=450000,
            best_bid_price=23045.0,
            best_bid_qty=125,
            best_ask_price=23046.0,
            best_ask_qty=175,
            spread=1.0,
            mid_price=23045.5,
            timestamp=now
        )

quote_engine = QuoteEngine()

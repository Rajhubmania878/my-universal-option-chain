import asyncio
import json
import struct
import time
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, asdict

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.services.angel.auth import angel_auth_manager
from backend.app.services.market.token_manager import token_manager, SubscriptionMode, TokenSubscription

try:
    import websockets
except ImportError:
    websockets = None

@dataclass
class MarketTick:
    token: str
    exchange_type: int
    subscription_mode: int
    sequence_number: int
    exchange_timestamp: int
    ltp: float
    last_traded_qty: Optional[int] = None
    avg_traded_price: Optional[float] = None
    volume: Optional[int] = None
    total_buy_qty: Optional[int] = None
    total_sell_qty: Optional[int] = None
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    close_price: Optional[float] = None
    open_interest: Optional[int] = None
    best_buy_price: Optional[float] = None
    best_buy_qty: Optional[int] = None
    best_sell_price: Optional[float] = None
    best_sell_qty: Optional[int] = None
    received_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SmartWebSocketManager:
    """
    Angel One SmartAPI WebSocket 2.0 Streaming Client:
    - Non-blocking async packet receiver
    - Little-endian binary unpacking (Modes: 1 LTP, 2 Quote, 3 Snapquote)
    - Heartbeat ping-pong (30s)
    - Exponential backoff reconnection
    - Automatic resubscription on reconnect
    - High-throughput async tick queue
    """

    SMART_STREAM_URL = "wss://smartapisocket.angelone.in/smart-stream"

    def __init__(self, auth_manager=angel_auth_manager, tokens=token_manager):
        self.auth_manager = auth_manager
        self.token_manager = tokens
        self.tick_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        
        self._ws = None
        self._running = False
        self._listen_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        
        # Diagnostics
        self.is_connected = False
        self.reconnect_count = 0
        self.ticks_received = 0
        self.last_tick_time: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.connection_start_time: Optional[datetime] = None
        self._tick_listeners: List[Callable[[MarketTick], None]] = []

    def add_tick_listener(self, listener: Callable[[MarketTick], None]):
        """Register a synchronous or asynchronous callback for tick processing."""
        self._tick_listeners.append(listener)

    def parse_binary_tick(self, data: bytes) -> Optional[MarketTick]:
        """
        Unpacks official Angel One SmartStream binary packet (Little Endian '<'):
        - Mode 1 (LTP): 51 bytes
        - Mode 2 (Quote): 123 bytes
        - Mode 3 (SnapQuote): 131+ bytes (including Open Interest and depth)
        """
        if len(data) < 51:
            return None

        try:
            # Header: Mode (1B), Exchange (1B), Token (25s)
            sub_mode, exch_type = struct.unpack_from("<BB", data, 0)
            raw_token = struct.unpack_from("<25s", data, 2)[0]
            token = raw_token.decode("utf-8", errors="ignore").rstrip("\x00").strip()

            # Sequence Number (8B 'q'), Timestamp (8B 'q'), LTP (8B 'q' in paise)
            seq_no, ts, raw_ltp = struct.unpack_from("<qqq", data, 27)
            ltp = raw_ltp / 100.0

            tick = MarketTick(
                token=token,
                exchange_type=exch_type,
                subscription_mode=sub_mode,
                sequence_number=seq_no,
                exchange_timestamp=ts,
                ltp=ltp,
                received_at=datetime.utcnow().isoformat()
            )

            # Mode 2: Quote (min 123 bytes)
            if sub_mode in (SubscriptionMode.QUOTE, SubscriptionMode.SNAPQUOTE) and len(data) >= 123:
                (
                    ltq, raw_atp, vol,
                    total_buy, total_sell,
                    raw_open, raw_high, raw_low, raw_close
                ) = struct.unpack_from("<qqqqqqqqq", data, 51)

                tick.last_traded_qty = ltq
                tick.avg_traded_price = raw_atp / 100.0
                tick.volume = vol
                tick.total_buy_qty = total_buy
                tick.total_sell_qty = total_sell
                tick.open_price = raw_open / 100.0
                tick.high_price = raw_high / 100.0
                tick.low_price = raw_low / 100.0
                tick.close_price = raw_close / 100.0

            # Mode 3: Snapquote (min 131 bytes, carries Open Interest)
            if sub_mode == SubscriptionMode.SNAPQUOTE and len(data) >= 131:
                raw_oi = struct.unpack_from("<q", data, 123)[0]
                tick.open_interest = raw_oi

                # Best Bid & Ask depth parsing if available
                if len(data) >= 171:
                    try:
                        # Depth Buy: 20 bytes (qty, price, orders)
                        b_qty, b_price = struct.unpack_from("<qq", data, 131)
                        tick.best_buy_qty = b_qty
                        tick.best_buy_price = b_price / 100.0
                        # Depth Sell: 20 bytes
                        s_qty, s_price = struct.unpack_from("<qq", data, 151)
                        tick.best_sell_qty = s_qty
                        tick.best_sell_price = s_price / 100.0
                    except struct.error:
                        pass

            return tick
        except Exception as exc:
            logger.debug(f"Error unpacking binary tick: {exc}")
            return None

    def parse_json_tick(self, text: str) -> Optional[MarketTick]:
        """Parse text/JSON ticks or connection status payloads."""
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                return None
            
            # SmartAPI JSON format
            token = str(data.get("tk") or data.get("token") or "")
            if not token:
                return None

            ltp = float(data.get("ltp", 0.0) or data.get("lp", 0.0))
            return MarketTick(
                token=token,
                exchange_type=int(data.get("e", 2)),
                subscription_mode=int(data.get("mode", 1)),
                sequence_number=int(data.get("sq", 0)),
                exchange_timestamp=int(data.get("ft", int(time.time() * 1000))),
                ltp=ltp,
                open_interest=int(data.get("oi", 0)) if "oi" in data else None,
                volume=int(data.get("v", 0)) if "v" in data else None,
                received_at=datetime.utcnow().isoformat()
            )
        except Exception:
            return None

    async def _handle_incoming_raw(self, message: Any):
        """Dispatch incoming raw message immediately into non-blocking queue."""
        tick = None
        if isinstance(message, bytes):
            tick = self.parse_binary_tick(message)
        elif isinstance(message, str):
            if message.strip() == "pong":
                return
            tick = self.parse_json_tick(message)

        if tick:
            self.ticks_received += 1
            self.last_tick_time = datetime.utcnow()
            
            # Non-blocking enqueue (drops oldest if full to avoid backpressure)
            if self.tick_queue.full():
                try:
                    self.tick_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await self.tick_queue.put(tick)

            # Fire listeners
            for listener in self._tick_listeners:
                try:
                    res = listener(tick)
                    if asyncio.iscoroutine(res):
                        asyncio.create_task(res)
                except Exception as e:
                    logger.debug(f"Error in tick listener: {e}")

    async def connect_and_run(self):
        """
        Main streaming loop with exponential backoff and auto-resubscription.
        """
        self._running = True
        backoff = 1.0
        max_backoff = 30.0

        while self._running:
            jwt = self.auth_manager.get_jwt_token()
            feed_token = self.auth_manager.get_feed_token()

            if not jwt or not feed_token:
                logger.warning("Waiting for valid Angel One JWT / feed token before connecting WebSocket...")
                await asyncio.sleep(5)
                continue

            headers = {
                "Authorization": f"Bearer {jwt}",
                "x-api-key": settings.ANGEL_API_KEY,
                "x-client-code": settings.ANGEL_CLIENT_CODE,
                "x-feed-token": feed_token,
            }

            try:
                if websockets is None:
                    # In test/standalone environment, run internal tick simulation loop
                    logger.info("websockets library not installed or running in standalone simulation mode.")
                    self.is_connected = True
                    self.connection_start_time = datetime.utcnow()
                    await self._simulate_stream()
                    break

                logger.info(f"Connecting to Angel One SmartStream: {self.SMART_STREAM_URL}...")
                async with websockets.connect(
                    self.SMART_STREAM_URL,
                    extra_headers=headers,
                    ping_interval=None  # We control heartbeats manually
                ) as ws:
                    self._ws = ws
                    self.is_connected = True
                    self.connection_start_time = datetime.utcnow()
                    backoff = 1.0  # Reset backoff on successful handshake
                    logger.info("Connected to Angel One SmartStream WebSocket.")

                    # Auto-resubscribe all active tokens
                    await self.resubscribe_active_tokens()

                    # Start heartbeat task
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                    # Stream listener loop
                    while self._running:
                        msg = await ws.recv()
                        await self._handle_incoming_raw(msg)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.is_connected = False
                self.reconnect_count += 1
                self.last_error = str(exc)
                logger.warning(f"SmartStream disconnected ({exc}). Reconnecting in {backoff:.1f}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, max_backoff)

        self.is_connected = False
        logger.info("SmartStream loop terminated.")

    async def _heartbeat_loop(self):
        """Send ping every 30 seconds."""
        while self.is_connected and self._running and self._ws:
            try:
                await asyncio.sleep(30)
                if self._ws and self.is_connected:
                    await self._ws.send("ping")
            except Exception:
                break

    async def subscribe(self, subscriptions: List[TokenSubscription]):
        """Send subscription request to active WebSocket."""
        if not subscriptions or not self.is_connected or not self._ws:
            return

        payload = self.token_manager.format_smartapi_payload(subscriptions, action=1)
        if "batch" in payload:
            for p in payload["batch"]:
                await self._ws.send(json.dumps(p))
        else:
            await self._ws.send(json.dumps(payload))
        logger.info(f"Subscribed to {len(subscriptions)} tokens on SmartStream.")

    async def unsubscribe(self, subscriptions: List[TokenSubscription]):
        """Send unsubscribe request to active WebSocket."""
        if not subscriptions or not self.is_connected or not self._ws:
            return

        payload = self.token_manager.format_smartapi_payload(subscriptions, action=0)
        if "batch" in payload:
            for p in payload["batch"]:
                await self._ws.send(json.dumps(p))
        else:
            await self._ws.send(json.dumps(payload))
        logger.info(f"Unsubscribed from {len(subscriptions)} tokens on SmartStream.")

    async def resubscribe_active_tokens(self):
        """Resubscribe all tokens tracked in TokenManager upon reconnection."""
        active = self.token_manager._active_subscriptions.values()
        if active:
            await self.subscribe(list(active))

    async def _simulate_stream(self):
        """Generates realistic synthetic ticks when running in standalone mode."""
        while self._running:
            # Pull tokens from TokenManager
            tokens = list(self.token_manager._active_subscriptions.keys())
            if tokens:
                for tok in tokens[:5]:
                    sim_tick = MarketTick(
                        token=tok,
                        exchange_type=2,
                        subscription_mode=3,
                        sequence_number=self.ticks_received + 1,
                        exchange_timestamp=int(time.time() * 1000),
                        ltp=450.0 + (self.ticks_received % 20),
                        volume=15000 + self.ticks_received,
                        open_interest=250000,
                        received_at=datetime.utcnow().isoformat()
                    )
                    await self._handle_incoming_raw(json.dumps(sim_tick.to_dict()))
            await asyncio.sleep(1)

    def stop(self):
        self._running = False
        self.is_connected = False
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()

    def get_status(self) -> Dict[str, Any]:
        return {
            "connected": self.is_connected,
            "reconnect_count": self.reconnect_count,
            "ticks_received": self.ticks_received,
            "last_tick_time": self.last_tick_time.isoformat() if self.last_tick_time else None,
            "queue_size": self.tick_queue.qsize(),
            "active_subscriptions": self.token_manager.get_subscription_count(),
            "last_error": self.last_error,
        }

smart_websocket_manager = SmartWebSocketManager()

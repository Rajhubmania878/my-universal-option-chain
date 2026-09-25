import asyncio
from typing import Optional, List
from datetime import datetime

from backend.app.core.logging import logger
from backend.app.services.market.websocket_manager import smart_websocket_manager, MarketTick
from backend.app.storage.redis_client import redis_client

class MarketDataWorker:
    """
    Background worker that ingests market ticks from the non-blocking WebSocket queue
    and persists the latest state into Redis / memory.
    """

    def __init__(self, batch_size: int = 100, flush_interval_ms: int = 50):
        self.batch_size = batch_size
        self.flush_interval = flush_interval_ms / 1000.0
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.ticks_processed = 0
        self.last_flush_time: Optional[datetime] = None

    async def start(self):
        if self._running:
            return
        self._running = True
        logger.info("Starting MarketDataWorker tick processing loop...")
        self._task = asyncio.create_task(self._process_queue())

    async def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MarketDataWorker stopped.")

    async def _process_queue(self):
        batch: List[MarketTick] = []
        while self._running:
            try:
                # Wait for at least one tick
                try:
                    tick = await asyncio.wait_for(smart_websocket_manager.tick_queue.get(), timeout=self.flush_interval)
                    batch.append(tick)
                    smart_websocket_manager.tick_queue.task_done()
                except asyncio.TimeoutError:
                    pass

                # Drain additional available items up to batch_size
                while len(batch) < self.batch_size:
                    try:
                        tick = smart_websocket_manager.tick_queue.get_nowait()
                        batch.append(tick)
                        smart_websocket_manager.tick_queue.task_done()
                    except asyncio.QueueEmpty:
                        break

                # Flush batch to Redis / cache
                if batch:
                    for t in batch:
                        redis_client.set(f"quote:{t.token}", t.to_dict())
                        if t.open_interest is not None:
                            redis_client.set(f"oi:{t.token}", t.open_interest)
                    self.ticks_processed += len(batch)
                    self.last_flush_time = datetime.utcnow()
                    batch.clear()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in MarketDataWorker loop: {e}")
                await asyncio.sleep(0.1)

market_data_worker = MarketDataWorker()

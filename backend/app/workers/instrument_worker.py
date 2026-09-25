import asyncio
from datetime import datetime, time
from typing import Optional

from backend.app.core.logging import logger
from backend.app.services.angel.instrument_master import instrument_master

class InstrumentWorker:
    """
    Background worker that schedules periodic downloads of Angel One's OpenAPIScripMaster.
    Typically runs once per day before market opening (e.g. 08:30 IST) or periodically.
    """

    def __init__(self, refresh_interval_hours: int = 24):
        self.refresh_interval_seconds = refresh_interval_hours * 3600
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.last_run_time: Optional[datetime] = None
        self.last_error: Optional[str] = None

    async def start(self):
        """Start the background refresh loop."""
        if self._running:
            return
        self._running = True
        logger.info("Starting Instrument Master background refresh worker...")
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        """Stop the background refresh worker."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Instrument Master worker stopped.")

    async def refresh_once(self) -> int:
        """Execute a single download and indexing cycle asynchronously."""
        try:
            # Run in executor to avoid blocking the asyncio event loop
            loop = asyncio.get_running_loop()
            count = await loop.run_in_executor(None, instrument_master.load_from_url)
            self.last_run_time = datetime.utcnow()
            self.last_error = None
            logger.info(f"Instrument worker successfully refreshed master ({count} instruments).")
            return count
        except Exception as exc:
            self.last_error = str(exc)
            logger.error(f"Error during instrument refresh: {exc}")
            return instrument_master.total_instruments

    async def _run_loop(self):
        while self._running:
            try:
                await self.refresh_once()
                # Wait for the next refresh interval
                await asyncio.sleep(self.refresh_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"InstrumentWorker loop exception: {e}")
                await asyncio.sleep(60)

instrument_worker = InstrumentWorker()

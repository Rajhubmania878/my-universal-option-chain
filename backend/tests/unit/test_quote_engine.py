import unittest
import time
from backend.app.services.market.websocket_manager import MarketTick
from backend.app.services.market.quote_engine import QuoteEngine, NormalizedQuote

class TestQuoteEngine(unittest.TestCase):
    def setUp(self):
        # Create an isolated QuoteEngine with small stale threshold
        self.engine = QuoteEngine(stale_threshold_seconds=1.0)

    def test_initial_seeded_quotes(self):
        crude_fut = self.engine.get_quote("MCX_CRUDE_FUT")
        self.assertIsNotNone(crude_fut)
        self.assertEqual(crude_fut.symbol, "CRUDEOIL19FEB26FUT")
        self.assertEqual(crude_fut.ltp, 8908.0)
        self.assertEqual(crude_fut.exchange, "MCX")
        self.assertAlmostEqual(crude_fut.spread, 1.0)
        self.assertAlmostEqual(crude_fut.mid_price, 8907.5)

    def test_process_tick_and_calculations(self):
        # Tick with LTP = 9000, Close = 8900
        tick = MarketTick(
            token="TEST_CRUDE_9000",
            exchange_type=5,
            subscription_mode=3,
            sequence_number=1,
            exchange_timestamp=int(time.time() * 1000),
            ltp=9000.0,
            close_price=8900.0,
            open_price=8910.0,
            high_price=9020.0,
            low_price=8890.0,
            volume=50000,
            open_interest=10000,
            best_buy_price=8998.0,
            best_buy_qty=50,
            best_sell_price=9002.0,
            best_sell_qty=75,
            last_traded_qty=10,
            avg_traded_price=8950.0
        )
        quote = self.engine.process_tick(tick)
        
        self.assertEqual(quote.token, "TEST_CRUDE_9000")
        self.assertEqual(quote.ltp, 9000.0)
        self.assertEqual(quote.change, 100.0)
        self.assertAlmostEqual(quote.change_percent, 1.1236, places=3)
        self.assertEqual(quote.spread, 4.0)
        self.assertEqual(quote.mid_price, 9000.0)
        self.assertEqual(quote.open_interest, 10000)
        self.assertEqual(quote.volume, 50000)
        self.assertFalse(quote.is_stale)

    def test_oi_change_tracking(self):
        # First tick OI = 10,000
        tick1 = MarketTick(
            token="OI_TEST_TOKEN",
            exchange_type=2,
            subscription_mode=3,
            sequence_number=1,
            exchange_timestamp=int(time.time() * 1000),
            ltp=500.0,
            close_price=490.0,
            open_interest=10000
        )
        q1 = self.engine.process_tick(tick1)
        self.assertEqual(q1.open_interest, 10000)
        self.assertEqual(q1.oi_change, 0)

        # Second tick OI rises to 12,500
        tick2 = MarketTick(
            token="OI_TEST_TOKEN",
            exchange_type=2,
            subscription_mode=3,
            sequence_number=2,
            exchange_timestamp=int(time.time() * 1000) + 1000,
            ltp=505.0,
            close_price=490.0,
            open_interest=12500
        )
        q2 = self.engine.process_tick(tick2)
        self.assertEqual(q2.open_interest, 12500)
        self.assertEqual(q2.oi_change, 2500)

    def test_stale_quote_detection(self):
        tick = MarketTick(
            token="STALE_TOKEN",
            exchange_type=2,
            subscription_mode=1,
            sequence_number=1,
            exchange_timestamp=int(time.time() * 1000),
            ltp=150.0,
            close_price=150.0
        )
        self.engine.process_tick(tick)
        
        # Fresh right now
        q_fresh = self.engine.get_quote("STALE_TOKEN", max_age_seconds=1.0)
        self.assertIsNotNone(q_fresh)
        self.assertFalse(q_fresh.is_stale)

        # Artificially age timestamp
        with self.engine._lock:
            self.engine._quotes["STALE_TOKEN"].timestamp = time.time() - 5.0

        q_stale = self.engine.get_quote("STALE_TOKEN", max_age_seconds=1.0)
        self.assertIsNotNone(q_stale)
        self.assertTrue(q_stale.is_stale)

    def test_batch_quotes_query(self):
        batch = self.engine.get_quotes_batch(["MCX_CRUDE_FUT", "26000", "NON_EXISTENT_TOKEN"])
        self.assertEqual(len(batch), 3)
        self.assertIsNotNone(batch["MCX_CRUDE_FUT"])
        self.assertEqual(batch["MCX_CRUDE_FUT"]["symbol"], "CRUDEOIL19FEB26FUT")
        self.assertIsNotNone(batch["26000"])
        self.assertEqual(batch["26000"]["symbol"], "NIFTY26MAR26FUT")
        self.assertIsNone(batch["NON_EXISTENT_TOKEN"])

    def test_underlying_quote_lookup(self):
        crude = self.engine.get_underlying_quote("CRUDEOIL")
        self.assertIsNotNone(crude)
        self.assertIn("CRUDEOIL", crude.symbol)

        nifty = self.engine.get_underlying_quote("NIFTY")
        self.assertIsNotNone(nifty)
        self.assertIn("NIFTY", nifty.symbol)

        missing = self.engine.get_underlying_quote("UNKNOWN_STOCK")
        self.assertIsNone(missing)

    def test_quote_engine_stats(self):
        stats = self.engine.get_stats()
        self.assertIn("total_cached_quotes", stats)
        self.assertIn("stale_quotes_count", stats)
        self.assertIn("fresh_quotes_count", stats)
        self.assertIn("total_ticks_processed", stats)
        self.assertTrue(stats["total_cached_quotes"] >= 4)

if __name__ == "__main__":
    unittest.main()

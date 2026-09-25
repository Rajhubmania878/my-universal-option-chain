import unittest
import struct
import json
import asyncio
from backend.app.services.market.token_manager import TokenManager, SubscriptionMode
from backend.app.services.market.websocket_manager import SmartWebSocketManager, MarketTick

class TestTokenAndWebSocket(unittest.TestCase):
    def setUp(self):
        self.token_mgr = TokenManager(strike_window=3)
        self.ws_mgr = SmartWebSocketManager(tokens=self.token_mgr)

    def test_calculate_atm_strike(self):
        # NIFTY near 23045 should pick 23000
        atm_nifty = self.token_mgr.calculate_atm_strike("NIFTY", 23045.0, "26MAR2026", "NFO")
        self.assertEqual(atm_nifty, 23000.0)

        # CRUDEOIL near 8920 should pick 8900
        atm_crude = self.token_mgr.calculate_atm_strike("CRUDEOIL", 8920.0, "19FEB2026", "MCX")
        self.assertEqual(atm_crude, 8900.0)

    def test_strike_window_contracts(self):
        contracts = self.token_mgr.get_strike_window_contracts("NIFTY", "26MAR2026", 23000.0, window=2, exchange="NFO")
        # ATM ± 2 strikes = up to 5 strikes
        self.assertTrue(len(contracts) <= 5)
        atm_row = next((c for c in contracts if c["is_atm"]), None)
        self.assertIsNotNone(atm_row)
        self.assertEqual(atm_row["strike"], 23000.0)
        self.assertIsNotNone(atm_row["ce"])
        self.assertIsNotNone(atm_row["pe"])

    def test_dynamic_token_replacement_on_atm_shift(self):
        # 1. Initial subscription at 23000
        to_sub1, to_unsub1, atm1 = self.token_mgr.update_underlying_subscriptions(
            underlying="NIFTY",
            expiry="26MAR2026",
            reference_price=23000.0,
            mode=SubscriptionMode.SNAPQUOTE,
            exchange="NFO"
        )
        self.assertEqual(atm1, 23000.0)
        self.assertTrue(len(to_sub1) > 0)
        self.assertEqual(len(to_unsub1), 0)
        initial_count = self.token_mgr.get_subscription_count()

        # 2. Market moves up: reference price 23600 -> ATM shifts
        to_sub2, to_unsub2, atm2 = self.token_mgr.update_underlying_subscriptions(
            underlying="NIFTY",
            expiry="26MAR2026",
            reference_price=23600.0,
            mode=SubscriptionMode.SNAPQUOTE,
            exchange="NFO"
        )
        self.assertEqual(atm2, 23600.0)
        # Should unsubscribe lower strikes and subscribe higher strikes
        self.assertTrue(len(to_sub2) > 0)
        self.assertTrue(len(to_unsub2) > 0)

    def test_binary_tick_parsing_mode_1_ltp(self):
        # Pack 51-byte packet:
        # sub_mode (1B)=1, exch_type (1B)=2, token (25s)='35003', seq (8B)=101, ts (8B)=1711440000000, ltp (8B)=2305000 (23050.00)
        raw_token = b"35003" + b"\x00" * 20
        packet = struct.pack("<BB25sqqq", 1, 2, raw_token, 101, 1711440000000, 2305000)
        
        self.assertEqual(len(packet), 51)
        tick = self.ws_mgr.parse_binary_tick(packet)
        self.assertIsNotNone(tick)
        self.assertEqual(tick.token, "35003")
        self.assertEqual(tick.exchange_type, 2)
        self.assertEqual(tick.subscription_mode, 1)
        self.assertEqual(tick.sequence_number, 101)
        self.assertEqual(tick.ltp, 23050.0)

    def test_binary_tick_parsing_mode_2_quote(self):
        raw_token = b"MCX_CRUDE_8900" + b"\x00" * 11
        # Header (51 bytes) + Quote (72 bytes: 9 * 8) = 123 bytes
        # 2 B + 1 25s + 12 q = 15 items
        packet = struct.pack(
            "<BB25sqqqqqqqqqqqq",
            2, 5, raw_token, 505, 1711440000000, 891000,  # ltp = 8910.0
            100, 890500, 150000, 25000, 30000,           # ltq, atp, vol, buy_qty, sell_qty
            885000, 895000, 882000, 884000              # open, high, low, close
        )
        self.assertEqual(len(packet), 123)
        tick = self.ws_mgr.parse_binary_tick(packet)
        self.assertIsNotNone(tick)
        self.assertEqual(tick.token, "MCX_CRUDE_8900")
        self.assertEqual(tick.ltp, 8910.0)
        self.assertEqual(tick.avg_traded_price, 8905.0)
        self.assertEqual(tick.volume, 150000)
        self.assertEqual(tick.open_price, 8850.0)
        self.assertEqual(tick.high_price, 8950.0)

    def test_binary_tick_parsing_mode_3_snapquote(self):
        raw_token = b"26000" + b"\x00" * 20
        # Header (51B) + Quote (72B) + OI (8B) = 131 bytes
        # 2 B + 1 25s + 13 q = 16 items
        packet = struct.pack(
            "<BB25sqqqqqqqqqqqqq",
            3, 2, raw_token, 808, 1711440000000, 2310000,
            25, 2309000, 500000, 120000, 110000,
            2300000, 2315000, 2298000, 2302000,
            1250000  # open interest
        )
        self.assertEqual(len(packet), 131)
        tick = self.ws_mgr.parse_binary_tick(packet)
        self.assertIsNotNone(tick)
        self.assertEqual(tick.token, "26000")
        self.assertEqual(tick.subscription_mode, 3)
        self.assertEqual(tick.open_interest, 1250000)

    def test_json_tick_parsing(self):
        raw_json = json.dumps({
            "tk": "35003",
            "e": 2,
            "mode": 1,
            "ltp": 498.5,
            "oi": 176500,
            "v": 457200
        })
        tick = self.ws_mgr.parse_json_tick(raw_json)
        self.assertIsNotNone(tick)
        self.assertEqual(tick.token, "35003")
        self.assertEqual(tick.ltp, 498.5)
        self.assertEqual(tick.open_interest, 176500)

    def test_smartapi_subscription_payload_format(self):
        subs, _ = self.token_mgr.build_subscription_plan("NIFTY", "26MAR2026", 23000.0, mode=SubscriptionMode.SNAPQUOTE, exchange="NFO")
        payload = self.token_mgr.format_smartapi_payload(subs, action=1)
        
        self.assertIn("action", payload)
        self.assertEqual(payload["action"], 1)
        self.assertIn("params", payload)
        self.assertEqual(payload["params"]["mode"], SubscriptionMode.SNAPQUOTE)
        self.assertTrue(len(payload["params"]["tokenList"]) > 0)
        self.assertEqual(payload["params"]["tokenList"][0]["exchangeType"], 2)

    def test_non_blocking_tick_queue(self):
        async def run_queue_test():
            tick = MarketTick(
                token="TEST_TOK",
                exchange_type=2,
                subscription_mode=1,
                sequence_number=1,
                exchange_timestamp=1711440000000,
                ltp=500.0
            )
            await self.ws_mgr.tick_queue.put(tick)
            retrieved = await self.ws_mgr.tick_queue.get()
            self.assertEqual(retrieved.token, "TEST_TOK")
            self.assertEqual(retrieved.ltp, 500.0)

        asyncio.run(run_queue_test())

if __name__ == "__main__":
    unittest.main()

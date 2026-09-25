import unittest
import time
from backend.app.services.storage.snapshot_engine import SnapshotIngestionEngine, OptionChainSnapshot

class TestSnapshotEngine(unittest.TestCase):
    def setUp(self):
        self.engine = SnapshotIngestionEngine(max_snapshots_per_underlying=20)

    def test_seeded_intraday_snapshots(self):
        timeline = self.engine.get_timeline("CRUDEOIL")
        self.assertGreaterEqual(len(timeline), 8)
        self.assertEqual(timeline[0]["underlying"], "CRUDEOIL")
        self.assertIn("spot_price", timeline[0])
        self.assertIn("pcr_oi", timeline[0])
        self.assertIn("atm_straddle_premium", timeline[0])

        # Timestamps should be strictly ascending
        for i in range(1, len(timeline)):
            self.assertGreaterEqual(timeline[i]["timestamp"], timeline[i - 1]["timestamp"])

    def test_get_snapshot_by_id(self):
        timeline = self.engine.get_timeline("CRUDEOIL")
        first_id = timeline[0]["snapshot_id"]

        snap = self.engine.get_snapshot_by_id("CRUDEOIL", first_id)
        self.assertIsNotNone(snap)
        self.assertEqual(snap["snapshot_id"], first_id)
        self.assertIn("strikes", snap)
        self.assertGreater(len(snap["strikes"]), 3)
        self.assertIn("ce", snap["strikes"][0])
        self.assertIn("pe", snap["strikes"][0])

    def test_capture_snapshot(self):
        strikes_mock = [
            {"strike": 8800.0, "ce": {"oi": 5000, "ltp": 240.0, "iv": 20.0}, "pe": {"oi": 4000, "ltp": 120.0, "iv": 20.0}},
            {"strike": 8900.0, "ce": {"oi": 15000, "ltp": 180.0, "iv": 19.5}, "pe": {"oi": 16000, "ltp": 180.0, "iv": 19.5}}
        ]
        snap = self.engine.capture_snapshot(
            underlying="CRUDEOIL",
            spot_price=8910.0,
            strikes_data=strikes_mock,
            pcr_oi=1.05,
            atm_straddle_premium=360.0
        )
        self.assertEqual(snap.underlying, "CRUDEOIL")
        self.assertEqual(snap.spot_price, 8910.0)
        self.assertEqual(snap.total_ce_oi, 20000)
        self.assertEqual(snap.total_pe_oi, 20000)

    def test_compare_snapshots_deltas(self):
        timeline = self.engine.get_timeline("CRUDEOIL")
        base_id = timeline[0]["snapshot_id"] # 09:15
        target_id = timeline[-1]["snapshot_id"] # 15:15

        comparison = self.engine.compare_snapshots("CRUDEOIL", base_id, target_id)
        self.assertEqual(comparison["underlying"], "CRUDEOIL")
        self.assertIn("spot_shift", comparison)
        self.assertIn("pcr_shift", comparison)
        self.assertIn("straddle_decay", comparison)

        deltas = comparison["deltas"]
        self.assertGreater(len(deltas), 0)
        # Spot increased from 8840 to 8908 (+68)
        self.assertAlmostEqual(comparison["spot_shift"], 68.0, delta=5.0)
        # Straddle decayed across the day
        self.assertLess(comparison["straddle_decay"], 0)

    def test_get_snapshot_at_or_before(self):
        timeline = self.engine.get_timeline("CRUDEOIL")
        mid_time = timeline[3]["timestamp"] + 10.0 # Just after index 3

        snap = self.engine.get_snapshot_at_or_before("CRUDEOIL", mid_time)
        self.assertIsNotNone(snap)
        self.assertEqual(snap["snapshot_id"], timeline[3]["snapshot_id"])

if __name__ == "__main__":
    unittest.main()

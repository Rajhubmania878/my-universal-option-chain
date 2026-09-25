import unittest
import asyncio
from backend.app.api.routes.snapshots import (
    get_snapshots_timeline,
    get_snapshot_detail,
    compare_snapshots_endpoint,
    capture_snapshot_endpoint,
    CaptureSnapshotRequest
)

class TestSnapshotRoutes(unittest.TestCase):
    def test_get_timeline_route(self):
        res = asyncio.run(get_snapshots_timeline(underlying="CRUDEOIL"))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["underlying"], "CRUDEOIL")
        self.assertGreaterEqual(res["count"], 5)
        self.assertIn("market_time", res["data"][0])

    def test_get_detail_route(self):
        tl = asyncio.run(get_snapshots_timeline(underlying="CRUDEOIL"))
        snap_id = tl["data"][0]["snapshot_id"]

        detail = asyncio.run(get_snapshot_detail(snapshot_id=snap_id, underlying="CRUDEOIL"))
        self.assertEqual(detail["status"], "success")
        self.assertEqual(detail["data"]["snapshot_id"], snap_id)
        self.assertIn("strikes", detail["data"])

    def test_compare_snapshots_route(self):
        tl = asyncio.run(get_snapshots_timeline(underlying="CRUDEOIL"))
        base_id = tl["data"][0]["snapshot_id"]
        tgt_id = tl["data"][-1]["snapshot_id"]

        comp = asyncio.run(compare_snapshots_endpoint(
            baseline_id=base_id,
            target_id=tgt_id,
            underlying="CRUDEOIL"
        ))
        self.assertEqual(comp["status"], "success")
        self.assertIn("spot_shift", comp["data"])
        self.assertIn("deltas", comp["data"])

    def test_capture_snapshot_route(self):
        req = CaptureSnapshotRequest(
            underlying="CRUDEOIL",
            spot_price=8915.0,
            strikes=[
                {"strike": 8900.0, "ce": {"oi": 1000, "ltp": 200.0}, "pe": {"oi": 1000, "ltp": 150.0}}
            ],
            pcr_oi=1.1,
            max_pain=8900.0
        )
        res = asyncio.run(capture_snapshot_endpoint(req))
        self.assertEqual(res["status"], "success")
        self.assertIn("SNAP-CRUDEOIL-", res["snapshot_id"])

if __name__ == "__main__":
    unittest.main()

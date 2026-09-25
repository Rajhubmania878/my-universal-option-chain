"""
REST API routes for Historical Snapshot Ingestion, Timeline Discovery & Market Replay (Phase 17).
"""
from typing import Dict, Any, List, Optional
try:
    from fastapi import APIRouter, HTTPException, Query
    from pydantic import BaseModel
except ImportError:
    class APIRouter:
        def __init__(self, *args, **kwargs):
            self.routes = []
        def get(self, *args, **kwargs):
            def decorator(f):
                return f
            return decorator
        def post(self, *args, **kwargs):
            def decorator(f):
                return f
            return decorator
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            self.status_code = status_code
            self.detail = detail
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    def Query(default=None, **kwargs):
        return default

from backend.app.services.storage.snapshot_engine import snapshot_engine

router = APIRouter(prefix="/snapshots", tags=["Historical Snapshots & Market Replay"])

class CaptureSnapshotRequest(BaseModel):
    underlying: str
    spot_price: float
    strikes: List[Dict[str, Any]]
    pcr_oi: float = 1.0
    pcr_volume: float = 1.0
    max_pain: Optional[float] = None
    atm_straddle_premium: Optional[float] = None

@router.get("/timeline")
async def get_snapshots_timeline(
    underlying: str = Query("CRUDEOIL", description="Underlying symbol (e.g. CRUDEOIL, NIFTY)")
) -> Dict[str, Any]:
    """Returns available snapshot timestamps and summary metrics for the timeline scrubber."""
    timeline = snapshot_engine.get_timeline(underlying.upper())
    return {
        "status": "success",
        "underlying": underlying.upper(),
        "count": len(timeline),
        "data": timeline
    }

@router.get("/detail")
async def get_snapshot_detail(
    snapshot_id: str = Query(..., description="Snapshot ID to retrieve"),
    underlying: str = Query("CRUDEOIL", description="Underlying symbol")
) -> Dict[str, Any]:
    """Returns full strike-by-strike Option Chain state at a specific historical timestamp."""
    snap = snapshot_engine.get_snapshot_by_id(underlying.upper(), snapshot_id)
    if not snap:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")
    return {
        "status": "success",
        "data": snap
    }

@router.get("/compare")
async def compare_snapshots_endpoint(
    baseline_id: str = Query(..., description="Baseline Snapshot ID (e.g. 09:15 AM Open)"),
    target_id: str = Query(..., description="Target Snapshot ID (e.g. 13:30 PM Current)"),
    underlying: str = Query("CRUDEOIL", description="Underlying symbol")
) -> Dict[str, Any]:
    """Compares two snapshots to evaluate cumulative OI shift, spot migration, and straddle theta decay."""
    try:
        comparison = snapshot_engine.compare_snapshots(
            underlying=underlying.upper(),
            baseline_id=baseline_id,
            target_id=target_id
        )
        return {"status": "success", "data": comparison}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/capture")
async def capture_snapshot_endpoint(request: CaptureSnapshotRequest) -> Dict[str, Any]:
    """Triggers on-demand capture of the active Option Chain state into the snapshot ring-buffer."""
    try:
        snap = snapshot_engine.capture_snapshot(
            underlying=request.underlying,
            spot_price=request.spot_price,
            strikes_data=request.strikes,
            pcr_oi=request.pcr_oi,
            pcr_volume=request.pcr_volume,
            max_pain=request.max_pain,
            atm_straddle_premium=request.atm_straddle_premium
        )
        return {"status": "success", "snapshot_id": snap.snapshot_id, "market_time": snap.market_time}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

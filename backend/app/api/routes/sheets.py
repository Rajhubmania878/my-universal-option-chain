from typing import Dict, List, Optional, Any

try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        def dict(self):
            return self.__dict__
    def Field(*args, **kwargs):
        return kwargs.get('default', Ellipsis)

try:
    from fastapi import APIRouter, HTTPException, Query, Path, Body
except ImportError:
    class APIRouter:
        def __init__(self, *args, **kwargs):
            pass
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
    def Query(*args, **kwargs):
        return kwargs.get('default', Ellipsis)
    def Path(*args, **kwargs):
        return kwargs.get('default', Ellipsis)
    def Body(*args, **kwargs):
        return kwargs.get('default', Ellipsis)

from backend.app.services.integrations.sheets_exporter import sheets_exporter

router = APIRouter(prefix="/sheets", tags=["Google Sheets & External Export Engine"])

class SyncSheetRequest(BaseModel):
    spreadsheet_id: str = "options-live-dashboard-sheet-id"
    sheet_tab_name: str = "LiveOptionChain"
    underlying: str = "NIFTY"
    expiry: Optional[str] = None
    strike_window: int = 10

@router.get("/export/{underlying}", summary="Export 2D Formatted Option Chain for Google Sheets")
def export_option_chain_for_sheets(
    underlying: str,
    expiry: Optional[str] = Query(default=None, description="Expiry date"),
    strike_window: int = Query(default=10, ge=1, le=25, description="Number of strikes around ATM"),
    exchange: Optional[str] = Query(default=None, description="Exchange (NFO or MCX)")
) -> Dict[str, Any]:
    """
    Generates a 2D matrix array with headers, strike values, live Greeks,
    and dynamic Google Sheets formulas (=SUM, =AVERAGE, =PCR) ready for
    Sheets API or CSV copy-paste.
    """
    try:
        matrix = sheets_exporter.generate_sheet_matrix(
            underlying=underlying,
            expiry=expiry,
            strike_window=strike_window,
            exchange=exchange
        )
        return {
            "status": "success",
            "data": matrix
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/sync", summary="Synchronize Live Option Chain to Google Sheets")
def sync_to_google_sheet(req: SyncSheetRequest) -> Dict[str, Any]:
    """
    Executes synchronization with target Google Sheet spreadsheet and tab.
    """
    try:
        result = sheets_exporter.sync_to_sheet(
            spreadsheet_id=req.spreadsheet_id,
            sheet_tab_name=req.sheet_tab_name,
            underlying=req.underlying,
            expiry=req.expiry
        )
        return {
            "status": "success",
            "message": f"Successfully prepared sync payload for spreadsheet {req.spreadsheet_id}",
            "data": result.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

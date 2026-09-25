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
        def delete(self, *args, **kwargs):
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

from backend.app.services.analytics.alert_engine import (
    alert_engine,
    MetricType,
    AlertCondition
)

router = APIRouter(prefix="/alerts", tags=["Alerts & Threshold Monitoring"])

class CreateRuleRequest(BaseModel):
    underlying: str
    metric: MetricType
    condition: AlertCondition
    threshold: float
    message_template: Optional[str] = None

@router.get("/rules", summary="List All Alert Rules")
def list_rules() -> Dict[str, Any]:
    rules = alert_engine.list_rules()
    return {
        "status": "success",
        "data": [r.to_dict() for r in rules]
    }

@router.post("/rules", summary="Create an Alert Rule")
def create_rule(req: CreateRuleRequest) -> Dict[str, Any]:
    try:
        rule = alert_engine.add_rule(
            underlying=req.underlying,
            metric=req.metric,
            condition=req.condition,
            threshold=req.threshold,
            message_template=req.message_template
        )
        return {
            "status": "success",
            "message": "Alert rule created successfully",
            "data": rule.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/rules/{rule_id}", summary="Delete an Alert Rule")
def delete_rule(rule_id: str) -> Dict[str, Any]:
    success = alert_engine.delete_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return {
        "status": "success",
        "message": f"Rule {rule_id} deleted successfully"
    }

@router.get("/history", summary="Get Triggered Alert History")
def get_alert_history(limit: int = Query(default=50, ge=1, le=200)) -> Dict[str, Any]:
    history = alert_engine.get_history(limit=limit)
    return {
        "status": "success",
        "data": [h.to_dict() for h in history]
    }

@router.post("/evaluate", summary="Evaluate Alert Rules Against Live State")
def evaluate_alerts(underlying: Optional[str] = Query(default=None, description="Optional underlying to evaluate")) -> Dict[str, Any]:
    try:
        triggered = alert_engine.evaluate_rules(underlying=underlying)
        return {
            "status": "success",
            "triggered_count": len(triggered),
            "data": [t.to_dict() for t in triggered]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

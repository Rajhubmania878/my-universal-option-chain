import time
from datetime import datetime

try:
    from fastapi import APIRouter
except ImportError:
    class APIRouter:
        def __init__(self, *args, **kwargs):
            self.routes = []
        def get(self, *args, **kwargs):
            def decorator(f):
                return f
            return decorator

from backend.app.core.config import settings
from backend.app.models.schemas.health import HealthResponse

try:
    import pytz
    IST = pytz.timezone("Asia/Kolkata")
except ImportError:
    IST = None

router = APIRouter()
SERVER_START_TIME = time.time()

@router.get("/health", response_model=HealthResponse, summary="Service Liveness and Health Probe")
def get_health() -> HealthResponse:
    """
    Returns basic application health, uptime, and environment information.
    Used by Oracle Cloud load balancer, Kubernetes/Docker liveness probes, and Google Apps Script.
    """
    now = datetime.now(IST) if IST else datetime.utcnow()
    uptime = time.time() - SERVER_START_TIME
    
    return HealthResponse(
        status="ok",
        app_name=settings.PROJECT_NAME,
        version="1.0.0",
        environment=settings.APP_ENV,
        timestamp=now.isoformat(),
        uptime_seconds=round(uptime, 2)
    )

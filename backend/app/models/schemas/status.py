from typing import Dict, Any, Optional, List

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

class ComponentStatus(BaseModel):
    """Status details for an individual subsystem or integration."""
    component: str = Field(..., description="Component identifier (e.g. postgresql, redis, angel_api)")
    status: str = Field(..., description="Operational status: online, offline, degraded, pending, idle")
    latency_ms: Optional[float] = Field(None, description="Roundtrip check latency in milliseconds")
    last_successful_update: Optional[str] = Field(None, description="ISO timestamp of last successful check/message")
    last_error: Optional[str] = Field(None, description="Description of latest error if any")
    error_count: int = Field(default=0, description="Total sequential or historical error counter")
    details: Dict[str, Any] = Field(default_factory=dict, description="Component-specific metadata")

class SystemStatusResponse(BaseModel):
    """Aggregated system and infrastructure status schema."""
    overall_status: str = Field(..., description="Overall health: operational, degraded, or down")
    timestamp: str = Field(..., description="ISO timestamp in Asia/Kolkata timezone")
    components: List[ComponentStatus] = Field(..., description="List of monitored subsystems")
    active_subscriptions_count: int = Field(default=0, description="Active WebSocket market data tokens count")
    snapshot_interval_seconds: int = Field(default=5, description="Historical persistence snapshot interval")

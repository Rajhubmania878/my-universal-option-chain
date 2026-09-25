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

class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str = Field(..., description="Overall health state: ok, degraded, or unhealthy", example="ok")
    app_name: str = Field(..., description="Name of the application", example="Universal Options Market Dashboard")
    version: str = Field(default="1.0.0", description="Application semantic version")
    environment: str = Field(..., description="Active environment (development/production/testing)")
    timestamp: str = Field(..., description="Current ISO timestamp in Asia/Kolkata timezone")
    uptime_seconds: float = Field(..., description="Uptime in seconds since server started")

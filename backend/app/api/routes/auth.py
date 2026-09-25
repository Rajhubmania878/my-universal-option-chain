from typing import Dict, Any, Optional

try:
    from fastapi import APIRouter, HTTPException, status
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

from backend.app.services.angel.auth import angel_auth_manager

router = APIRouter(prefix="/auth", tags=["Angel One Authentication"])

class AuthActionResponse(BaseModel):
    success: bool
    message: str
    session_status: Dict[str, Any]

class ConnectCredentialsRequest(BaseModel):
    client_code: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None)
    api_key: Optional[str] = Field(default=None)
    totp_secret: Optional[str] = Field(default=None)

@router.get("/session", summary="Get Angel One Session Status")
def get_session_info() -> Dict[str, Any]:
    """
    Returns sanitized session state, expiration countdown, and authentication status.
    Never exposes raw tokens, keys, passwords, or TOTP secrets.
    """
    return angel_auth_manager.get_session_status()

@router.get("/totp", summary="Get Live Generated 6-Digit TOTP for Angel One")
def get_live_totp() -> Dict[str, Any]:
    """
    Returns real-time 6-digit TOTP code derived from the configured Angel One TOTP Base32 secret.
    """
    return angel_auth_manager.get_live_totp_info()

@router.post("/connect", response_model=AuthActionResponse, summary="Connect Angel One SmartAPI with Credentials")
def connect_account(req: ConnectCredentialsRequest) -> AuthActionResponse:
    """
    Authenticates dynamically with Angel One SmartAPI using provided or stored client credentials.
    """
    success = angel_auth_manager.login(
        client_code=req.client_code,
        password=req.password,
        api_key=req.api_key,
        totp_secret=req.totp_secret
    )
    if not success:
        return AuthActionResponse(
            success=False,
            message=f"Authentication failed: {angel_auth_manager.session.last_error or 'Check credentials'}",
            session_status=angel_auth_manager.get_session_status()
        )
    return AuthActionResponse(
        success=True,
        message="Angel One SmartAPI authentication successful.",
        session_status=angel_auth_manager.get_session_status()
    )

@router.post("/login", response_model=AuthActionResponse, summary="Trigger Angel One Login / Session Generation")
def trigger_login() -> AuthActionResponse:
    """
    Triggers authentication with Angel One SmartAPI using server-side environment secrets.
    """
    success = angel_auth_manager.login()
    if not success:
        return AuthActionResponse(
            success=False,
            message=f"Authentication failed: {angel_auth_manager.session.last_error or 'Check credentials in .env'}",
            session_status=angel_auth_manager.get_session_status()
        )
    return AuthActionResponse(
        success=True,
        message="Angel One SmartAPI authentication successful.",
        session_status=angel_auth_manager.get_session_status()
    )

@router.post("/logout", response_model=AuthActionResponse, summary="Terminate Angel One Session")
def trigger_logout() -> AuthActionResponse:
    """
    Terminates active Angel One session and cleans in-memory tokens.
    """
    angel_auth_manager.logout()
    return AuthActionResponse(
        success=True,
        message="Session successfully terminated.",
        session_status=angel_auth_manager.get_session_status()
    )

@router.post("/refresh", response_model=AuthActionResponse, summary="Renew SmartAPI Token")
def trigger_refresh() -> AuthActionResponse:
    """
    Refreshes the active session token.
    """
    success = angel_auth_manager.renew_token()
    return AuthActionResponse(
        success=success,
        message="Token renewal executed successfully." if success else "Token renewal failed; full login required.",
        session_status=angel_auth_manager.get_session_status()
    )

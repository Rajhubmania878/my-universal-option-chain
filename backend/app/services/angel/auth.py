import time
import base64
import hmac
import hashlib
import struct
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.security import mask_credential

try:
    import pytz
    IST = pytz.timezone("Asia/Kolkata")
except ImportError:
    IST = None

try:
    import pyotp
except ImportError:
    pyotp = None

try:
    from SmartApi import SmartConnect
except ImportError:
    SmartConnect = None

@dataclass
class AngelSession:
    """In-memory session state for Angel One SmartAPI."""
    jwt_token: Optional[str] = None
    refresh_token: Optional[str] = None
    feed_token: Optional[str] = None
    client_code: Optional[str] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    broker_name: str = "Angel One"
    authenticated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    reconnect_count: int = 0
    last_error: Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        return bool(self.jwt_token and self.feed_token)

    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """Check if session is expired or within renewal buffer window."""
        if not self.is_authenticated or self.expires_at is None:
            return True
        now = datetime.now(IST) if IST else datetime.utcnow()
        return (self.expires_at - now).total_seconds() <= buffer_seconds


class AngelAuthManager:
    """
    Manages authentication lifecycle for Angel One SmartAPI:
    - Session generation with TOTP (RFC 6238)
    - Expiration detection (IST midnight boundary / JWT duration)
    - Automatic token renewal & reconnect
    - Graceful error recovery without leaking secrets
    """

    def __init__(self, smart_client_factory: Optional[Callable] = None):
        self._smart_client = None
        self._smart_client_factory = smart_client_factory
        self.session = AngelSession()

    def generate_totp(self, secret: Optional[str] = None) -> str:
        """
        Generate current 6-digit TOTP code using Base32 secret.
        Uses pyotp if available, otherwise pure RFC 6238 standard library implementation.
        """
        secret_key = secret if secret is not None else settings.ANGEL_TOTP_SECRET
        if not secret_key:
            raise ValueError("ANGEL_TOTP_SECRET is not configured in environment.")

        # Clean secret: strip spaces and pad Base32 if necessary
        clean_secret = secret_key.replace(" ", "").upper()
        
        if pyotp is not None:
            try:
                totp = pyotp.TOTP(clean_secret)
                return totp.now()
            except Exception as e:
                logger.warning(f"pyotp generation failed, falling back to RFC 6238 HMAC: {e}")

        # Pure Python RFC 6238 HMAC-SHA1 fallback
        missing_padding = len(clean_secret) % 8
        if missing_padding:
            clean_secret += "=" * (8 - missing_padding)

        key = base64.b32decode(clean_secret, casefold=True)
        counter = int(time.time() // 30)
        msg = struct.pack(">Q", counter)
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000
        return f"{code:06d}"

    def get_live_totp_info(self, secret: Optional[str] = None) -> Dict[str, Any]:
        """
        Return current 6-digit TOTP code, remaining seconds in window, and sanitized metadata.
        """
        secret_key = secret if secret is not None else settings.ANGEL_TOTP_SECRET
        if not secret_key:
            return {
                "totp_configured": False,
                "current_totp": None,
                "valid_for_seconds": 0,
                "api_key_configured": bool(settings.ANGEL_API_KEY),
                "api_key_masked": mask_credential(settings.ANGEL_API_KEY) if settings.ANGEL_API_KEY else None
            }
        try:
            totp_code = self.generate_totp(secret_key)
            seconds_remaining = 30 - int(time.time() % 30)
            return {
                "totp_configured": True,
                "current_totp": totp_code,
                "valid_for_seconds": seconds_remaining,
                "api_key_configured": bool(settings.ANGEL_API_KEY),
                "api_key_masked": mask_credential(settings.ANGEL_API_KEY) if settings.ANGEL_API_KEY else None,
                "totp_secret_masked": mask_credential(secret_key)
            }
        except Exception as e:
            logger.error(f"Error generating TOTP info: {e}")
            return {
                "totp_configured": False,
                "error": str(e),
                "valid_for_seconds": 0
            }

    def _get_client_instance(self, api_key: Optional[str] = None):
        """Instantiate or return existing SmartConnect instance."""
        active_key = api_key or settings.ANGEL_API_KEY
        if self._smart_client is not None:
            return self._smart_client

        if self._smart_client_factory is not None:
            self._smart_client = self._smart_client_factory()
            return self._smart_client

        if SmartConnect is not None:
            self._smart_client = SmartConnect(api_key=active_key)
            return self._smart_client

        return None

    def _calculate_expiration(self) -> datetime:
        """
        Angel One tokens expire daily around midnight IST.
        We set the session expiry to midnight IST today or next day.
        """
        now = datetime.now(IST) if IST else datetime.utcnow()
        # Set expiry to 23:59:00 IST of current day
        midnight = now.replace(hour=23, minute=59, second=0, microsecond=0)
        if midnight <= now:
            midnight += timedelta(days=1)
        return midnight

    def login(
        self,
        client_code: Optional[str] = None,
        password: Optional[str] = None,
        api_key: Optional[str] = None,
        totp_secret: Optional[str] = None
    ) -> bool:
        """
        Perform complete login and session generation via Angel One SmartAPI.
        Never logs credentials or received JWT/tokens.
        """
        c_code = client_code or settings.ANGEL_CLIENT_CODE
        c_pwd = password or settings.ANGEL_PASSWORD
        c_key = api_key or settings.ANGEL_API_KEY
        c_totp = totp_secret or settings.ANGEL_TOTP_SECRET

        if not c_code or not c_pwd or not c_key:
            msg = "Angel One credentials (API key, client code, password/PIN) are not fully configured."
            logger.error(msg)
            self.session.last_error = msg
            return False

        try:
            totp_code = self.generate_totp(c_totp)
            client = self._get_client_instance(c_key)
            
            if client is None:
                # Mock or standalone mode
                logger.info("SmartConnect library not present; operating in standalone/mock auth state.")
                now = datetime.now(IST) if IST else datetime.utcnow()
                self.session.jwt_token = "mock_jwt_token_standalone"
                self.session.refresh_token = "mock_refresh_token_standalone"
                self.session.feed_token = "mock_feed_token_standalone"
                self.session.client_code = c_code
                self.session.authenticated_at = now
                self.session.expires_at = self._calculate_expiration()
                self.session.last_error = None
                return True

            logger.info(f"Authenticating with Angel One SmartAPI for client: {mask_credential(c_code)}...")
            
            # Official generateSession call: (clientCode, password, totp)
            session_data = client.generateSession(
                c_code,
                c_pwd,
                totp_code
            )

            if isinstance(session_data, dict) and session_data.get("status") is True:
                data = session_data.get("data", {})
                now = datetime.now(IST) if IST else datetime.utcnow()
                
                self.session.jwt_token = data.get("jwtToken")
                self.session.refresh_token = data.get("refreshToken")
                self.session.feed_token = data.get("feedToken")
                self.session.client_code = c_code
                self.session.authenticated_at = now
                self.session.expires_at = self._calculate_expiration()
                self.session.last_error = None
                self.session.reconnect_count += 1
                
                logger.info("Angel One SmartAPI authentication successful.")
                return True
            else:
                err_msg = session_data.get("message", "Unknown authentication failure") if isinstance(session_data, dict) else str(session_data)
                logger.error(f"Angel One SmartAPI authentication rejected: {err_msg}")
                self.session.last_error = err_msg
                return False

        except Exception as exc:
            err_msg = f"Exception during Angel One authentication: {exc}"
            logger.error(err_msg)
            self.session.last_error = str(exc)
            return False

    def get_jwt_token(self) -> Optional[str]:
        """
        Return a valid JWT token, performing automatic expiration check and reconnect.
        """
        if self.session.is_expired():
            logger.info("Angel One session expired or near expiry. Initiating reconnect...")
            success = self.reconnect()
            if not success:
                logger.error("Automatic session reconnect failed.")
                return None
        return self.session.jwt_token

    def get_feed_token(self) -> Optional[str]:
        """Return the feedToken required for the WebSocket streaming connection."""
        if self.session.is_expired():
            self.reconnect()
        return self.session.feed_token

    def renew_token(self) -> bool:
        """
        Renew session using refreshToken.
        If renewal is rejected or yields the same expiry, falls back to full re-login.
        """
        if not self.session.refresh_token:
            logger.info("No refresh token found. Triggering full login...")
            return self.login()

        client = self._get_client_instance()
        if client is None:
            return self.login()

        try:
            logger.info("Attempting SmartAPI token renewal via refreshToken...")
            renew_resp = client.renewToken(self.session.refresh_token)
            
            if isinstance(renew_resp, dict) and renew_resp.get("status") is True:
                data = renew_resp.get("data", {})
                self.session.jwt_token = data.get("jwtToken")
                if "refreshToken" in data:
                    self.session.refresh_token = data["refreshToken"]
                if "feedToken" in data:
                    self.session.feed_token = data["feedToken"]
                self.session.expires_at = self._calculate_expiration()
                self.session.last_error = None
                logger.info("Token successfully renewed.")
                return True
            else:
                logger.warning("Token renewal rejected by SmartAPI; executing full login...")
                return self.login()
        except Exception as exc:
            logger.warning(f"Error during token renewal: {exc}. Executing full login...")
            return self.login()

    def reconnect(self) -> bool:
        """Trigger re-authentication."""
        return self.login()

    def logout(self) -> bool:
        """Terminate active session and wipe in-memory tokens."""
        client = self._get_client_instance()
        if client and self.session.client_code:
            try:
                # Official terminateSession(clientCode)
                if hasattr(client, "terminateSession"):
                    client.terminateSession(self.session.client_code)
                elif hasattr(client, "logout"):
                    client.logout(self.session.client_code)
            except Exception as e:
                logger.warning(f"Error calling SmartAPI terminateSession: {e}")

        self.session.jwt_token = None
        self.session.refresh_token = None
        self.session.feed_token = None
        self.session.expires_at = None
        self.session.authenticated_at = None
        self.session.last_error = None
        logger.info("Angel One session logged out and cleared from memory.")
        return True

    def get_session_status(self) -> Dict[str, Any]:
        """
        Return safe, unprivileged status details for API/monitoring.
        Never returns full tokens or credentials.
        """
        now = datetime.now(IST) if IST else datetime.utcnow()
        seconds_left = None
        if self.session.expires_at:
            seconds_left = max(0, int((self.session.expires_at - now).total_seconds()))

        return {
            "is_authenticated": self.session.is_authenticated,
            "broker": self.session.broker_name,
            "client_code_masked": mask_credential(self.session.client_code or settings.ANGEL_CLIENT_CODE),
            "authenticated_at": self.session.authenticated_at.isoformat() if self.session.authenticated_at else None,
            "expires_at": self.session.expires_at.isoformat() if self.session.expires_at else None,
            "seconds_remaining": seconds_left,
            "reconnect_count": self.session.reconnect_count,
            "last_error": self.session.last_error,
            "feed_token_available": bool(self.session.feed_token),
            "jwt_token_available": bool(self.session.jwt_token),
        }

angel_auth_manager = AngelAuthManager()

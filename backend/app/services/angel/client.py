from typing import Optional, Dict, Any
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.services.angel.auth import angel_auth_manager

class AngelClientProvider:
    """
    HTTP and SmartConnect client provider for Angel One SmartAPI operations.
    Ensures that every outbound request carries valid authentication tokens.
    """

    def __init__(self, auth_manager=angel_auth_manager):
        self.auth_manager = auth_manager

    def get_auth_headers(self) -> Dict[str, str]:
        """
        Build standard SmartAPI HTTP headers with valid JWT token.
        """
        jwt = self.auth_manager.get_jwt_token()
        if not jwt:
            raise PermissionError("Not authenticated with Angel One SmartAPI. Login required.")

        return {
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "fe80::1",
            "X-PrivateKey": settings.ANGEL_API_KEY or "",
        }

    def get_profile(self) -> Dict[str, Any]:
        """Fetch client profile information from Angel One."""
        client = self.auth_manager._get_client_instance()
        if client and hasattr(client, "getProfile"):
            token = self.auth_manager.get_jwt_token()
            return client.getProfile(token)
        
        # Standalone mock response
        return {
            "status": True,
            "message": "SUCCESS",
            "data": {
                "clientcode": self.auth_manager.session.client_code or "MOCK_CLIENT",
                "name": "Quantitative Trader",
                "email": "user@domain.com",
                "mobileno": "9876543210",
                "exchanges": ["NSE", "NFO", "MCX", "BSE"],
                "products": ["CNC", "MIS", "NRML"],
            }
        }

angel_client_provider = AngelClientProvider()

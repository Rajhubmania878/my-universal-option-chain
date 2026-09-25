import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from backend.app.core.config import settings
from backend.app.services.angel.auth import AngelAuthManager, AngelSession
from backend.app.services.angel.client import AngelClientProvider

class TestAngelOneAuth(unittest.TestCase):
    def setUp(self):
        settings.ANGEL_API_KEY = "test_api_key_mock"
        settings.ANGEL_CLIENT_CODE = "A123456"
        settings.ANGEL_PASSWORD = "mock_secret_pin"
        settings.ANGEL_TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # Standard base32 test key

    def test_totp_generation(self):
        auth = AngelAuthManager()
        code = auth.generate_totp("JBSWY3DPEHPK3PXP")
        self.assertTrue(code.isdigit())
        self.assertEqual(len(code), 6)

    def test_totp_missing_secret_raises(self):
        auth = AngelAuthManager()
        with self.assertRaises(ValueError):
            auth.generate_totp(secret="")

    def test_login_with_mock_smart_client_success(self):
        mock_smart = MagicMock()
        mock_smart.generateSession.return_value = {
            "status": True,
            "message": "SUCCESS",
            "errorcode": "",
            "data": {
                "jwtToken": "mock_jwt_header.payload.signature",
                "refreshToken": "mock_refresh_token_xyz",
                "feedToken": "mock_feed_token_123"
            }
        }

        auth = AngelAuthManager(smart_client_factory=lambda: mock_smart)
        success = auth.login()

        self.assertTrue(success)
        self.assertTrue(auth.session.is_authenticated)
        self.assertEqual(auth.session.jwt_token, "mock_jwt_header.payload.signature")
        self.assertEqual(auth.session.feed_token, "mock_feed_token_123")
        self.assertEqual(auth.session.reconnect_count, 1)
        self.assertFalse(auth.session.is_expired())

        # Verify SmartAPI generateSession was called with correct client code
        mock_smart.generateSession.assert_called_once()
        call_args = mock_smart.generateSession.call_args[0]
        self.assertEqual(call_args[0], "A123456")
        self.assertEqual(call_args[1], "mock_secret_pin")
        self.assertEqual(len(call_args[2]), 6)  # TOTP 6 digits

    def test_login_failure_handling(self):
        mock_smart = MagicMock()
        mock_smart.generateSession.return_value = {
            "status": False,
            "message": "Invalid credentials or TOTP expired",
            "errorcode": "AB1004",
            "data": None
        }

        auth = AngelAuthManager(smart_client_factory=lambda: mock_smart)
        success = auth.login()

        self.assertFalse(success)
        self.assertFalse(auth.session.is_authenticated)
        self.assertIn("Invalid credentials", auth.session.last_error)

    def test_expiration_detection_and_auto_reconnect(self):
        mock_smart = MagicMock()
        mock_smart.generateSession.return_value = {
            "status": True,
            "message": "SUCCESS",
            "data": {
                "jwtToken": "token_reconnected",
                "refreshToken": "refresh_reconnected",
                "feedToken": "feed_reconnected"
            }
        }

        auth = AngelAuthManager(smart_client_factory=lambda: mock_smart)
        # Manually seed an expired session
        auth.session.jwt_token = "old_expired_token"
        auth.session.feed_token = "old_feed_token"
        auth.session.expires_at = datetime.utcnow() - timedelta(minutes=10)

        self.assertTrue(auth.session.is_expired())

        # Calling get_jwt_token should trigger auto-reconnect
        token = auth.get_jwt_token()
        self.assertEqual(token, "token_reconnected")
        self.assertEqual(auth.session.reconnect_count, 1)

    def test_token_renewal_success(self):
        mock_smart = MagicMock()
        mock_smart.renewToken.return_value = {
            "status": True,
            "message": "SUCCESS",
            "data": {
                "jwtToken": "renewed_jwt_token",
                "refreshToken": "renewed_refresh_token",
                "feedToken": "renewed_feed_token"
            }
        }

        auth = AngelAuthManager(smart_client_factory=lambda: mock_smart)
        auth.session.refresh_token = "valid_refresh_token"
        auth.session.jwt_token = "initial_token"
        auth.session.feed_token = "initial_feed"

        renewed = auth.renew_token()
        self.assertTrue(renewed)
        self.assertEqual(auth.session.jwt_token, "renewed_jwt_token")
        self.assertEqual(auth.session.feed_token, "renewed_feed_token")

    def test_logout(self):
        mock_smart = MagicMock()
        auth = AngelAuthManager(smart_client_factory=lambda: mock_smart)
        auth.session.jwt_token = "token_to_clear"
        auth.session.feed_token = "feed_to_clear"
        auth.session.client_code = "A123456"

        auth.logout()
        self.assertFalse(auth.session.is_authenticated)
        self.assertIsNone(auth.session.jwt_token)
        self.assertIsNone(auth.session.feed_token)

    def test_session_status_never_exposes_secrets(self):
        auth = AngelAuthManager()
        auth.session.jwt_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.sensitive_payload"
        auth.session.refresh_token = "secret_refresh_token_999"
        auth.session.feed_token = "secret_feed_token_888"
        auth.session.client_code = "A123456"
        auth.session.expires_at = datetime.utcnow() + timedelta(hours=4)

        status_data = auth.get_session_status()
        status_str = str(status_data)

        # Confirm tokens and secrets never appear in status dictionary
        self.assertNotIn("sensitive_payload", status_str)
        self.assertNotIn("secret_refresh_token", status_str)
        self.assertNotIn("secret_feed_token", status_str)
        self.assertTrue(status_data["is_authenticated"])
        self.assertTrue(status_data["jwt_token_available"])
        self.assertTrue(status_data["feed_token_available"])
        self.assertEqual(status_data["client_code_masked"], "A1***56")

    def test_auth_headers_generation(self):
        auth = AngelAuthManager()
        auth.session.jwt_token = "valid_test_jwt"
        auth.session.feed_token = "valid_test_feed"
        auth.session.expires_at = datetime.utcnow() + timedelta(hours=1)

        client_provider = AngelClientProvider(auth_manager=auth)
        headers = client_provider.get_auth_headers()

        self.assertEqual(headers["Authorization"], "Bearer valid_test_jwt")
        self.assertEqual(headers["X-PrivateKey"], "test_api_key_mock")
        self.assertEqual(headers["X-UserType"], "USER")

if __name__ == "__main__":
    unittest.main()

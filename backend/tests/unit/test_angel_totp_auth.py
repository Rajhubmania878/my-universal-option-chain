import unittest
from backend.app.services.angel.auth import AngelAuthManager
from backend.app.api.routes.auth import (
    get_live_totp,
    connect_account,
    ConnectCredentialsRequest
)


class TestAngelAuthAndTotp(unittest.TestCase):
    def setUp(self):
        self.auth_mgr = AngelAuthManager()

    def test_totp_generation_with_secret(self):
        secret = "ABZDZPRGOK7SGZIS52GXKHZR5M"
        totp = self.auth_mgr.generate_totp(secret)
        self.assertEqual(len(totp), 6)
        self.assertTrue(totp.isdigit())

    def test_live_totp_info(self):
        info = get_live_totp()
        self.assertTrue(info["totp_configured"])
        self.assertIsNotNone(info["current_totp"])
        self.assertGreaterEqual(info["valid_for_seconds"], 0)
        self.assertLessEqual(info["valid_for_seconds"], 30)

    def test_connect_account_standalone_mode(self):
        req = ConnectCredentialsRequest(
            client_code="R123456",
            password="123456_PIN",
            api_key="vTz0rnxJ",
            totp_secret="ABZDZPRGOK7SGZIS52GXKHZR5M"
        )
        res = connect_account(req)
        self.assertTrue(res.success)
        self.assertIn("successful", res.message)
        self.assertTrue(res.session_status["is_authenticated"])


if __name__ == '__main__':
    unittest.main()

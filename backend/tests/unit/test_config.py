import unittest
import os
from backend.app.core.config import Settings
from backend.app.core.security import mask_credential, sanitize_dict

class TestConfigAndSecurity(unittest.TestCase):
    def test_default_settings(self):
        cfg = Settings()
        self.assertEqual(cfg.PROJECT_NAME, "Universal Options Market Dashboard")
        self.assertEqual(cfg.API_V1_PREFIX, "/api/v1")
        self.assertEqual(cfg.SNAPSHOT_INTERVAL_SECONDS, 5)
        self.assertIn("postgresql+psycopg2://", cfg.sqlalchemy_database_uri)
        self.assertIn("redis://", cfg.redis_url)

    def test_mask_credential(self):
        masked = mask_credential("SECRET_PASSWORD_12345", visible_prefix=2, visible_suffix=2)
        self.assertTrue(masked.startswith("SE"))
        self.assertTrue(masked.endswith("45"))
        self.assertNotIn("PASSWORD", masked)

    def test_masked_summary_never_exposes_secrets(self):
        os.environ["ANGEL_PASSWORD"] = "SuperSecretPin999"
        os.environ["ANGEL_API_KEY"] = "MyApiKey123"
        cfg = Settings()
        summary = cfg.get_masked_summary()
        
        # Verify secret values are not in summary
        summary_str = str(summary)
        self.assertNotIn("SuperSecretPin999", summary_str)
        self.assertNotIn("MyApiKey123", summary_str)
        self.assertTrue(summary["angel_one"]["api_key_configured"])

    def test_sanitize_dict(self):
        raw = {
            "token": "12345",
            "api_key": "raw_secret_key",
            "password": "secret_password",
            "strike": 8900,
            "nested": {
                "totp_secret": "ABCDEF123456",
                "exchange": "MCX"
            }
        }
        sanitized = sanitize_dict(raw)
        self.assertEqual(sanitized["strike"], 8900)
        self.assertEqual(sanitized["token"], "[REDACTED]")
        self.assertEqual(sanitized["api_key"], "[REDACTED]")
        self.assertEqual(sanitized["password"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["totp_secret"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["exchange"], "MCX")

if __name__ == "__main__":
    unittest.main()

import unittest
from backend.app.api.routes.health import get_health

class TestHealthEndpoint(unittest.TestCase):
    def test_get_health(self):
        health = get_health()
        self.assertEqual(health.status, "ok")
        self.assertIn("Options Market", health.app_name)
        self.assertGreaterEqual(health.uptime_seconds, 0.0)
        self.assertIsNotNone(health.timestamp)

if __name__ == "__main__":
    unittest.main()

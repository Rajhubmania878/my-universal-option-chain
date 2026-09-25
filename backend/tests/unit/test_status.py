import unittest
from backend.app.api.routes.status import get_status

class TestStatusEndpoint(unittest.TestCase):
    def test_get_status_components(self):
        status_resp = get_status()
        self.assertIn(status_resp.overall_status, ["operational", "operational_standalone", "degraded"])
        self.assertIsNotNone(status_resp.timestamp)
        
        # Verify all mandatory components from spec are reported
        component_names = {comp.component for comp in status_resp.components}
        expected_components = {"Angel API", "WebSocket", "Oracle API", "PostgreSQL", "Redis", "Google Sheets"}
        for expected in expected_components:
            self.assertIn(expected, component_names, f"Expected component {expected} missing from status report")

    def test_graceful_degradation_without_live_services(self):
        """Ensure checking status without running DB or Redis returns clean offline/fallback status rather than crashing."""
        status_resp = get_status()
        redis_comp = next(c for c in status_resp.components if c.component == "Redis")
        self.assertIn(redis_comp.status, ["online", "fallback_mode", "offline"])

if __name__ == "__main__":
    unittest.main()

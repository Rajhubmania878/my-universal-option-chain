import unittest
from backend.app.services.analytics.alert_engine import AlertEngine, AlertRule, MetricType, AlertCondition

class TestAlertEngine(unittest.TestCase):
    def setUp(self):
        self.engine = AlertEngine()

    def test_default_rules_seeded(self):
        rules = self.engine.list_rules()
        self.assertGreaterEqual(len(rules), 3)
        rule_metrics = [r.metric for r in rules]
        self.assertIn(MetricType.IV_RANK, rule_metrics)
        self.assertIn(MetricType.OI_PCR, rule_metrics)
        self.assertIn(MetricType.ATM_STRADDLE_PREMIUM, rule_metrics)

    def test_add_and_delete_rule(self):
        new_rule = self.engine.add_rule(
            underlying="NIFTY",
            metric=MetricType.SPOT_PRICE,
            condition=AlertCondition.GREATER_THAN,
            threshold=24000.0,
            message_template="NIFTY crossed {threshold}! Spot is {value}"
        )
        self.assertTrue(new_rule.id.startswith("rule-"))
        self.assertEqual(new_rule.underlying, "NIFTY")
        self.assertEqual(new_rule.threshold, 24000.0)

        # Confirm listed
        rules = self.engine.list_rules()
        self.assertTrue(any(r.id == new_rule.id for r in rules))

        # Delete rule
        deleted = self.engine.delete_rule(new_rule.id)
        self.assertTrue(deleted)
        self.assertFalse(any(r.id == new_rule.id for r in self.engine.list_rules()))

    def test_evaluate_rule_triggers_alert(self):
        # Add a rule that will definitely trigger against live NIFTY state (spot is ~23045)
        rule = self.engine.add_rule(
            underlying="NIFTY",
            metric=MetricType.SPOT_PRICE,
            condition=AlertCondition.GREATER_THAN,
            threshold=20000.0,
            message_template="NIFTY bullish alert: spot {value} > {threshold}"
        )
        triggered = self.engine.evaluate_rules(underlying="NIFTY")
        matching = [t for t in triggered if t.rule_id == rule.id]
        self.assertGreater(len(matching), 0)
        self.assertGreater(matching[0].current_value, 20000.0)
        self.assertIn("NIFTY bullish alert", matching[0].message)

        # Verify in history
        history = self.engine.get_history()
        self.assertTrue(any(h.id == matching[0].id for h in history))

    def test_evaluate_rule_negative_condition(self):
        # Add a rule that will NOT trigger (spot price < 15000)
        rule = self.engine.add_rule(
            underlying="NIFTY",
            metric=MetricType.SPOT_PRICE,
            condition=AlertCondition.LESS_THAN,
            threshold=15000.0
        )
        triggered = self.engine.evaluate_rules(underlying="NIFTY")
        matching = [t for t in triggered if t.rule_id == rule.id]
        self.assertEqual(len(matching), 0)

    def test_evaluate_crudeoil_straddle_rule(self):
        # Trigger straddle alert when premium > 10
        rule = self.engine.add_rule(
            underlying="CRUDEOIL",
            metric=MetricType.ATM_STRADDLE_PREMIUM,
            condition=AlertCondition.GREATER_THAN,
            threshold=10.0
        )
        triggered = self.engine.evaluate_rules(underlying="CRUDEOIL")
        matching = [t for t in triggered if t.rule_id == rule.id]
        self.assertGreater(len(matching), 0)
        self.assertGreater(matching[0].current_value, 10.0)

    def test_rule_serialization_to_dict(self):
        rule = self.engine.add_rule(
            underlying="RELIANCE",
            metric=MetricType.OI_PCR,
            condition=AlertCondition.LESS_THAN,
            threshold=0.85
        )
        d = rule.to_dict()
        self.assertEqual(d["underlying"], "RELIANCE")
        self.assertEqual(d["metric"], "oi_pcr")
        self.assertEqual(d["condition"], "<")
        self.assertEqual(d["threshold"], 0.85)

if __name__ == "__main__":
    unittest.main()

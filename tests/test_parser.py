import os
import unittest
from unittest.mock import patch

from policygate.parser import parse, parse_offline


class OfflineParserTests(unittest.TestCase):
    def test_happy_request(self):
        r = parse_offline(
            "prod Postgres on AWS in us-east-1, HA required, 30-day backups, $900/month. Approver: Jane Smith",
            "Demo Engineer",
        )
        self.assertEqual(r.environment, "production")
        self.assertTrue(r.high_availability)
        self.assertEqual(r.backup_retention_days, 30)
        self.assertEqual(r.monthly_budget_usd, 900)
        self.assertEqual(r.approver_name, "Jane Smith")
        self.assertIsNone(r.encryption_at_rest)

    def test_explicit_bad_controls_are_preserved(self):
        r = parse_offline(
            "production postgres, single AZ, no encryption, 7-day backups, public access enabled, $900",
            "Demo Engineer",
        )
        self.assertFalse(r.high_availability)
        self.assertFalse(r.encryption_at_rest)
        self.assertTrue(r.public_access)
        self.assertEqual(r.backup_retention_days, 7)


class LiveParserFailureModeTests(unittest.TestCase):
    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "POLICYGATE_ALLOW_AI_FALLBACK": "false"},
        clear=False,
    )
    @patch("policygate.parser.parse_with_claude", side_effect=RuntimeError("Claude unavailable"))
    def test_live_claude_failure_fails_closed_by_default(self, _mock_claude):
        with self.assertRaisesRegex(RuntimeError, "Claude unavailable"):
            parse("prod Postgres on AWS", "Demo Engineer")

    @patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "POLICYGATE_ALLOW_AI_FALLBACK": "true"},
        clear=False,
    )
    @patch("policygate.parser.parse_with_claude", side_effect=RuntimeError("Claude unavailable"))
    def test_explicit_ai_fallback_uses_offline_parser(self, _mock_claude):
        result = parse("prod Postgres on AWS, HA required, 30-day backups, $900", "Demo Engineer")
        self.assertEqual(result.environment, "production")
        self.assertTrue(result.high_availability)
        self.assertEqual(result.backup_retention_days, 30)


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from policygate import demo_evidence

VERIFIED = {
    "claude_live": True,
    "policy_result": "PASS",
    "terraform_live_plan": True,
    "terraform_resources_added": 1,
    "terraform_resources_changed": 0,
    "terraform_resources_destroyed": 0,
    "terraform_plan_sha256": "a" * 64,
    "terraform_plan_summary": "Plan: 1 to add, 0 to change, 0 to destroy.",
    "foxit_mcp_live": True,
    "foxit_esign_live": True,
    "foxit_status": "EXECUTED",
    "human_gate_state": "VERIFIED",
    "human_signature_verified": True,
    "final_audit_state": "APPROVED",
}


class SanitizeTests(unittest.TestCase):
    def test_only_allowed_fields_survive(self):
        raw = dict(VERIFIED)
        raw.update({
            "foxit_folder_id": "35508167",
            "aws_account_id": "123456789012",
            "client_secret": "super-secret",
            "signed_session_url": "https://na1.fusion.foxit.com/session/abc",
        })
        clean = demo_evidence.sanitize(raw)
        self.assertEqual(set(clean), set(VERIFIED))
        for dropped in ("foxit_folder_id", "aws_account_id", "client_secret", "signed_session_url"):
            self.assertNotIn(dropped, clean)

    def test_email_in_an_allowed_field_is_rejected(self):
        raw = dict(VERIFIED, human_gate_state="VERIFIED by jane@example.com")
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(raw)

    def test_url_is_rejected(self):
        raw = dict(VERIFIED, foxit_status="EXECUTED https://na1.fusion.foxit.com/s/xyz")
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(raw)

    def test_aws_account_id_is_rejected(self):
        raw = dict(VERIFIED, terraform_plan_summary="account 123456789012 will be used")
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(raw)

    def test_credential_shaped_text_is_rejected(self):
        raw = dict(VERIFIED, terraform_plan_summary="aws_secret_access_key = wJalr")
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(raw)

    def test_terraform_state_is_rejected(self):
        raw = dict(VERIFIED, terraform_plan_summary="see terraform.tfstate for details")
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(raw)

    def test_plan_hash_must_be_a_digest(self):
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(dict(VERIFIED, terraform_plan_sha256="not-a-hash"))

    def test_build_produces_only_allowed_fields(self):
        built = demo_evidence.build(
            claude_live=True, policy_passed=True, terraform_live_plan=True,
            resources_added=1, resources_changed=0, resources_destroyed=0,
            terraform_plan_sha256="b" * 64,
            terraform_plan_summary="Plan: 1 to add, 0 to change, 0 to destroy.",
            foxit_mcp_live=True, foxit_esign_live=True, foxit_status="EXECUTED",
            human_gate_state="VERIFIED", human_signature_verified=True,
            final_audit_state="APPROVED",
        )
        self.assertTrue(set(built).issubset(set(demo_evidence.ALLOWED_FIELDS)))
        self.assertEqual(built["policy_result"], "PASS")


class BadgeTests(unittest.TestCase):
    def test_verified_evidence_produces_the_headline_badges(self):
        self.assertEqual(
            demo_evidence.badges(VERIFIED),
            {
                "Claude": "LIVE",
                "Policy Engine": "PASS",
                "Terraform": "LIVE PLAN",
                "Foxit MCP": "LIVE",
                "Foxit eSign": "LIVE",
                "Human Gate": "VERIFIED",
            },
        )

    def test_no_evidence_means_no_badges(self):
        self.assertIsNone(demo_evidence.badges(None))
        self.assertIsNone(demo_evidence.badges({}))

    def test_unsigned_run_does_not_claim_verified(self):
        pending = dict(
            VERIFIED,
            foxit_status="SENT",
            human_gate_state="AWAITING_HUMAN_APPROVAL",
            human_signature_verified=False,
            final_audit_state="AWAITING_HUMAN_APPROVAL",
        )
        self.assertFalse(demo_evidence.is_verified(pending))
        self.assertIsNone(demo_evidence.badges(pending))

    def test_completed_is_not_executed(self):
        self.assertFalse(demo_evidence.is_verified(dict(VERIFIED, foxit_status="COMPLETED")))

    def test_any_offline_integration_blocks_the_badges(self):
        for field in ("claude_live", "terraform_live_plan", "foxit_mcp_live", "foxit_esign_live"):
            with self.subTest(field=field):
                self.assertFalse(demo_evidence.is_verified(dict(VERIFIED, **{field: False})))

    def test_failed_policy_blocks_the_badges(self):
        self.assertFalse(demo_evidence.is_verified(dict(VERIFIED, policy_result="FAIL")))


class LoadTests(unittest.TestCase):
    def test_missing_file_returns_none(self):
        with TemporaryDirectory() as tmp:
            self.assertIsNone(demo_evidence.load(Path(tmp) / "absent.json"))

    def test_unreadable_json_returns_none(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo-evidence.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertIsNone(demo_evidence.load(path))

    def test_round_trip_from_disk(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo-evidence.json"
            path.write_text(json.dumps(dict(VERIFIED, foxit_folder_id="35508167")), encoding="utf-8")
            loaded = demo_evidence.load(path)
            self.assertNotIn("foxit_folder_id", loaded)
            self.assertTrue(demo_evidence.is_verified(loaded))

    def test_no_evidence_ships_in_the_repository(self):
        """A committed sample carrying LIVE values would be indistinguishable
        from a real run on screen."""
        self.assertFalse(demo_evidence.DEFAULT_EVIDENCE_PATH.exists())


if __name__ == "__main__":
    unittest.main()

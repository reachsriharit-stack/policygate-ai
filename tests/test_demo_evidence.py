import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from policygate import demo_evidence

APP = Path(__file__).resolve().parents[1] / "policygate" / "streamlit_app.py"

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64

HCL = """resource "aws_db_instance" "policygate_db" {
  engine                      = "postgres"
  multi_az                    = true
  storage_encrypted           = true
  backup_retention_period     = 30
  publicly_accessible         = false
  manage_master_user_password = true
}"""

VERIFIED = {
    "request_text": "Provision production PostgreSQL on AWS in us-east-1.",
    "claude_live": True,
    "claude_fallback_used": False,
    "parsed_environment": "production",
    "parsed_cloud": "aws",
    "parsed_region": "us-east-1",
    "parsed_service": "PostgreSQL",
    "parsed_high_availability": True,
    "parsed_backup_retention_days": 30,
    "parsed_budget_monthly": 900,
    "requested_controls": ["PostgreSQL", "AWS us-east-1", "High availability"],
    "policy_injected_controls": ["Encryption at rest", "Human approval required"],
    "policy_rule_results": [
        {"code": "REG-01", "description": "AWS region is approved", "result": "PASS"},
        {"code": "SEC-01", "description": "Encryption at rest required", "result": "PASS"},
    ],
    "policy_result": "PASS",
    "terraform_generated": True,
    "terraform_resource_type": "AWS RDS PostgreSQL",
    "terraform_multi_az": True,
    "terraform_encrypted": True,
    "terraform_backup_retention_days": 30,
    "terraform_publicly_accessible": False,
    "terraform_managed_password": True,
    "terraform_hcl_preview": HCL,
    "terraform_live_plan": True,
    "terraform_add": 1,
    "terraform_change": 0,
    "terraform_destroy": 0,
    "terraform_plan_sha256": HASH_A,
    "terraform_plan_summary": "Plan: 1 to add, 0 to change, 0 to destroy.",
    "approval_pdf_generated": True,
    "unsigned_pdf_sha256": HASH_B,
    "foxit_mcp_live": True,
    "foxit_mcp_operation_verified": True,
    "foxit_mcp_output_pdf_sha256": HASH_C,
    "foxit_esign_live": True,
    "pre_approval_state": "AWAITING_HUMAN_APPROVAL",
    "agent_may_sign": False,
    "agent_signed": False,
    "provisioning_allowed_before_approval": False,
    "foxit_status": "EXECUTED",
    "human_signature_verified": True,
    "signer_match": True,
    "human_gate_state": "VERIFIED",
    "terraform_plan_hash_verified": True,
    "terraform_replanned_after_signature": False,
    "signed_pdf_sha256": "d" * 64,
    "final_audit_state": "APPROVED",
    "terraform_apply_ran": False,
    "terraform_destroy_ran": False,
}


class OfflineFallbackTests(unittest.TestCase):
    """1. No evidence keeps the honest offline labels."""

    def test_no_evidence_produces_no_badges(self):
        self.assertIsNone(demo_evidence.badges(None))
        self.assertIsNone(demo_evidence.badges({}))
        self.assertFalse(demo_evidence.is_verified(None))

    def test_missing_file_returns_none(self):
        with TemporaryDirectory() as tmp:
            self.assertIsNone(demo_evidence.load(Path(tmp) / "absent.json"))

    def test_unreadable_json_returns_none(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo-evidence.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertIsNone(demo_evidence.load(path))

    def test_the_app_falls_back_to_runtime_status(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn("runtime.claude", source)
        self.assertIn("runtime.foxit_esign", source)


class VerifiedBadgeTests(unittest.TestCase):
    """2. A verified run produces the headline badges."""

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

    def test_badges_are_derived_not_written_by_the_app(self):
        """15. Nothing in the UI may hard-code a verified state."""
        source = APP.read_text(encoding="utf-8")
        self.assertNotIn('"Claude": "LIVE"', source)
        self.assertIn("demo_evidence.badges(", source)


class DisplayedFromEvidenceTests(unittest.TestCase):
    """3-6. Every displayed value is read from evidence."""

    def setUp(self):
        self.source = APP.read_text(encoding="utf-8")

    def test_request_text_comes_from_evidence(self):
        self.assertRegex(self.source, r"""evidence\[['"]request_text['"]\]""")
        # The workflow's default request must not be reproduced in the panel.
        self.assertNotIn("Provision production PostgreSQL on AWS in us-east-1.", self.source)

    def test_parsed_intent_fields_come_from_evidence(self):
        for field in (
            "parsed_environment",
            "parsed_cloud",
            "parsed_region",
            "parsed_service",
            "parsed_high_availability",
            "parsed_backup_retention_days",
            "parsed_budget_monthly",
        ):
            self.assertIn(field, self.source)
            self.assertIn(field, demo_evidence.ALLOWED_FIELDS)

    def test_generated_terraform_fields_come_from_evidence(self):
        for field in (
            "terraform_resource_type",
            "terraform_multi_az",
            "terraform_encrypted",
            "terraform_backup_retention_days",
            "terraform_publicly_accessible",
            "terraform_managed_password",
            "terraform_hcl_preview",
        ):
            self.assertIn(field, self.source)
            self.assertIn(field, demo_evidence.ALLOWED_FIELDS)

    def test_plan_hash_is_displayed_from_evidence_and_validated(self):
        self.assertRegex(self.source, r"""evidence\[['"]terraform_plan_sha256['"]\]""")
        clean = demo_evidence.sanitize(VERIFIED)
        self.assertEqual(clean["terraform_plan_sha256"], HASH_A)
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(dict(VERIFIED, terraform_plan_sha256="not-a-hash"))

    def test_hcl_preview_keeps_the_managed_password_proof(self):
        clean = demo_evidence.sanitize(VERIFIED)
        self.assertIn("manage_master_user_password = true", clean["terraform_hcl_preview"])


class HumanBoundaryTests(unittest.TestCase):
    """7-13. The conditions that must hold before anything reads as approved."""

    def test_pre_sign_state_is_preserved(self):
        clean = demo_evidence.sanitize(VERIFIED)
        self.assertEqual(clean["pre_approval_state"], "AWAITING_HUMAN_APPROVAL")
        self.assertIs(clean["agent_may_sign"], False)
        self.assertIs(clean["agent_signed"], False)
        self.assertIs(clean["provisioning_allowed_before_approval"], False)

    def test_executed_is_required(self):
        for status in ("SENT", "COMPLETED", "SHARED", "IN PROGRESS", ""):
            with self.subTest(status=status):
                self.assertFalse(demo_evidence.is_verified(dict(VERIFIED, foxit_status=status)))

    def test_signer_must_match(self):
        self.assertFalse(demo_evidence.is_verified(dict(VERIFIED, signer_match=False)))

    def test_plan_hash_must_be_verified(self):
        self.assertFalse(
            demo_evidence.is_verified(dict(VERIFIED, terraform_plan_hash_verified=False))
        )

    def test_replanning_after_signature_blocks_verification(self):
        self.assertFalse(
            demo_evidence.is_verified(dict(VERIFIED, terraform_replanned_after_signature=True))
        )

    def test_signed_pdf_hash_is_required_for_approved(self):
        without = dict(VERIFIED)
        without.pop("signed_pdf_sha256")
        self.assertFalse(demo_evidence.is_verified(without))

    def test_apply_must_not_have_run(self):
        self.assertFalse(demo_evidence.is_verified(dict(VERIFIED, terraform_apply_ran=True)))

    def test_destroy_must_not_have_run(self):
        self.assertFalse(demo_evidence.is_verified(dict(VERIFIED, terraform_destroy_ran=True)))

    def test_a_signed_agent_is_never_verified(self):
        self.assertFalse(demo_evidence.is_verified(dict(VERIFIED, agent_signed=True)))

    def test_fallback_parser_blocks_verification(self):
        self.assertFalse(demo_evidence.is_verified(dict(VERIFIED, claude_fallback_used=True)))

    def test_failed_policy_blocks_verification(self):
        self.assertFalse(demo_evidence.is_verified(dict(VERIFIED, policy_result="FAIL")))

    def test_pending_run_is_not_verified(self):
        pending = dict(
            VERIFIED,
            foxit_status="SENT",
            human_signature_verified=False,
            signer_match=False,
            terraform_plan_hash_verified=False,
            final_audit_state="AWAITING_HUMAN_APPROVAL",
        )
        pending.pop("signed_pdf_sha256")
        self.assertFalse(demo_evidence.is_verified(pending))
        self.assertIsNone(demo_evidence.badges(pending))


class SensitiveContentTests(unittest.TestCase):
    """14. Identity-bearing evidence is rejected, not masked."""

    def test_unknown_keys_are_dropped(self):
        raw = dict(VERIFIED)
        raw.update({
            "foxit_folder_id": "35508167",
            "signer_email_field": "someone@example.com",
            "client_secret": "super-secret",
        })
        clean = demo_evidence.sanitize(raw)
        for dropped in ("foxit_folder_id", "signer_email_field", "client_secret"):
            self.assertNotIn(dropped, clean)

    def test_email_is_rejected(self):
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(dict(VERIFIED, request_text="approve for jane@example.com"))

    def test_signing_url_is_rejected(self):
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(
                dict(VERIFIED, foxit_status="EXECUTED https://na1.fusion.foxit.com/s/xyz")
            )

    def test_aws_account_id_is_rejected(self):
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(
                dict(VERIFIED, terraform_hcl_preview="# account 123456789012\n" + HCL)
            )

    def test_arn_is_rejected(self):
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(
                dict(VERIFIED, terraform_hcl_preview='kms_key_id = "arn:aws:kms:us-east-1:1234:key/x"')
            )

    def test_access_key_is_rejected(self):
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(
                dict(VERIFIED, terraform_hcl_preview='access_key = "AKIAIOSFODNN7EXAMPLE"')
            )

    def test_assigned_password_is_rejected(self):
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(
                dict(VERIFIED, terraform_hcl_preview='password = "hunter2"')
            )

    def test_terraform_state_is_rejected(self):
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(
                dict(VERIFIED, terraform_plan_summary="see terraform.tfstate for details")
            )

    def test_private_ip_is_rejected(self):
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(
                dict(VERIFIED, terraform_hcl_preview="# endpoint 10.0.4.17\n" + HCL)
            )

    def test_sensitive_content_inside_a_list_is_rejected(self):
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(
                dict(VERIFIED, requested_controls=["PostgreSQL", "notify jane@example.com"])
            )

    def test_sensitive_content_inside_a_rule_result_is_rejected(self):
        with self.assertRaises(demo_evidence.UnsafeEvidence):
            demo_evidence.sanitize(
                dict(
                    VERIFIED,
                    policy_rule_results=[
                        {"code": "APR-02", "description": "approver jane@example.com", "result": "PASS"}
                    ],
                )
            )


class RepositoryHygieneTests(unittest.TestCase):
    """15. No committed file can make the UI claim a verified run."""

    def test_any_committed_evidence_is_sanitized_and_complete(self):
        """Publishing a real run's record is the intended workflow, so this no
        longer forbids the file — it constrains it. Committed evidence must
        survive the sanitizer (carrying no identity) and describe a *complete*
        verified run, so a half-finished state can never be published as though
        it were approved.

        No test can tell a genuine artifact from a hand-written one; nothing in
        a repository can. That claim is protected procedurally instead: the file
        is downloaded from a workflow run, and DEMO_SCRIPT.md says in as many
        words not to write one by hand.
        """
        path = demo_evidence.DEFAULT_EVIDENCE_PATH
        if not path.exists():
            self.skipTest("no run evidence is published in this checkout")
        evidence = demo_evidence.load(path)  # raises UnsafeEvidence if it leaks
        self.assertTrue(
            demo_evidence.is_verified(evidence),
            "committed evidence must describe a complete verified run",
        )

    def test_round_trip_from_disk(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo-evidence.json"
            path.write_text(json.dumps(dict(VERIFIED, foxit_folder_id="35508167")), encoding="utf-8")
            loaded = demo_evidence.load(path)
            self.assertNotIn("foxit_folder_id", loaded)
            self.assertTrue(demo_evidence.is_verified(loaded))


if __name__ == "__main__":
    unittest.main()

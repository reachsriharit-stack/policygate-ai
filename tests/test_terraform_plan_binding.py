import unittest

from policygate.audit import build_pre_sign_audit, finalize_from_foxit_folder
from policygate.evidence import build_evidence_packet
from policygate.foxit_client import mock_handoff
from policygate.pdf_render import render_evidence_pdf
from policygate.planner import build_plan
from policygate.rules import evaluate
from policygate.schema import ChangeRequest


def make_request(**overrides) -> ChangeRequest:
    base = dict(
        request_id="PG-TEST-0001",
        requested_by="Demo Engineer",
        environment="production",
        cloud="aws",
        database_engine="postgresql",
        region="us-east-1",
        high_availability=True,
        encryption_at_rest=True,
        backup_retention_days=30,
        public_access=False,
        monthly_budget_usd=900,
        approver_name="Jane Smith",
        approver_email="jane@example.com",
    )
    base.update(overrides)
    return ChangeRequest(**base)


def make_policy_result():
    request = make_request()
    plan = build_plan(request)
    return evaluate(request, plan)


SAMPLE_TERRAFORM_PLAN = {
    "plan_summary": "Terraform will perform the following actions:\n\n  # aws_db_instance.policygate_db will be created\n\nPlan: 1 to add, 0 to change, 0 to destroy.",
    "plan_file_sha256": "planhash" * 8,
}


class EvidencePacketTerraformTests(unittest.TestCase):
    def test_terraform_plan_key_absent_when_not_provided(self):
        evidence = build_evidence_packet(make_policy_result())
        self.assertNotIn("terraform_plan", evidence)

    def test_terraform_plan_key_present_when_provided(self):
        evidence = build_evidence_packet(make_policy_result(), terraform_plan=SAMPLE_TERRAFORM_PLAN)
        self.assertEqual(evidence["terraform_plan"], SAMPLE_TERRAFORM_PLAN)

    def test_config_level_plan_sha256_unaffected_by_terraform_plan(self):
        """The existing config-level hash must not change meaning just
        because a terraform_plan was also attached — approval_gate.py's
        authorize_provisioning() depends on this hash staying config-only."""
        result = make_policy_result()
        without = build_evidence_packet(result)
        with_tf = build_evidence_packet(result, terraform_plan=SAMPLE_TERRAFORM_PLAN)
        self.assertEqual(without["plan_sha256"], with_tf["plan_sha256"])


class PdfRenderTerraformTests(unittest.TestCase):
    def test_renders_without_terraform_plan(self):
        evidence = build_evidence_packet(make_policy_result())
        pdf_bytes = render_evidence_pdf(evidence)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_renders_with_terraform_plan_and_is_larger(self):
        result = make_policy_result()
        evidence_without = build_evidence_packet(result)
        evidence_with = build_evidence_packet(result, terraform_plan=SAMPLE_TERRAFORM_PLAN)
        pdf_without = render_evidence_pdf(evidence_without)
        pdf_with = render_evidence_pdf(evidence_with)
        self.assertTrue(pdf_with.startswith(b"%PDF"))
        self.assertGreater(len(pdf_with), len(pdf_without))

    def test_states_the_workflow_state_it_stops_in(self):
        """An approval document should say where the agent halted, not leave a
        reader to infer it from the absence of a signature."""
        import base64
        import re
        import zlib

        evidence = build_evidence_packet(make_policy_result(), terraform_plan=SAMPLE_TERRAFORM_PLAN)
        pdf_bytes = render_evidence_pdf(evidence)

        text = ""
        for match in re.finditer(rb"stream\n(.*?)endstream", pdf_bytes, re.S):
            try:
                text += zlib.decompress(
                    base64.a85decode(match.group(1).strip(), adobe=True)
                ).decode("latin-1")
            except Exception:  # pragma: no cover - non-content streams
                continue

        self.assertIn("AWAITING_HUMAN_APPROVAL", text)
        self.assertIn("Workflow state", text)

    def test_handles_missing_plan_summary_gracefully(self):
        evidence = build_evidence_packet(
            make_policy_result(), terraform_plan={"plan_file_sha256": "abc"}
        )
        pdf_bytes = render_evidence_pdf(evidence)  # should not raise
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))


class AuditChainTerraformTests(unittest.TestCase):
    def test_pre_sign_audit_carries_plan_file_hash(self):
        evidence = build_evidence_packet(make_policy_result(), terraform_plan=SAMPLE_TERRAFORM_PLAN)
        handoff = mock_handoff("jane@example.com", evidence["request_id"])
        pre_sign = build_pre_sign_audit(evidence, b"fake pdf bytes", handoff)
        self.assertEqual(pre_sign["terraform_plan_file_sha256"], SAMPLE_TERRAFORM_PLAN["plan_file_sha256"])

    def test_pre_sign_audit_hash_is_none_without_terraform_plan(self):
        evidence = build_evidence_packet(make_policy_result())
        handoff = mock_handoff("jane@example.com", evidence["request_id"])
        pre_sign = build_pre_sign_audit(evidence, b"fake pdf bytes", handoff)
        self.assertIsNone(pre_sign["terraform_plan_file_sha256"])

    def test_final_audit_still_carries_plan_file_hash_after_signing(self):
        evidence = build_evidence_packet(make_policy_result(), terraform_plan=SAMPLE_TERRAFORM_PLAN)
        handoff = mock_handoff("jane@example.com", evidence["request_id"])
        pre_sign = build_pre_sign_audit(evidence, b"fake pdf bytes", handoff)
        folder_response = {
            "folder": {
                "folderId": handoff.folder_id,
                "folderStatus": "EXECUTED",
                "folderRecipientParties": [
                    {"partyDetails": {"emailId": "jane@example.com"}}
                ],
            }
        }
        final = finalize_from_foxit_folder(pre_sign, folder_response, b"signed pdf bytes")
        self.assertEqual(final["terraform_plan_file_sha256"], SAMPLE_TERRAFORM_PLAN["plan_file_sha256"])
        self.assertEqual(final["state"], "APPROVED")


if __name__ == "__main__":
    unittest.main()

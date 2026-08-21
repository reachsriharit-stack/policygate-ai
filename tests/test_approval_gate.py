import unittest

from policygate.provisioning.approval_gate import ProvisioningNotAuthorized, authorize_provisioning


def _evidence(plan_sha256="deadbeef" * 8):
    return {
        "request_id": "PG-TEST-0001",
        "plan_sha256": plan_sha256,
        "proposed_plan": {"cloud": "aws"},  # content doesn't matter, hash does
    }


def _final_audit(**overrides):
    audit = {
        "request_id": "PG-TEST-0001",
        "state": "APPROVED",
        "agent_may_sign": False,
        "foxit_folder_status": "EXECUTED",
        "signed_pdf_sha256": "abc123",
        "signer_email": "jane@example.com",
        "expected_signer_email": "jane@example.com",
        "verified_signer_email": "jane@example.com",
        "plan_sha256": None,  # filled in per-test to match/mismatch evidence
    }
    audit.update(overrides)
    return audit


class ApprovalGateTests(unittest.TestCase):
    def _matching_pair(self):
        evidence = _evidence()
        from policygate import evidence as evidence_module
        real_hash = evidence_module.sha256_json(evidence["proposed_plan"])
        evidence["plan_sha256"] = real_hash
        audit = _final_audit(plan_sha256=real_hash)
        return evidence, audit

    def test_fully_valid_pair_is_authorized(self):
        evidence, audit = self._matching_pair()
        self.assertTrue(authorize_provisioning(audit, evidence))

    def test_rejects_mismatched_request_ids(self):
        evidence, audit = self._matching_pair()
        audit["request_id"] = "PG-DIFFERENT"
        with self.assertRaises(ProvisioningNotAuthorized):
            authorize_provisioning(audit, evidence)

    def test_rejects_non_approved_state(self):
        evidence, audit = self._matching_pair()
        audit["state"] = "AWAITING_HUMAN_APPROVAL"
        with self.assertRaises(ProvisioningNotAuthorized):
            authorize_provisioning(audit, evidence)

    def test_rejects_agent_may_sign_true(self):
        evidence, audit = self._matching_pair()
        audit["agent_may_sign"] = True
        with self.assertRaises(ProvisioningNotAuthorized):
            authorize_provisioning(audit, evidence)

    def test_rejects_folder_not_executed(self):
        evidence, audit = self._matching_pair()
        audit["foxit_folder_status"] = "SENT"
        with self.assertRaises(ProvisioningNotAuthorized):
            authorize_provisioning(audit, evidence)

    def test_rejects_missing_signed_pdf_hash(self):
        evidence, audit = self._matching_pair()
        audit["signed_pdf_sha256"] = None
        with self.assertRaises(ProvisioningNotAuthorized):
            authorize_provisioning(audit, evidence)

    def test_rejects_missing_verified_signer_email(self):
        evidence, audit = self._matching_pair()
        audit["verified_signer_email"] = ""
        with self.assertRaises(ProvisioningNotAuthorized):
            authorize_provisioning(audit, evidence)

    def test_rejects_verified_signer_mismatch(self):
        evidence, audit = self._matching_pair()
        audit["verified_signer_email"] = "mallory@example.com"
        with self.assertRaises(ProvisioningNotAuthorized):
            authorize_provisioning(audit, evidence)

    def test_rejects_plan_hash_mismatch_even_with_everything_else_valid(self):
        """The critical case: plan was edited/regenerated after signing."""
        evidence, audit = self._matching_pair()
        audit["plan_sha256"] = "totally-different-hash"
        with self.assertRaises(ProvisioningNotAuthorized):
            authorize_provisioning(audit, evidence)


if __name__ == "__main__":
    unittest.main()

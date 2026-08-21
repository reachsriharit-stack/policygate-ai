import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from policygate.provision import apply_approved
from policygate.provisioning.terraform_runner import hash_plan_file


def _evidence():
    return {
        "request_id": "PG-TEST-0001",
        "plan_sha256": "configlevelhash" * 4,
        "proposed_plan": {"cloud": "aws"},
    }


def _matching_final_audit(evidence, workdir):
    from policygate import evidence as evidence_module

    approved_plan_hash = hash_plan_file(workdir)
    return {
        "request_id": evidence["request_id"],
        "plan_sha256": evidence_module.sha256_json(evidence["proposed_plan"]),
        "state": "APPROVED",
        "agent_may_sign": False,
        "foxit_folder_status": "EXECUTED",
        "signed_pdf_sha256": "abc123",
        "signer_email": "jane@example.com",
        "expected_signer_email": "jane@example.com",
        "verified_signer_email": "jane@example.com",
        "terraform_plan_file_sha256": approved_plan_hash,
    }


class ApplyNeverRePlansTests(unittest.TestCase):
    """Regression tests for the bug where --apply regenerated the plan
    (overwriting the approved file) before checking authorization."""

    def test_apply_approved_never_calls_run_plan(self):
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            (workdir / "tfplan").write_bytes(b"the exact plan the human approved")
            evidence = _evidence()
            final_audit = _matching_final_audit(evidence, workdir)

            with patch("policygate.provision.terraform_runner.run_plan") as mock_plan, \
                 patch("policygate.provision.terraform_runner.run_init") as mock_init, \
                 patch("policygate.provision.terraform_runner.run_validate") as mock_validate, \
                 patch("policygate.provision.terraform_generator.write_terraform") as mock_write_tf, \
                 patch("policygate.provision.terraform_runner.run_apply") as mock_apply:
                apply_approved(evidence, final_audit, workdir)

            mock_plan.assert_not_called()
            mock_init.assert_not_called()
            mock_validate.assert_not_called()
            mock_write_tf.assert_not_called()
            mock_apply.assert_called_once()

    def test_apply_approved_does_not_overwrite_the_plan_file(self):
        """Even if apply_approved touched the plan file as a side effect,
        this would catch it: the file's bytes must be byte-identical
        before and after the call."""
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            original_bytes = b"the exact plan the human approved"
            (workdir / "tfplan").write_bytes(original_bytes)
            evidence = _evidence()
            final_audit = _matching_final_audit(evidence, workdir)

            with patch("policygate.provision.terraform_runner.run_apply"):
                apply_approved(evidence, final_audit, workdir)

            self.assertEqual((workdir / "tfplan").read_bytes(), original_bytes)


class NoFallbackForUnboundApprovalTests(unittest.TestCase):
    """Regression tests for the bug where a signed audit missing
    terraform_plan_file_sha256 fell back to trusting a freshly-generated
    manifest instead of being flatly denied."""

    def test_apply_denied_when_audit_has_no_bound_plan_hash(self):
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            (workdir / "tfplan").write_bytes(b"some plan file that happens to exist")
            evidence = _evidence()
            final_audit = _matching_final_audit(evidence, workdir)
            final_audit["terraform_plan_file_sha256"] = None  # not bound at signing time

            with patch("policygate.provision.terraform_runner.run_plan") as mock_plan, \
                 patch("policygate.provision.terraform_runner.run_apply") as mock_apply, \
                 self.assertRaises(SystemExit):
                apply_approved(evidence, final_audit, workdir)

            mock_plan.assert_not_called()
            mock_apply.assert_not_called()

    def test_apply_denied_does_not_consult_any_manifest_file(self):
        """Even if a manifest with a matching hash exists in workdir (e.g.
        left over from an earlier plan_preview() run), apply_approved()
        must not use it as a substitute for a signed plan hash."""
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            (workdir / "tfplan").write_bytes(b"some plan file that happens to exist")
            plan_hash = hash_plan_file(workdir)

            # A manifest sitting in workdir with a hash that WOULD match —
            # this must be irrelevant to an audit that never bound a hash.
            manifest_path = workdir / "PG-TEST-0001-terraform-plan-manifest.json"
            manifest_path.write_text(json.dumps({"terraform_plan_file_sha256": plan_hash}))

            evidence = _evidence()
            final_audit = _matching_final_audit(evidence, workdir)
            final_audit["terraform_plan_file_sha256"] = None

            with patch("policygate.provision.terraform_runner.run_apply") as mock_apply, \
                 self.assertRaises(SystemExit):
                apply_approved(evidence, final_audit, workdir)

            mock_apply.assert_not_called()


if __name__ == "__main__":
    unittest.main()

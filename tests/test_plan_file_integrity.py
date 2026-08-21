import json
import tempfile
import unittest
from pathlib import Path

from policygate.provisioning.approval_gate import (
    ProvisioningNotAuthorized,
    verify_plan_file_integrity,
)
from policygate.provisioning.terraform_generator import write_plan_manifest
from policygate.provisioning.terraform_runner import hash_plan_file


def _evidence():
    return {
        "request_id": "PG-TEST-0001",
        "plan_sha256": "configlevelhash" * 4,
        "proposed_plan": {"cloud": "aws"},
    }


class PlanFileIntegrityTests(unittest.TestCase):
    def test_hash_plan_file_is_deterministic_for_same_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            plan_path = Path(td) / "tfplan"
            plan_path.write_bytes(b"fake binary plan content")
            self.assertEqual(hash_plan_file(td), hash_plan_file(td))

    def test_hash_plan_file_changes_if_content_changes(self):
        with tempfile.TemporaryDirectory() as td:
            plan_path = Path(td) / "tfplan"
            plan_path.write_bytes(b"plan A")
            hash_a = hash_plan_file(td)
            plan_path.write_bytes(b"plan B - different resources")
            hash_b = hash_plan_file(td)
            self.assertNotEqual(hash_a, hash_b)

    def test_hash_plan_file_raises_if_missing(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                hash_plan_file(td)

    def test_manifest_records_both_hash_layers(self):
        with tempfile.TemporaryDirectory() as td:
            manifest_path = write_plan_manifest(
                _evidence(), "planfilehash123", "Plan: 1 to add, 0 to change, 0 to destroy.", td
            )
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["config_plan_sha256"], "configlevelhash" * 4)
            self.assertEqual(manifest["terraform_plan_file_sha256"], "planfilehash123")
            self.assertIn("1 to add", manifest["plan_summary"])

    def test_verify_plan_file_integrity_passes_when_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "tfplan").write_bytes(b"the approved plan")
            current_hash = hash_plan_file(td)
            manifest = {"terraform_plan_file_sha256": current_hash}
            self.assertTrue(verify_plan_file_integrity(manifest, td))

    def test_verify_plan_file_integrity_fails_if_replanned_differently(self):
        """The exact scenario this exists to catch: someone re-ran `terraform
        plan` after approval (state drift, provider update, whatever) and the
        file on disk is no longer what was signed off on."""
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "tfplan").write_bytes(b"the approved plan")
            approved_hash = hash_plan_file(td)
            manifest = {"terraform_plan_file_sha256": approved_hash}

            # Simulate a re-plan producing a different result.
            (Path(td) / "tfplan").write_bytes(b"a different plan after re-planning")

            with self.assertRaises(ProvisioningNotAuthorized):
                verify_plan_file_integrity(manifest, td)

    def test_verify_plan_file_integrity_fails_if_manifest_incomplete(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "tfplan").write_bytes(b"some plan")
            with self.assertRaises(ProvisioningNotAuthorized):
                verify_plan_file_integrity({}, td)


if __name__ == "__main__":
    unittest.main()

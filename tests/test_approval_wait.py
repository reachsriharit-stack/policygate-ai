import unittest
from unittest.mock import Mock, patch

from policygate.approval_wait import (
    ApprovalTimeout,
    FolderMismatch,
    assert_plan_hash_unchanged,
    wait_for_executed_folder,
)
from policygate.audit import build_pre_sign_audit, finalize_from_foxit_folder
from policygate.evidence import build_evidence_packet
from policygate.foxit_client import mock_handoff
from policygate.planner import build_plan
from policygate.rules import evaluate
from policygate.schema import ChangeRequest

FOLDER_ID = "35508167"
SIGNER = "approver@example.com"
PLAN_SHA = "a" * 64


def folder_response(status, folder_id=FOLDER_ID, signer=SIGNER):
    return {
        "folder": {
            "folderId": folder_id,
            "folderStatus": status,
            "folderRecipientParties": [
                {"partyDetails": {"emailId": signer}, "contractPermissions": "FILL_FIELDS_AND_SIGN"}
            ],
        }
    }


class ScriptedClient:
    """Records every method the waiter touches, so a test can prove the wait
    is read-only."""

    def __init__(self, statuses, folder_id=FOLDER_ID, signer=SIGNER):
        self.statuses = list(statuses)
        self.folder_id = folder_id
        self.signer = signer
        self.calls = []

    def get_folder(self, folder_id):
        self.calls.append(("get_folder", folder_id))
        status = self.statuses.pop(0) if self.statuses else "SENT"
        return folder_response(status, self.folder_id, self.signer)

    def download_document(self, *a, **k):  # pragma: no cover - must not be called
        self.calls.append(("download_document", a))
        raise AssertionError("the waiter must not download anything")

    def create_human_approval_draft(self, *a, **k):  # pragma: no cover
        self.calls.append(("create_human_approval_draft", a))
        raise AssertionError("the waiter must not create a folder")


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def pre_sign_audit(plan_sha=PLAN_SHA, signer=SIGNER):
    request = ChangeRequest(
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
        approver_name="Human Approver",
        approver_email=signer,
    )
    result = evaluate(request, build_plan(request))
    evidence = build_evidence_packet(
        result,
        terraform_plan={"plan_summary": "Plan: 1 to add, 0 to change, 0 to destroy.",
                        "plan_file_sha256": plan_sha},
    )
    handoff = mock_handoff(signer, evidence["request_id"])
    handoff.folder_id = FOLDER_ID
    return evidence, build_pre_sign_audit(evidence, b"%PDF-unsigned", handoff)


class ExecutedAllowsVerificationTests(unittest.TestCase):
    def test_executed_returns_the_folder_for_verification(self):
        client = ScriptedClient(["SENT", "SENT", "EXECUTED"])
        clock = FakeClock()
        response = wait_for_executed_folder(
            client, FOLDER_ID, timeout_seconds=900, poll_interval_seconds=10,
            sleep=clock.sleep, monotonic=clock.monotonic,
        )
        self.assertEqual(response["folder"]["folderStatus"], "EXECUTED")
        self.assertEqual(clock.slept, [10, 10])

        evidence, pre_sign = pre_sign_audit()
        final = finalize_from_foxit_folder(pre_sign, response, b"%PDF-signed")
        self.assertEqual(final["state"], "APPROVED")
        self.assertEqual(final["verified_signer_email"], SIGNER)

    def test_wait_only_reads_folder_status(self):
        client = ScriptedClient(["EXECUTED"])
        clock = FakeClock()
        wait_for_executed_folder(
            client, FOLDER_ID, sleep=clock.sleep, monotonic=clock.monotonic
        )
        self.assertEqual([name for name, _ in client.calls], ["get_folder"])


class IntermediateStatusTests(unittest.TestCase):
    def test_completed_does_not_finalize(self):
        """COMPLETED is not an executed signature and must never approve."""
        _, pre_sign = pre_sign_audit()
        with self.assertRaises(ValueError):
            finalize_from_foxit_folder(pre_sign, folder_response("COMPLETED"), b"%PDF-signed")

    def test_completed_and_sent_keep_waiting_until_timeout(self):
        client = ScriptedClient(["SENT", "SHARED", "COMPLETED", "COMPLETED"])
        clock = FakeClock()
        with self.assertRaises(ApprovalTimeout) as ctx:
            wait_for_executed_folder(
                client, FOLDER_ID, timeout_seconds=30, poll_interval_seconds=10,
                sleep=clock.sleep, monotonic=clock.monotonic,
            )
        self.assertIn("COMPLETED", str(ctx.exception))


class SignerAndFolderTests(unittest.TestCase):
    def test_wrong_signer_fails(self):
        _, pre_sign = pre_sign_audit()
        response = folder_response("EXECUTED", signer="someone-else@example.com")
        with self.assertRaises(ValueError) as ctx:
            finalize_from_foxit_folder(pre_sign, response, b"%PDF-signed")
        self.assertIn("signer mismatch", str(ctx.exception).lower())

    def test_different_folder_fails_while_waiting(self):
        client = ScriptedClient(["EXECUTED"], folder_id="99999999")
        clock = FakeClock()
        with self.assertRaises(FolderMismatch):
            wait_for_executed_folder(
                client, FOLDER_ID, sleep=clock.sleep, monotonic=clock.monotonic
            )

    def test_different_folder_fails_at_finalization(self):
        _, pre_sign = pre_sign_audit()
        with self.assertRaises(ValueError):
            finalize_from_foxit_folder(
                pre_sign, folder_response("EXECUTED", folder_id="99999999"), b"%PDF-signed"
            )


class TimeoutFailsClosedTests(unittest.TestCase):
    def test_timeout_raises_and_leaves_the_audit_pending(self):
        client = ScriptedClient(["SENT"] * 100)
        clock = FakeClock()
        _, pre_sign = pre_sign_audit()
        with self.assertRaises(ApprovalTimeout):
            wait_for_executed_folder(
                client, FOLDER_ID, timeout_seconds=900, poll_interval_seconds=10,
                sleep=clock.sleep, monotonic=clock.monotonic,
            )
        # Nothing about the pre-sign record may have moved.
        self.assertEqual(pre_sign["state"], "AWAITING_HUMAN_APPROVAL")
        self.assertIsNone(pre_sign["verified_signer_email"])
        self.assertIs(pre_sign["agent_may_sign"], False)
        self.assertEqual(sum(clock.slept), 900)


class PlanHashTests(unittest.TestCase):
    def test_unchanged_plan_hash_passes(self):
        _, pre_sign = pre_sign_audit()
        final = finalize_from_foxit_folder(pre_sign, folder_response("EXECUTED"), b"%PDF-signed")
        assert_plan_hash_unchanged(final, PLAN_SHA)  # must not raise

    def test_changed_plan_hash_fails(self):
        _, pre_sign = pre_sign_audit()
        final = finalize_from_foxit_folder(pre_sign, folder_response("EXECUTED"), b"%PDF-signed")
        final["terraform_plan_file_sha256"] = "b" * 64
        with self.assertRaises(ValueError) as ctx:
            assert_plan_hash_unchanged(final, PLAN_SHA)
        self.assertIn("changed across the human approval boundary", str(ctx.exception))


class NoProvisioningWhileWaitingTests(unittest.TestCase):
    def test_no_terraform_apply_or_destroy_occurs_while_waiting(self):
        import policygate.provisioning.terraform_runner as tf_runner

        with patch.object(tf_runner, "run_apply", Mock()) as apply_mock, \
             patch.object(tf_runner, "run_destroy", Mock()) as destroy_mock, \
             patch.object(tf_runner, "_run", Mock()) as run_mock:
            client = ScriptedClient(["SENT", "COMPLETED", "EXECUTED"])
            clock = FakeClock()
            wait_for_executed_folder(
                client, FOLDER_ID, sleep=clock.sleep, monotonic=clock.monotonic
            )
            apply_mock.assert_not_called()
            destroy_mock.assert_not_called()
            run_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()

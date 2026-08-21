import os
import unittest
from unittest.mock import patch

from policygate.schema import WorkflowState
from policygate.workflow import run_workflow


class WorkflowTests(unittest.TestCase):
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "FOXIT_ESIGN_CLIENT_ID": "", "FOXIT_ESIGN_CLIENT_SECRET": ""}, clear=False)
    def test_pass_stops_at_human_boundary(self):
        result = run_workflow(
            "prod Postgres on AWS, HA required, 30-day backups, $900/month. Approver: Jane Smith",
            approver_email="jane@example.com",
        )
        self.assertEqual(result.state, WorkflowState.AWAITING_HUMAN_APPROVAL)
        self.assertTrue(result.policy_result.passed)
        self.assertFalse(result.audit_record["agent_may_sign"])
        self.assertTrue(result.pdf_bytes.startswith(b"%PDF"))

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "FOXIT_ESIGN_CLIENT_ID": "", "FOXIT_ESIGN_CLIENT_SECRET": ""}, clear=False)
    def test_fail_does_not_generate_pdf_or_handoff(self):
        result = run_workflow(
            "production Postgres, single AZ, no encryption, 7-day backups, public access enabled, $900. Approver: Jane Smith"
        )
        self.assertEqual(result.state, WorkflowState.BLOCKED)
        self.assertIsNone(result.pdf_bytes)
        self.assertIsNone(result.handoff)

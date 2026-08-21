import os
import unittest
from unittest.mock import patch

from policygate.runtime_status import enforce_submission_mode, get_runtime_status


class SubmissionModeTests(unittest.TestCase):
    @patch.dict(os.environ, {"POLICYGATE_SUBMISSION_MODE": "false"}, clear=False)
    def test_normal_mode_does_not_require_live_credentials(self):
        enforce_submission_mode(False)

    @patch.dict(
        os.environ,
        {
            "POLICYGATE_SUBMISSION_MODE": "true",
            "ANTHROPIC_API_KEY": "",
            "FOXIT_ESIGN_CLIENT_ID": "",
            "FOXIT_ESIGN_CLIENT_SECRET": "",
            "POLICYGATE_FOXIT_SEND_NOW": "false",
            "POLICYGATE_EMBEDDED_SIGNING": "false",
        },
        clear=False,
    )
    def test_submission_mode_rejects_mock_paths(self):
        with self.assertRaises(RuntimeError):
            enforce_submission_mode(False)

    @patch.dict(
        os.environ,
        {
            "POLICYGATE_SUBMISSION_MODE": "true",
            "ANTHROPIC_API_KEY": "test-key",
            "POLICYGATE_ALLOW_AI_FALLBACK": "false",
            "FOXIT_ESIGN_CLIENT_ID": "id",
            "FOXIT_ESIGN_CLIENT_SECRET": "secret",
            "FOXIT_CLOUD_API_CLIENT_ID": "pdf-id",
            "FOXIT_CLOUD_API_CLIENT_SECRET": "pdf-secret",
            "POLICYGATE_FOXIT_SEND_NOW": "true",
            "POLICYGATE_EMBEDDED_SIGNING": "false",
        },
        clear=False,
    )
    def test_submission_mode_accepts_live_configuration(self):
        enforce_submission_mode(True)


    @patch.dict(
        os.environ,
        {
            "POLICYGATE_SUBMISSION_MODE": "true",
            "ANTHROPIC_API_KEY": "test-key",
            "POLICYGATE_ALLOW_AI_FALLBACK": "true",
            "FOXIT_ESIGN_CLIENT_ID": "id",
            "FOXIT_ESIGN_CLIENT_SECRET": "secret",
            "FOXIT_CLOUD_API_CLIENT_ID": "pdf-id",
            "FOXIT_CLOUD_API_CLIENT_SECRET": "pdf-secret",
            "POLICYGATE_FOXIT_SEND_NOW": "true",
            "POLICYGATE_EMBEDDED_SIGNING": "false",
        },
        clear=False,
    )
    def test_submission_mode_rejects_ai_fallback(self):
        with self.assertRaises(RuntimeError):
            enforce_submission_mode(True)

    @patch.dict(
        os.environ,
        {
            "POLICYGATE_SUBMISSION_MODE": "true",
            "ANTHROPIC_API_KEY": "test-key",
            "POLICYGATE_ALLOW_AI_FALLBACK": "false",
            "FOXIT_ESIGN_CLIENT_ID": "id",
            "FOXIT_ESIGN_CLIENT_SECRET": "secret",
            "FOXIT_CLOUD_API_CLIENT_ID": "pdf-id",
            "FOXIT_CLOUD_API_CLIENT_SECRET": "pdf-secret",
            "POLICYGATE_FOXIT_SEND_NOW": "true",
            "POLICYGATE_EMBEDDED_SIGNING": "true",
        },
        clear=False,
    )
    def test_submission_mode_rejects_two_signing_routes(self):
        with self.assertRaises(RuntimeError):
            enforce_submission_mode(True)

    @patch.dict(
        os.environ,
        {
            "ANTHROPIC_API_KEY": "test-key",
            "FOXIT_ESIGN_CLIENT_ID": "id",
            "FOXIT_ESIGN_CLIENT_SECRET": "secret",
            "FOXIT_CLOUD_API_CLIENT_ID": "pdf-id",
            "FOXIT_CLOUD_API_CLIENT_SECRET": "pdf-secret",
            "POLICYGATE_INCLUDE_TERRAFORM_PLAN": "true",
        },
        clear=False,
    )
    def test_runtime_status_makes_live_vs_mock_visible(self):
        status = get_runtime_status()
        self.assertEqual(status.claude, "LIVE")
        self.assertEqual(status.foxit_esign, "LIVE")
        self.assertTrue(status.foxit_mcp.startswith("CONFIGURED"))
        self.assertEqual(status.terraform_plan, "LIVE PLAN")


if __name__ == "__main__":
    unittest.main()

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

class DeveloperPlatformSubmissionModeTests(unittest.TestCase):
    """Submission mode must judge eSign by the transport foxit_client will use,
    otherwise a fully live gateway setup reads as a mock."""

    LIVE_GATEWAY = {
        "POLICYGATE_SUBMISSION_MODE": "true",
        "ANTHROPIC_API_KEY": "test-key",
        "POLICYGATE_ALLOW_AI_FALLBACK": "false",
        "FOXIT_ESIGN_TRANSPORT": "developer_platform",
        "FOXIT_CLOUD_API_CLIENT_ID": "cloud-id",
        "FOXIT_CLOUD_API_CLIENT_SECRET": "cloud-secret",
        "FOXIT_ESIGN_CLIENT_ID": "",
        "FOXIT_ESIGN_CLIENT_SECRET": "",
        "POLICYGATE_FOXIT_SEND_NOW": "true",
        "POLICYGATE_EMBEDDED_SIGNING": "false",
    }

    @patch.dict(os.environ, LIVE_GATEWAY, clear=False)
    def test_gateway_credentials_satisfy_submission_mode(self):
        enforce_submission_mode(True)  # must not raise

    @patch.dict(os.environ, LIVE_GATEWAY, clear=False)
    def test_gateway_credentials_report_esign_live(self):
        self.assertEqual(get_runtime_status(True).foxit_esign, "LIVE")

    @patch.dict(
        os.environ,
        {**LIVE_GATEWAY, "FOXIT_CLOUD_API_CLIENT_ID": "", "FOXIT_CLOUD_API_CLIENT_SECRET": ""},
        clear=False,
    )
    def test_gateway_transport_without_its_credentials_is_rejected(self):
        with self.assertRaises(RuntimeError):
            enforce_submission_mode(True)

    @patch.dict(
        os.environ,
        {
            **LIVE_GATEWAY,
            "FOXIT_ESIGN_TRANSPORT": "esign_oauth",
            "FOXIT_ESIGN_CLIENT_ID": "",
            "FOXIT_ESIGN_CLIENT_SECRET": "",
        },
        clear=False,
    )
    def test_portal_transport_still_requires_portal_credentials(self):
        # Gateway credentials are present but unused by this transport.
        with self.assertRaises(RuntimeError):
            enforce_submission_mode(True)



if __name__ == "__main__":
    unittest.main()

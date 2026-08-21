import unittest

from policygate.audit import (
    finalize_from_foxit_folder,
    finalize_from_foxit_webhook,
    verify_foxit_webhook_signature,
)


class AuditFinalizationTests(unittest.TestCase):
    def setUp(self):
        self.pre = {
            "request_id": "PG-1",
            "foxit_folder_id": "123",
            "signer_email": "jane@example.com",
            "expected_signer_email": "jane@example.com",
            "state": "AWAITING_HUMAN_APPROVAL",
            "agent_may_sign": False,
        }

    def _folder(self, folder_id=123, status="EXECUTED", email="jane@example.com"):
        return {
            "folderId": folder_id,
            "folderStatus": status,
            "folderRecipientParties": [
                {"partyDetails": {"emailId": email}}
            ],
        }

    def test_webhook_completed_is_not_final(self):
        payload = {
            "event_name": "folder_completed",
            "event_date": 123456,
            "data": {"folder": self._folder()},
        }
        with self.assertRaises(ValueError):
            finalize_from_foxit_webhook(self.pre, payload)

    def test_webhook_requires_same_folder(self):
        payload = {
            "event_name": "folder_executed",
            "event_date": 123456,
            "data": {"folder": self._folder(folder_id=999)},
        }
        with self.assertRaises(ValueError):
            finalize_from_foxit_webhook(self.pre, payload)

    def test_webhook_same_folder_and_signer_can_finalize(self):
        payload = {
            "event_name": "folder_executed",
            "event_date": 123456,
            "data": {
                "folder": self._folder(),
                "signing_party": {"emailId": "jane@example.com"},
            },
        }
        final = finalize_from_foxit_webhook(self.pre, payload, b"signed")
        self.assertEqual(final["state"], "APPROVED")
        self.assertEqual(final["verified_signer_email"], "jane@example.com")
        self.assertIn("signed_pdf_sha256", final)

    def test_webhook_requires_executed_folder_status(self):
        payload = {
            "event_name": "folder_executed",
            "event_date": 123456,
            "data": {"folder": self._folder(status="COMPLETED")},
        }
        with self.assertRaises(ValueError):
            finalize_from_foxit_webhook(self.pre, payload)


    def test_webhook_requires_signed_pdf_before_approval(self):
        payload = {
            "event_name": "folder_executed",
            "event_date": 123456,
            "data": {
                "folder": self._folder(),
                "signing_party": {"emailId": "jane@example.com"},
            },
        }
        with self.assertRaises(ValueError):
            finalize_from_foxit_webhook(self.pre, payload)

    def test_webhook_rejects_wrong_signer(self):
        payload = {
            "event_name": "folder_executed",
            "event_date": 123456,
            "data": {
                "folder": self._folder(),
                "signing_party": {"emailId": "mallory@example.com"},
            },
        }
        with self.assertRaises(ValueError):
            finalize_from_foxit_webhook(self.pre, payload, b"signed")

    def test_polling_requires_executed_status(self):
        response = {"folder": self._folder(status="SHARED")}
        with self.assertRaises(ValueError):
            finalize_from_foxit_folder(self.pre, response, b"signed")

    def test_polling_executes_same_folder_and_signer(self):
        response = {"folder": self._folder()}
        final = finalize_from_foxit_folder(self.pre, response, b"signed")
        self.assertEqual(final["state"], "APPROVED")
        self.assertEqual(final["foxit_folder_status"], "EXECUTED")
        self.assertEqual(final["verified_signer_email"], "jane@example.com")
        self.assertFalse(final["agent_may_sign"])

    def test_polling_rejects_recipient_mismatch(self):
        response = {"folder": self._folder(email="mallory@example.com")}
        with self.assertRaises(ValueError):
            finalize_from_foxit_folder(self.pre, response, b"signed")


class FoxitWebhookSignatureTests(unittest.TestCase):
    def test_valid_signature(self):
        import base64
        import hashlib
        import hmac

        body = b'{"event_name":"folder_executed"}'
        secret = "demo-webhook-secret"
        signature = base64.b64encode(
            hmac.new(secret.encode(), body, hashlib.sha256).digest()
        ).decode("ascii")
        self.assertTrue(verify_foxit_webhook_signature(body, signature, secret))

    def test_tampered_body_rejected(self):
        import base64
        import hashlib
        import hmac

        body = b'{"event_name":"folder_executed"}'
        secret = "demo-webhook-secret"
        signature = base64.b64encode(
            hmac.new(secret.encode(), body, hashlib.sha256).digest()
        ).decode("ascii")
        self.assertFalse(
            verify_foxit_webhook_signature(body + b" ", signature, secret)
        )

    def test_missing_inputs_rejected(self):
        self.assertFalse(verify_foxit_webhook_signature(b"body", None, "secret"))
        self.assertFalse(verify_foxit_webhook_signature(b"body", "sig", None))



if __name__ == "__main__":
    unittest.main()

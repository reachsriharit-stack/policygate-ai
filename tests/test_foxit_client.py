import json
import unittest
from unittest.mock import Mock, patch

from policygate.foxit_client import FoxitESignClient


class FoxitClientTests(unittest.TestCase):
    @patch.dict("os.environ", {
        "FOXIT_ESIGN_BASE_URL": "https://na1.foxitesign.foxit.com",
        "FOXIT_ESIGN_CLIENT_ID": "id",
        "FOXIT_ESIGN_CLIENT_SECRET": "secret",
    }, clear=False)
    def test_uses_documented_token_and_createfolder_endpoints(self):
        session = Mock()
        token_response = Mock()
        token_response.json.return_value = {"access_token": "TOKEN"}
        token_response.raise_for_status.return_value = None
        folder_response = Mock()
        folder_response.json.return_value = {"folder": {"folderId": 123}}
        folder_response.raise_for_status.return_value = None
        session.post.side_effect = [token_response, folder_response]

        client = FoxitESignClient(session=session)
        handoff = client.create_human_approval_draft(
            b"%PDF-demo", "Jane Smith", "jane@example.com", "PG-1"
        )
        self.assertEqual(handoff.folder_id, "123")
        self.assertTrue(session.post.call_args_list[0].args[0].endswith("/api/oauth2/access_token"))
        self.assertTrue(session.post.call_args_list[1].args[0].endswith("/api/folders/createfolder"))
        payload = session.post.call_args_list[1].kwargs["json"]
        self.assertFalse(payload["sendNow"])
        self.assertTrue(payload["processTextTags"])
        self.assertNotIn("signNow", payload)

    @patch.dict("os.environ", {
        "FOXIT_ESIGN_BASE_URL": "https://na1.foxitesign.foxit.com",
        "FOXIT_ESIGN_CLIENT_ID": "id",
        "FOXIT_ESIGN_CLIENT_SECRET": "secret",
    }, clear=False)
    def test_can_explicitly_route_invitation_without_signing(self):
        session = Mock()
        token_response = Mock()
        token_response.json.return_value = {"access_token": "TOKEN"}
        token_response.raise_for_status.return_value = None
        folder_response = Mock()
        folder_response.json.return_value = {"folder": {"folderId": 123}}
        folder_response.raise_for_status.return_value = None
        session.post.side_effect = [token_response, folder_response]

        client = FoxitESignClient(session=session)
        client.create_human_approval_draft(
            b"%PDF-demo", "Jane Smith", "jane@example.com", "PG-1", send_now=True
        )
        payload = session.post.call_args_list[1].kwargs["json"]
        self.assertTrue(payload["sendNow"])
        self.assertNotIn("signature", payload)


    @patch.dict("os.environ", {
        "FOXIT_ESIGN_BASE_URL": "https://na1.foxitesign.foxit.com",
        "FOXIT_ESIGN_CLIENT_ID": "id",
        "FOXIT_ESIGN_CLIENT_SECRET": "secret",
    }, clear=False)
    def test_embedded_signing_creates_human_session_without_agent_signature(self):
        session = Mock()
        token_response = Mock()
        token_response.json.return_value = {"access_token": "TOKEN"}
        token_response.raise_for_status.return_value = None
        folder_response = Mock()
        folder_response.json.return_value = {
            "folder": {"folderId": 123},
            "embeddedSigningSessions": [
                {"embeddedSessionURL": "https://sign.example/human-session"}
            ],
        }
        folder_response.raise_for_status.return_value = None
        session.post.side_effect = [token_response, folder_response]

        client = FoxitESignClient(session=session)
        handoff = client.create_human_approval_draft(
            b"%PDF-demo",
            "Jane Smith",
            "jane@example.com",
            "PG-1",
            create_embedded_session=True,
        )

        payload = session.post.call_args_list[1].kwargs["json"]
        self.assertTrue(payload["createEmbeddedSigningSession"])
        self.assertEqual(payload["embeddedSignersEmailIds"], ["jane@example.com"])
        self.assertNotIn("signature", payload)
        self.assertNotIn("signNow", payload)
        self.assertEqual(handoff.embedded_session_url, "https://sign.example/human-session")

    @patch.dict("os.environ", {
        "FOXIT_ESIGN_BASE_URL": "https://na1.foxitesign.foxit.com",
        "FOXIT_ESIGN_CLIENT_ID": "id",
        "FOXIT_ESIGN_CLIENT_SECRET": "secret",
    }, clear=False)
    def test_uses_documented_status_and_download_endpoints(self):
        session = Mock()
        token1 = Mock()
        token1.json.return_value = {"access_token": "T1"}
        token1.raise_for_status.return_value = None
        folder = Mock()
        folder.json.return_value = {"folder": {"folderId": 123, "folderStatus": "EXECUTED"}}
        folder.raise_for_status.return_value = None
        token2 = Mock()
        token2.json.return_value = {"access_token": "T2"}
        token2.raise_for_status.return_value = None
        document = Mock()
        document.content = b"%PDF-signed"
        document.raise_for_status.return_value = None
        session.post.side_effect = [token1, token2]
        session.get.side_effect = [folder, document]

        client = FoxitESignClient(session=session)
        client.get_folder("123")
        data = client.download_document("123")
        self.assertEqual(data, b"%PDF-signed")
        self.assertTrue(session.get.call_args_list[0].args[0].endswith("/api/folders/myfolder"))
        self.assertTrue(session.get.call_args_list[1].args[0].endswith("/api/folders/document/download"))

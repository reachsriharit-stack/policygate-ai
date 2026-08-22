import json
import unittest
from unittest.mock import Mock, patch

from policygate.foxit_client import FoxitESignClient, FoxitNotConfigured


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


class DeveloperPlatformTransportTests(unittest.TestCase):
    """The Developer Platform gateway reaches the same eSign API with the same
    request bodies; only the host, route prefix and authentication differ."""

    DEV_ENV = {
        "FOXIT_ESIGN_TRANSPORT": "developer_platform",
        "FOXIT_CLOUD_API_CLIENT_ID": "cloud-id",
        "FOXIT_CLOUD_API_CLIENT_SECRET": "cloud-secret",
    }

    @staticmethod
    def _folder_session():
        session = Mock()
        folder_response = Mock()
        folder_response.json.return_value = {"folder": {"folderId": 456}}
        folder_response.raise_for_status.return_value = None
        session.post.return_value = folder_response
        return session

    @patch.dict("os.environ", DEV_ENV, clear=True)
    def test_posts_to_gateway_createfolder_without_a_token_exchange(self):
        session = self._folder_session()
        client = FoxitESignClient(session=session)
        handoff = client.create_human_approval_draft(
            b"%PDF-demo", "Jane Smith", "jane@example.com", "PG-1"
        )

        self.assertEqual(handoff.folder_id, "456")
        # One call only: the gateway authenticates per request, so there is no
        # OAuth round trip.
        self.assertEqual(session.post.call_count, 1)
        self.assertEqual(
            session.post.call_args.args[0],
            "https://na1.fusion.foxit.com/esign/api/v1/folders/createfolder",
        )

    @patch.dict("os.environ", DEV_ENV, clear=True)
    def test_authenticates_with_client_id_and_secret_headers(self):
        session = self._folder_session()
        FoxitESignClient(session=session).create_human_approval_draft(
            b"%PDF-demo", "Jane Smith", "jane@example.com", "PG-1"
        )
        headers = session.post.call_args.kwargs["headers"]
        self.assertEqual(headers["client_id"], "cloud-id")
        self.assertEqual(headers["client_secret"], "cloud-secret")
        self.assertNotIn("Authorization", headers)

    @patch.dict("os.environ", {"FOXIT_ESIGN_TRANSPORT": "developer_platform"}, clear=True)
    def test_not_configured_without_developer_platform_credentials(self):
        client = FoxitESignClient(session=Mock())
        self.assertFalse(client.configured)
        with self.assertRaises(FoxitNotConfigured):
            client.create_human_approval_draft(
                b"%PDF-demo", "Jane Smith", "jane@example.com", "PG-1"
            )

    @patch.dict("os.environ", DEV_ENV, clear=True)
    def test_routes_invitation_without_signing_the_document(self):
        session = self._folder_session()
        FoxitESignClient(session=session).create_human_approval_draft(
            b"%PDF-demo", "Jane Smith", "jane@example.com", "PG-1", send_now=True
        )
        payload = session.post.call_args.kwargs["json"]

        self.assertTrue(payload["sendNow"])
        self.assertEqual(payload["parties"][0]["emailId"], "jane@example.com")
        self.assertEqual(payload["parties"][0]["permission"], "FILL_FIELDS_AND_SIGN")
        # None of these may ever appear: each one would move the signature off
        # the human and onto the agent.
        for forbidden in (
            "signNow",
            "createExecutedFolder",
            "signature",
            "savedSignature",
            "useSavedSignature",
        ):
            self.assertNotIn(forbidden, payload)

    @patch.dict("os.environ", DEV_ENV, clear=True)
    def test_embedded_session_stays_opt_in_on_the_gateway(self):
        session = self._folder_session()
        FoxitESignClient(session=session).create_human_approval_draft(
            b"%PDF-demo", "Jane Smith", "jane@example.com", "PG-1"
        )
        payload = session.post.call_args.kwargs["json"]
        self.assertNotIn("createEmbeddedSigningSession", payload)

    @patch.dict("os.environ", DEV_ENV, clear=True)
    def test_status_and_download_use_the_gateway_prefix(self):
        session = Mock()
        status_response = Mock()
        status_response.json.return_value = {"folder": {"folderStatus": "SENT"}}
        status_response.raise_for_status.return_value = None
        download_response = Mock()
        download_response.content = b"%PDF-signed"
        download_response.raise_for_status.return_value = None
        session.get.side_effect = [status_response, download_response]

        client = FoxitESignClient(session=session)
        client.get_folder("456")
        client.download_document("456")

        self.assertEqual(
            session.get.call_args_list[0].args[0],
            "https://na1.fusion.foxit.com/esign/api/v1/folders/myfolder",
        )
        self.assertEqual(
            session.get.call_args_list[1].args[0],
            "https://na1.fusion.foxit.com/esign/api/v1/folders/document/download",
        )

    @patch.dict("os.environ", {
        "FOXIT_ESIGN_BASE_URL": "https://na1.foxitesign.foxit.com",
        "FOXIT_ESIGN_CLIENT_ID": "id",
        "FOXIT_ESIGN_CLIENT_SECRET": "secret",
    }, clear=True)
    def test_default_transport_is_unchanged(self):
        client = FoxitESignClient(session=Mock())
        self.assertEqual(
            client._url("/folders/createfolder"),
            "https://na1.foxitesign.foxit.com/api/folders/createfolder",
        )

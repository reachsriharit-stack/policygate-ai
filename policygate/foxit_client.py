"""Foxit eSign integration.

The challenge boundary is explicit: this client can create a draft signing
folder and optionally request a human embedded signing session. It deliberately
contains no method that signs, auto-accepts, or impersonates the approver.

Two transports reach the same eSign API:

``esign_oauth`` (default)
    The eSign portal host with an OAuth client-credentials token, using
    ``FOXIT_ESIGN_CLIENT_ID`` / ``FOXIT_ESIGN_CLIENT_SECRET``.

``developer_platform``
    The Foxit Developer Platform gateway, which authenticates every request
    with ``client_id`` / ``client_secret`` headers taken from the same
    ``FOXIT_CLOUD_API_*`` credentials the PDF Services API uses, and roots the
    eSign routes at ``/esign/api/v1``.

Select one with ``FOXIT_ESIGN_TRANSPORT``. Only the endpoints and the
authentication differ; the request bodies, the human-approval boundary, and the
absence of any signing method are identical in both.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Optional

import requests


class FoxitNotConfigured(RuntimeError):
    pass


@dataclass
class HumanApprovalHandoff:
    provider: str
    folder_id: str
    status: str
    signer_email: str
    embedded_session_url: Optional[str] = None
    mock: bool = False


DEVELOPER_PLATFORM = "developer_platform"
ESIGN_OAUTH = "esign_oauth"

_DEFAULT_HOSTS = {
    ESIGN_OAUTH: "https://na1.foxitesign.foxit.com",
    DEVELOPER_PLATFORM: "https://na1.fusion.foxit.com",
}
_API_PREFIXES = {
    ESIGN_OAUTH: "/api",
    DEVELOPER_PLATFORM: "/esign/api/v1",
}


class FoxitESignClient:
    def __init__(self, session: requests.Session | None = None):
        transport = os.getenv("FOXIT_ESIGN_TRANSPORT", ESIGN_OAUTH).strip().lower()
        self.transport = transport if transport in _API_PREFIXES else ESIGN_OAUTH
        self.base_url = os.getenv(
            "FOXIT_ESIGN_BASE_URL", _DEFAULT_HOSTS[self.transport]
        ).rstrip("/")
        if self.transport == DEVELOPER_PLATFORM:
            # Same Developer Platform credentials as the PDF Services API.
            self.client_id = os.getenv("FOXIT_CLOUD_API_CLIENT_ID")
            self.client_secret = os.getenv("FOXIT_CLOUD_API_CLIENT_SECRET")
        else:
            self.client_id = os.getenv("FOXIT_ESIGN_CLIENT_ID")
            self.client_secret = os.getenv("FOXIT_ESIGN_CLIENT_SECRET")
        self.session = session or requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _url(self, path: str) -> str:
        return f"{self.base_url}{_API_PREFIXES[self.transport]}/{path.lstrip('/')}"

    def _auth_headers(self) -> dict[str, str]:
        """The gateway authenticates per request; the portal exchanges the same
        credentials for a bearer token first. Neither value is ever logged."""
        if not self.configured:
            raise FoxitNotConfigured("Foxit eSign is not configured")
        if self.transport == DEVELOPER_PLATFORM:
            return {"client_id": self.client_id, "client_secret": self.client_secret}
        return {"Authorization": f"Bearer {self._get_token()}"}

    def _get_token(self) -> str:
        if not self.configured:
            raise FoxitNotConfigured("FOXIT_ESIGN_CLIENT_ID / FOXIT_ESIGN_CLIENT_SECRET are not set")
        response = self.session.post(
            self._url("/oauth2/access_token"),
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
                "scope": "read-write",
            },
            timeout=20,
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise RuntimeError("Foxit eSign token response did not contain access_token")
        return token

    def create_human_approval_draft(
        self,
        pdf_bytes: bytes,
        signer_name: str,
        signer_email: str,
        request_id: str,
        create_embedded_session: bool = False,
        send_now: bool = False,
    ) -> HumanApprovalHandoff:
        if not self.configured:
            raise FoxitNotConfigured("Foxit eSign is not configured")
        if not signer_email:
            raise ValueError("A signer email is required for Foxit eSign routing")

        names = signer_name.strip().split(maxsplit=1) if signer_name else ["Human", "Approver"]
        first_name = names[0]
        last_name = names[1] if len(names) > 1 else "Approver"
        encoded = base64.b64encode(pdf_bytes).decode("ascii")

        payload = {
            "folderName": f"PolicyGate Approval - {request_id}",
            # Routing is an explicit caller choice. Sending an invitation is allowed;
            # signing remains exclusively a human action.
            "sendNow": send_now,
            "processTextTags": True,
            "inputType": "base64",
            "base64FileString": [encoded],
            "fileNames": [f"{request_id}-approval.pdf"],
            "metadata": {
                "policygate_request_id": request_id,
                "approval_boundary": "human-only",
            },
            "parties": [{
                "firstName": first_name,
                "lastName": last_name,
                "emailId": signer_email,
                "permission": "FILL_FIELDS_AND_SIGN",
                "sequence": 1,
            }],
        }
        if create_embedded_session:
            payload.update({
                "createEmbeddedSigningSession": True,
                "embeddedSignersEmailIds": [signer_email],
            })

        response = self.session.post(
            self._url("/folders/createfolder"),
            headers=self._auth_headers(),
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        data = response.json()
        folder = data.get("folder") or {}
        folder_id = str(folder.get("folderId") or data.get("folderId") or "unknown")

        session_url = None
        sessions = data.get("embeddedSigningSessions") or []
        if sessions:
            session_url = sessions[0].get("embeddedSessionURL")

        return HumanApprovalHandoff(
            provider="Foxit eSign",
            folder_id=folder_id,
            status="AWAITING_HUMAN_APPROVAL",
            signer_email=signer_email,
            embedded_session_url=session_url,
        )

    def get_folder(self, folder_id: str) -> dict:
        """Fetch current Foxit folder data for a post-sign status check."""
        response = self.session.get(
            self._url("/folders/myfolder"),
            headers=self._auth_headers(),
            params={"folderId": folder_id},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def download_document(self, folder_id: str, doc_number: int = 1) -> bytes:
        """Download one document from a completed/executed Foxit folder."""
        response = self.session.get(
            self._url("/folders/document/download"),
            headers=self._auth_headers(),
            params={"folderId": folder_id, "docNumber": doc_number},
            timeout=45,
        )
        response.raise_for_status()
        return response.content


def mock_handoff(signer_email: str, request_id: str) -> HumanApprovalHandoff:
    return HumanApprovalHandoff(
        provider="Foxit eSign (mock)",
        folder_id=f"MOCK-{request_id}",
        status="AWAITING_HUMAN_APPROVAL",
        signer_email=signer_email or "approver@example.com",
        mock=True,
    )

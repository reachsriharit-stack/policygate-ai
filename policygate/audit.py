"""Audit-record helpers for pre-sign and post-sign evidence."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def verify_foxit_webhook_signature(
    raw_body: bytes,
    signature: str | None,
    webhook_secret: str | None,
) -> bool:
    """Verify Foxit eSign's HMAC-SHA-256/Base64 webhook signature.

    Foxit signs the *raw* HTTP request body with the configured webhook
    secret and sends the Base64 digest in the ``signature`` query
    parameter. Verification must therefore happen before parsing or
    re-serializing the JSON body.
    """
    if not raw_body or not signature or not webhook_secret:
        return False
    digest = hmac.new(
        webhook_secret.encode("utf-8"), raw_body, sha256
    ).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature.strip())


def build_pre_sign_audit(evidence: dict, pdf_bytes: bytes, handoff) -> dict:
    expected_signer = _normalize_email(handoff.signer_email)
    return {
        "request_id": evidence["request_id"],
        "policy_version": evidence["policy_version"],
        "plan_sha256": evidence["plan_sha256"],
        "unsigned_pdf_sha256": sha256_bytes(pdf_bytes),
        "terraform_plan_file_sha256": (evidence.get("terraform_plan") or {}).get("plan_file_sha256"),
        "foxit_folder_id": handoff.folder_id,
        # Retain signer_email for backward readability and add an explicit
        # expected/verified pair for the authorization gate.
        "signer_email": expected_signer,
        "expected_signer_email": expected_signer,
        "verified_signer_email": None,
        "state": "AWAITING_HUMAN_APPROVAL",
        "agent_may_sign": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _folder_from_webhook(payload: dict) -> dict:
    return ((payload.get("data") or {}).get("folder") or {})


def _assert_folder_matches(expected_folder_id: str, actual_folder_id) -> None:
    if actual_folder_id is None:
        raise ValueError("Foxit completion evidence did not include folderId")
    if str(actual_folder_id) != str(expected_folder_id):
        raise ValueError(
            f"Foxit folder mismatch: expected {expected_folder_id!r}, got {actual_folder_id!r}"
        )


def _recipient_emails(folder: dict) -> list[str]:
    emails: list[str] = []
    for party in folder.get("folderRecipientParties") or []:
        permission = str(party.get("contractPermissions") or party.get("permission") or "").upper()
        if permission and "SIGN" not in permission:
            continue
        details = party.get("partyDetails") or {}
        email = _normalize_email(details.get("emailId") or party.get("emailId"))
        if email:
            emails.append(email)
    return emails


def _verify_expected_signer_from_folder(pre_sign: dict, folder: dict) -> str:
    expected = _normalize_email(pre_sign.get("expected_signer_email") or pre_sign.get("signer_email"))
    if not expected:
        raise ValueError("Pre-sign audit does not identify the expected signer email")
    emails = _recipient_emails(folder)
    if expected not in emails:
        raise ValueError(
            f"Foxit signer mismatch: expected {expected!r}; folder recipients were {emails!r}"
        )
    return expected


def _verify_expected_signer_from_webhook(pre_sign: dict, webhook_payload: dict, folder: dict) -> str:
    expected = _normalize_email(pre_sign.get("expected_signer_email") or pre_sign.get("signer_email"))
    if not expected:
        raise ValueError("Pre-sign audit does not identify the expected signer email")

    data = webhook_payload.get("data") or {}
    signing_party = data.get("signing_party") or data.get("signingParty") or {}
    actual = _normalize_email(signing_party.get("emailId") or signing_party.get("email"))
    if actual:
        if actual != expected:
            raise ValueError(f"Foxit signer mismatch: expected {expected!r}, got {actual!r}")
        return actual

    # Some completion payloads may omit signing_party. In that case, require
    # the expected recipient to still be present on the correlated folder.
    return _verify_expected_signer_from_folder(pre_sign, folder)


def finalize_from_foxit_webhook(
    pre_sign: dict,
    webhook_payload: dict,
    signed_pdf: bytes | None = None,
) -> dict:
    """Create a final audit record from a correlated Foxit webhook.

    The HTTP receiver must authenticate/validate the webhook transport before
    calling this function. This function additionally prevents cross-folder
    completion and verifies the expected signer identity carried by Foxit.
    """
    event_name = webhook_payload.get("event_name")
    if event_name != "folder_executed":
        raise ValueError(
            f"Not a final Foxit execution event: {event_name!r}. "
            "Wait for folder_executed so the completed documents include Foxit's digital signature."
        )

    folder = _folder_from_webhook(webhook_payload)
    _assert_folder_matches(pre_sign["foxit_folder_id"], folder.get("folderId"))
    status = str(folder.get("folderStatus") or "").upper()
    if status != "EXECUTED":
        raise ValueError(
            f"Foxit folder_executed payload did not report EXECUTED status (status={status or 'UNKNOWN'})"
        )
    verified_signer = _verify_expected_signer_from_webhook(pre_sign, webhook_payload, folder)
    if signed_pdf is None:
        raise ValueError(
            "Signed Foxit PDF bytes are required before the audit can become APPROVED"
        )

    final = dict(pre_sign)
    final.update({
        "state": "APPROVED",
        "foxit_event_name": event_name,
        "foxit_event_date": webhook_payload.get("event_date"),
        "foxit_folder_status": status,
        "verified_signer_email": verified_signer,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    final["signed_pdf_sha256"] = sha256_bytes(signed_pdf)
    return final


def finalize_from_foxit_folder(
    pre_sign: dict,
    folder_response: dict,
    signed_pdf: bytes,
) -> dict:
    """Finalize a demo audit by polling Foxit after the human signs.

    We require the exact folder from the pre-sign record, ``EXECUTED`` status,
    and the expected signer email to still be one of Foxit's recipient parties.
    """
    folder = folder_response.get("folder") or {}
    _assert_folder_matches(pre_sign["foxit_folder_id"], folder.get("folderId"))
    status = str(folder.get("folderStatus") or "").upper()
    if status != "EXECUTED":
        raise ValueError(f"Foxit folder is not executed yet (status={status or 'UNKNOWN'})")

    verified_signer = _verify_expected_signer_from_folder(pre_sign, folder)

    final = dict(pre_sign)
    final.update({
        "state": "APPROVED",
        "foxit_folder_status": status,
        "approval_source": "foxit_folder_status_poll",
        "verified_signer_email": verified_signer,
        "signed_pdf_sha256": sha256_bytes(signed_pdf),
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    return final


def write_audit_record(record: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

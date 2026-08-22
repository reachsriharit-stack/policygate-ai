"""Sanitized evidence the demo UI is allowed to display.

The final workflow (.github/workflows/final-policygate-demo.yml) is the only
source of truth for whether an integration is live. This module carries a
deliberately narrow record of *what that run observed* — booleans, counts,
hashes and states — so the UI can report it without re-deriving anything and
without any opportunity to claim LIVE on its own.

Two rules give the file its shape:

* Allowlist, not denylist. Only the fields in ``ALLOWED_FIELDS`` survive
  ``sanitize``; anything else is dropped, so a future caller cannot widen what
  reaches a screen by adding a key upstream.
* No identity. Credentials, tokens, AWS account IDs, signing-session URLs,
  personal email addresses and Terraform state are rejected outright rather
  than merely omitted — see ``_reject_sensitive``.

There is no sample evidence file in this repository on purpose: a committed
example carrying LIVE values would be indistinguishable, on screen, from a
real run.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

#: Every field the UI may show, and the type it must have.
ALLOWED_FIELDS: dict[str, type | tuple[type, ...]] = {
    "claude_live": bool,
    "policy_result": str,
    "terraform_live_plan": bool,
    "terraform_resources_added": int,
    "terraform_resources_changed": int,
    "terraform_resources_destroyed": int,
    "terraform_plan_sha256": str,
    "terraform_plan_summary": str,
    "foxit_mcp_live": bool,
    "foxit_esign_live": bool,
    "foxit_status": str,
    "human_gate_state": str,
    "human_signature_verified": bool,
    "final_audit_state": str,
}

#: Default location the UI looks in; override with POLICYGATE_DEMO_EVIDENCE.
DEFAULT_EVIDENCE_PATH = Path(__file__).resolve().parents[1] / "demo-evidence.json"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_AWS_ACCOUNT = re.compile(r"\b\d{12}\b")
_URL = re.compile(r"https?://", re.I)
_SECRET_MARKERS = ("-----BEGIN", "aws_access_key", "aws_secret", "session_token", "bearer ")


class UnsafeEvidence(ValueError):
    """A value that must never reach a screen was found in the evidence."""


def _reject_sensitive(field: str, value: str) -> None:
    lowered = value.lower()
    if _EMAIL.search(value):
        raise UnsafeEvidence(f"{field} contains an email address")
    if _URL.search(value):
        raise UnsafeEvidence(f"{field} contains a URL")
    if _AWS_ACCOUNT.search(value):
        raise UnsafeEvidence(f"{field} contains what looks like an AWS account ID")
    if any(marker in lowered for marker in _SECRET_MARKERS):
        raise UnsafeEvidence(f"{field} contains credential-shaped text")
    if "tfstate" in lowered or '"terraform_version"' in lowered:
        raise UnsafeEvidence(f"{field} contains Terraform state")


def sanitize(raw: dict[str, Any]) -> dict[str, Any]:
    """Return only the allowed fields, correctly typed and free of identity.

    Unknown keys are dropped silently — that is the point of an allowlist — but
    a *known* field carrying sensitive content raises, because that means the
    producer is leaking and should be fixed rather than quietly trimmed.
    """
    if not isinstance(raw, dict):
        raise UnsafeEvidence("Demo evidence must be a JSON object")

    clean: dict[str, Any] = {}
    for field, expected in ALLOWED_FIELDS.items():
        if field not in raw:
            continue
        value = raw[field]
        if expected is bool:
            if not isinstance(value, bool):
                continue
        elif expected is int:
            if isinstance(value, bool) or not isinstance(value, int):
                continue
        else:
            if not isinstance(value, str):
                continue
            _reject_sensitive(field, value)
            if field == "terraform_plan_sha256" and not _SHA256.match(value):
                raise UnsafeEvidence("terraform_plan_sha256 is not a SHA-256 digest")
        clean[field] = value
    return clean


def build(
    *,
    claude_live: bool,
    policy_passed: bool,
    terraform_live_plan: bool,
    resources_added: int,
    resources_changed: int,
    resources_destroyed: int,
    terraform_plan_sha256: str,
    terraform_plan_summary: str,
    foxit_mcp_live: bool,
    foxit_esign_live: bool,
    foxit_status: str,
    human_gate_state: str,
    human_signature_verified: bool,
    final_audit_state: str,
) -> dict[str, Any]:
    """Build the record from what a run actually observed."""
    return sanitize(
        {
            "claude_live": claude_live,
            "policy_result": "PASS" if policy_passed else "FAIL",
            "terraform_live_plan": terraform_live_plan,
            "terraform_resources_added": resources_added,
            "terraform_resources_changed": resources_changed,
            "terraform_resources_destroyed": resources_destroyed,
            "terraform_plan_sha256": terraform_plan_sha256,
            "terraform_plan_summary": terraform_plan_summary,
            "foxit_mcp_live": foxit_mcp_live,
            "foxit_esign_live": foxit_esign_live,
            "foxit_status": foxit_status,
            "human_gate_state": human_gate_state,
            "human_signature_verified": human_signature_verified,
            "final_audit_state": final_audit_state,
        }
    )


def load(path: str | Path | None = None) -> Optional[dict[str, Any]]:
    """Load sanitized evidence, or None when there is none to show.

    Missing or unreadable evidence is not an error: the UI simply keeps its
    honest offline labels. Evidence that exists but leaks does raise.
    """
    candidate = Path(path or os.getenv("POLICYGATE_DEMO_EVIDENCE") or DEFAULT_EVIDENCE_PATH)
    if not candidate.is_file():
        return None
    try:
        raw = json.loads(candidate.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return sanitize(raw)


def is_verified(evidence: Optional[dict[str, Any]]) -> bool:
    """True only for a run that reached a verified human signature.

    Every integration must have reported live, the guardrails must have passed,
    Foxit must have reported EXECUTED, and the audit must be APPROVED. Anything
    short of that leaves the UI on its offline labels.
    """
    if not evidence:
        return False
    return (
        evidence.get("claude_live") is True
        and evidence.get("policy_result") == "PASS"
        and evidence.get("terraform_live_plan") is True
        and evidence.get("foxit_mcp_live") is True
        and evidence.get("foxit_esign_live") is True
        and evidence.get("human_signature_verified") is True
        and str(evidence.get("foxit_status", "")).upper() == "EXECUTED"
        and str(evidence.get("final_audit_state", "")).upper() == "APPROVED"
    )


def badges(evidence: Optional[dict[str, Any]]) -> Optional[dict[str, str]]:
    """The six headline labels, derived from the evidence — never asserted."""
    if not is_verified(evidence):
        return None
    assert evidence is not None
    return {
        "Claude": "LIVE",
        "Policy Engine": evidence["policy_result"],
        "Terraform": "LIVE PLAN",
        "Foxit MCP": "LIVE",
        "Foxit eSign": "LIVE",
        "Human Gate": "VERIFIED",
    }

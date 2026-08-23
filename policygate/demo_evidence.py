"""Sanitized evidence the demo UI is allowed to display.

The final workflow (.github/workflows/final-policygate-demo.yml) is the only
source of truth for what actually happened. This module carries a deliberately
narrow record of *what that run observed* — booleans, counts, hashes, states
and a few static strings — so the UI can tell the story without re-deriving
anything and without any opportunity to claim LIVE on its own.

Three rules give the file its shape:

* Allowlist, not denylist. Only the fields in ``ALLOWED_FIELDS`` survive
  ``sanitize``; anything else is dropped, so a future producer cannot widen
  what reaches a screen by adding a key upstream.
* No identity, and loudly. Credentials, tokens, AWS account IDs, ARNs,
  signing-session URLs, email addresses and Terraform state are *rejected*
  rather than masked — a leak means the producer is broken and should be
  fixed, not quietly trimmed at the display layer.
* Verified means verified. ``is_verified`` requires the whole chain: a live
  Claude call with no fallback, passing guardrails, a real plan, a Foxit
  EXECUTED folder, a matching signer, an unchanged plan hash, and no apply or
  destroy. Any gap leaves the UI on its honest offline labels.

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

BOOL = bool
INT = int
STR = str
NUMBER = (int, float)
STR_LIST = "str_list"
RULE_LIST = "rule_list"

#: Every field the UI may show, and the shape it must have.
ALLOWED_FIELDS: dict[str, Any] = {
    # 1. the request
    "request_text": STR,
    # 2. Claude's structured intent
    "claude_live": BOOL,
    "claude_fallback_used": BOOL,
    "parsed_environment": STR,
    "parsed_cloud": STR,
    "parsed_region": STR,
    "parsed_service": STR,
    "parsed_high_availability": BOOL,
    "parsed_backup_retention_days": INT,
    "parsed_budget_monthly": NUMBER,
    # 3. deterministic policy
    "requested_controls": STR_LIST,
    "policy_injected_controls": STR_LIST,
    "policy_rule_results": RULE_LIST,
    "policy_result": STR,
    # 4. generated infrastructure
    "terraform_generated": BOOL,
    "terraform_resource_type": STR,
    "terraform_multi_az": BOOL,
    "terraform_encrypted": BOOL,
    "terraform_backup_retention_days": INT,
    "terraform_publicly_accessible": BOOL,
    "terraform_managed_password": BOOL,
    "terraform_hcl_preview": STR,
    # 5. the real plan
    "terraform_live_plan": BOOL,
    "terraform_add": INT,
    "terraform_change": INT,
    "terraform_destroy": INT,
    "terraform_plan_sha256": STR,
    "terraform_plan_summary": STR,
    # 6. approval evidence
    "approval_pdf_generated": BOOL,
    "unsigned_pdf_sha256": STR,
    "foxit_mcp_live": BOOL,
    "foxit_mcp_operation_verified": BOOL,
    "foxit_mcp_output_pdf_sha256": STR,
    "foxit_esign_live": BOOL,
    # 7. the human boundary
    "pre_approval_state": STR,
    "agent_may_sign": BOOL,
    "agent_signed": BOOL,
    "provisioning_allowed_before_approval": BOOL,
    "foxit_status": STR,
    "human_signature_verified": BOOL,
    "signer_match": BOOL,
    "human_gate_state": STR,
    # 8. cryptographic binding
    "terraform_plan_hash_verified": BOOL,
    "terraform_replanned_after_signature": BOOL,
    # 9. final audit
    "signed_pdf_sha256": STR,
    "final_audit_state": STR,
    "terraform_apply_ran": BOOL,
    "terraform_destroy_ran": BOOL,
}

#: Default location the UI looks in; override with POLICYGATE_DEMO_EVIDENCE.
DEFAULT_EVIDENCE_PATH = Path(__file__).resolve().parents[1] / "demo-evidence.json"

HCL_PREVIEW_LIMIT = 4000
TEXT_LIMIT = 2000

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_AWS_ACCOUNT = re.compile(r"\b\d{12}\b")
_ARN = re.compile(r"\barn:aws[a-z-]*:", re.I)
_URL = re.compile(r"https?://", re.I)
_PRIVATE_IP = re.compile(r"\b(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|\b192\.168\.\d{1,3}\.\d{1,3}\b")
_ACCESS_KEY = re.compile(r"\b(?:AKIA|ASIA|ghp_|gho_|github_pat_)[A-Za-z0-9]{6,}")
_ASSIGNED_SECRET = re.compile(
    r"\b(password|secret|token|api[_-]?key|client[_-]?secret)\b\s*[=:]\s*[\"']?[^\s\"']+",
    re.I,
)
_SECRET_MARKERS = ("-----begin", "aws_access_key", "aws_secret_access_key", "session_token", "bearer ")
_STATE_MARKERS = ("tfstate", '"lineage"', '"serial"')


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
    if _ARN.search(value):
        raise UnsafeEvidence(f"{field} contains an ARN")
    if _PRIVATE_IP.search(value):
        raise UnsafeEvidence(f"{field} contains a private IP address")
    if _ACCESS_KEY.search(value):
        raise UnsafeEvidence(f"{field} contains an access key")
    if any(marker in lowered for marker in _SECRET_MARKERS):
        raise UnsafeEvidence(f"{field} contains credential-shaped text")
    if any(marker in lowered for marker in _STATE_MARKERS):
        raise UnsafeEvidence(f"{field} contains Terraform state")
    # `manage_master_user_password = true` is a boolean control, not a secret,
    # and is exactly the proof the demo wants to show. An assignment carrying
    # an actual value is not.
    for match in _ASSIGNED_SECRET.finditer(value):
        assigned = match.group(0).split("=")[-1].split(":")[-1].strip().strip("\"'").lower()
        if assigned not in {"true", "false", "null", "none", ""}:
            raise UnsafeEvidence(f"{field} contains an assigned {match.group(1).lower()}")


def _clean_str(field: str, value: str, limit: int) -> str:
    _reject_sensitive(field, value)
    if field.endswith("_sha256") and value and not _SHA256.match(value):
        raise UnsafeEvidence(f"{field} is not a SHA-256 digest")
    return value[:limit]


def sanitize(raw: dict[str, Any]) -> dict[str, Any]:
    """Return only the allowed fields, correctly shaped and free of identity.

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

        if expected is BOOL:
            if isinstance(value, bool):
                clean[field] = value
        elif expected is INT:
            if isinstance(value, int) and not isinstance(value, bool):
                clean[field] = value
        elif expected is NUMBER:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                clean[field] = value
        elif expected is STR:
            if isinstance(value, str):
                limit = HCL_PREVIEW_LIMIT if field == "terraform_hcl_preview" else TEXT_LIMIT
                clean[field] = _clean_str(field, value, limit)
        elif expected is STR_LIST:
            if isinstance(value, list):
                clean[field] = [
                    _clean_str(field, item, TEXT_LIMIT)
                    for item in value
                    if isinstance(item, str)
                ]
        elif expected is RULE_LIST:
            if isinstance(value, list):
                rules = []
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    code = item.get("code")
                    result = item.get("result")
                    if not isinstance(code, str) or not isinstance(result, str):
                        continue
                    rule = {
                        "code": _clean_str(field, code, 32),
                        "result": _clean_str(field, result, 16),
                    }
                    description = item.get("description")
                    if isinstance(description, str):
                        rule["description"] = _clean_str(field, description, 200)
                    rules.append(rule)
                clean[field] = rules
    return clean


def build(**values: Any) -> dict[str, Any]:
    """Build the record from what a run actually observed.

    Keyword names are the evidence field names, so a producer adding a value
    the allowlist does not know about simply loses it rather than smuggling it
    through.
    """
    return sanitize(values)


def load(path: str | Path | None = None) -> Optional[dict[str, Any]]:
    """Load sanitized evidence, or None when there is none to show.

    Missing or unreadable evidence is not an error: the UI keeps its honest
    offline labels. Evidence that exists but leaks does raise.
    """
    candidate = Path(path or os.getenv("POLICYGATE_DEMO_EVIDENCE") or DEFAULT_EVIDENCE_PATH)
    if not candidate.is_file():
        return None
    try:
        raw = json.loads(candidate.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return sanitize(raw)


#: Every condition that must hold before the UI may show a verified state.
#: Kept as data so a reader can audit the claim in one place.
_VERIFIED_REQUIREMENTS: tuple[tuple[str, Any], ...] = (
    ("claude_live", True),
    ("claude_fallback_used", False),
    ("policy_result", "PASS"),
    ("terraform_live_plan", True),
    ("foxit_mcp_live", True),
    ("foxit_mcp_operation_verified", True),
    ("foxit_esign_live", True),
    ("agent_signed", False),
    ("human_signature_verified", True),
    ("signer_match", True),
    ("terraform_plan_hash_verified", True),
    ("terraform_replanned_after_signature", False),
    ("terraform_apply_ran", False),
    ("terraform_destroy_ran", False),
)


def is_verified(evidence: Optional[dict[str, Any]]) -> bool:
    """True only for a run that completed the whole chain to a human signature."""
    if not evidence:
        return False
    for field, expected in _VERIFIED_REQUIREMENTS:
        if evidence.get(field) != expected:
            return False
    if str(evidence.get("foxit_status", "")).upper() != "EXECUTED":
        return False
    if str(evidence.get("final_audit_state", "")).upper() != "APPROVED":
        return False
    # An approval with no signed document, or no plan bound to it, is not an
    # approval anyone could check afterwards.
    for digest in ("signed_pdf_sha256", "terraform_plan_sha256"):
        if not _SHA256.match(str(evidence.get(digest, ""))):
            return False
    return True


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

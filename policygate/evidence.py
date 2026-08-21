"""Build the immutable pre-sign approval evidence packet."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json

from .schema import PolicyResult

AI_DISCLOSURE = (
    "AI interpreted the natural-language request. The provisioning plan and all "
    "compliance results were produced by deterministic code. The AI did not "
    "approve, authorize, or sign this change."
)


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_json(value: object) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def build_evidence_packet(result: PolicyResult, terraform_plan: dict | None = None) -> dict:
    request = asdict(result.request)
    plan = asdict(result.plan)
    checks = [asdict(c) for c in result.checks]

    packet = {
        "request_id": result.request.request_id,
        "requested_by": result.request.requested_by,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "policy_version": result.policy_version,
        "policy_status": "READY_FOR_HUMAN_REVIEW" if result.passed else "BLOCKED",
        "request": request,
        "proposed_plan": plan,
        "compliance_checks": checks,
        "ai_disclosure": AI_DISCLOSURE,
        "human_approval_required": result.request.environment == "production",
        "agent_may_sign": False,
    }
    if terraform_plan is not None:
        # {"plan_summary": <human-readable terraform show output>,
        #  "plan_file_sha256": <hash of the actual saved plan file>}
        # This is the value verify_plan_file_integrity() re-checks at apply
        # time — see provisioning/approval_gate.py.
        packet["terraform_plan"] = terraform_plan
    packet["request_sha256"] = sha256_json(request)
    packet["plan_sha256"] = sha256_json(plan)
    packet["checks_sha256"] = sha256_json(checks)
    return packet

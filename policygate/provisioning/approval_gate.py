"""The single choke point that decides whether provisioning is allowed to run.

Nothing else in this codebase — not the AI parser, not the rule engine, not
a passed policy check — can authorize infrastructure creation. Only a
verified, executed Foxit signature can, and only for the exact plan that was
actually signed.

This mirrors audit.py's finalize_from_foxit_folder(): it does not trust a
caller's claim that something was approved. It re-derives the plan hash from
the evidence packet itself and compares it against what's recorded in the
final audit, so a plan that was edited after signing — even by one field —
fails closed.
"""
from __future__ import annotations

from .. import evidence as evidence_module


class ProvisioningNotAuthorized(PermissionError):
    """Raised whenever authorize_provisioning() would return False.

    Deliberately a PermissionError subclass so a caller that forgets to
    check the return value and instead wraps this in a bare except still
    can't accidentally treat "authorization failed" as "safe to proceed."
    """


def authorize_provisioning(final_audit: dict, evidence: dict) -> bool:
    """Raises ProvisioningNotAuthorized with a specific reason on any failure.
    Returns True only if every check passes."""

    if final_audit.get("request_id") != evidence.get("request_id"):
        raise ProvisioningNotAuthorized(
            "Audit record and evidence packet reference different request IDs "
            f"({final_audit.get('request_id')!r} vs {evidence.get('request_id')!r})."
        )

    if final_audit.get("state") != "APPROVED":
        raise ProvisioningNotAuthorized(
            f"Audit state is {final_audit.get('state')!r}, not APPROVED."
        )

    if final_audit.get("agent_may_sign") is not False:
        # This should be structurally impossible given how audit records are
        # built, but a gate that trusts its own invariants isn't a gate.
        raise ProvisioningNotAuthorized(
            "Audit record does not explicitly assert agent_may_sign=false."
        )

    if final_audit.get("foxit_folder_status") != "EXECUTED":
        raise ProvisioningNotAuthorized(
            f"Foxit folder status is {final_audit.get('foxit_folder_status')!r}, "
            "not EXECUTED."
        )

    if not final_audit.get("signed_pdf_sha256"):
        raise ProvisioningNotAuthorized("No signed_pdf_sha256 present on the audit record.")

    expected_signer = (final_audit.get("expected_signer_email") or final_audit.get("signer_email") or "").strip().lower()
    verified_signer = (final_audit.get("verified_signer_email") or "").strip().lower()
    if not expected_signer:
        raise ProvisioningNotAuthorized("No expected signer email present on the audit record.")
    if not verified_signer:
        raise ProvisioningNotAuthorized("No verified_signer_email present on the final audit record.")
    if verified_signer != expected_signer:
        raise ProvisioningNotAuthorized(
            f"Verified Foxit signer {verified_signer!r} does not match expected approver {expected_signer!r}."
        )

    expected_plan_hash = evidence_module.sha256_json(evidence["proposed_plan"])
    if final_audit.get("plan_sha256") != expected_plan_hash:
        raise ProvisioningNotAuthorized(
            "Plan hash mismatch: the evidence packet's plan does not match what "
            "was actually signed. The plan may have been regenerated or edited "
            "after approval. Provisioning refused."
        )

    return True


def verify_plan_file_integrity(manifest: dict, workdir, plan_file: str = "tfplan") -> bool:
    """A second, independent check from authorize_provisioning() above —
    that one verifies the human signed off on this *configuration*; this one
    verifies the *literal plan file on disk right now* is byte-identical to
    the one whose hash was recorded in the manifest at generation time.

    These catch different failure modes. authorize_provisioning() catches
    "the approved configuration evidence was edited after signing." This check
    catches replacement, mutation, or re-planning of the saved plan artifact
    between approval and apply. Both must pass before apply. Terraform itself
    remains responsible for rejecting a saved plan that is stale relative to
    the state it was created from.
    """
    from . import terraform_runner  # local import avoids a hard dependency

    if not manifest.get("terraform_plan_file_sha256"):
        raise ProvisioningNotAuthorized(
            "The human approval did not cover a specific Terraform execution "
            "plan (no terraform_plan_file_sha256 on the signed audit record). "
            "There is no fallback to an unsigned or freshly-generated plan — "
            "generate a Terraform plan bound to a new approval before applying."
        )

    current_hash = terraform_runner.hash_plan_file(workdir, plan_file)
    if current_hash != manifest["terraform_plan_file_sha256"]:
        raise ProvisioningNotAuthorized(
            "Terraform plan file on disk does not match the plan that was "
            f"approved (approved={manifest['terraform_plan_file_sha256']!r}, "
            f"current={current_hash!r}). Re-plan, get it re-approved, and "
            "regenerate the manifest before applying."
        )

    return True

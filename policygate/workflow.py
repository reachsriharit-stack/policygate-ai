"""End-to-end workflow orchestration with a hard human approval boundary."""
from __future__ import annotations

import os
from dataclasses import dataclass

from .audit import build_pre_sign_audit
from .evidence import build_evidence_packet
from .foxit_client import FoxitESignClient, FoxitNotConfigured, HumanApprovalHandoff, mock_handoff
from .parser import parse
from .pdf_render import render_evidence_pdf
from .planner import build_plan
from .provisioning.plan_binding import generate_and_plan
from .rules import evaluate
from .runtime_status import enforce_submission_mode
from .schema import PolicyResult, WorkflowState


@dataclass
class WorkflowResult:
    state: WorkflowState
    policy_result: PolicyResult
    evidence: dict | None = None
    pdf_bytes: bytes | None = None
    handoff: HumanApprovalHandoff | None = None
    audit_record: dict | None = None


def run_workflow(
    nl_request: str,
    requested_by: str = "Demo Engineer",
    approver_name: str | None = None,
    approver_email: str | None = None,
    include_terraform_plan: bool | None = None,
) -> WorkflowResult:
    if include_terraform_plan is None:
        include_terraform_plan = os.getenv("POLICYGATE_INCLUDE_TERRAFORM_PLAN", "false").lower() == "true"
    enforce_submission_mode(include_terraform_plan)

    request = parse(nl_request, requested_by=requested_by)
    if approver_name:
        request.approver_name = approver_name
    if approver_email:
        request.approver_email = approver_email

    plan = build_plan(request)
    policy_result = evaluate(request, plan)
    if not policy_result.passed:
        return WorkflowResult(state=WorkflowState.BLOCKED, policy_result=policy_result)

    evidence = build_evidence_packet(policy_result)

    # Off by default: this calls the real terraform CLI against a real AWS
    # provider (see provisioning/plan_binding.py's docstring for why there's
    # no mock mode). Opt in explicitly with POLICYGATE_INCLUDE_TERRAFORM_PLAN
    # or the include_terraform_plan argument once terraform/AWS are ready.
    if include_terraform_plan:
        workdir = f"terraform/{request.request_id}"
        terraform_plan = generate_and_plan(evidence, workdir)
        evidence = build_evidence_packet(policy_result, terraform_plan=terraform_plan)

    pdf_bytes = render_evidence_pdf(evidence)

    client = FoxitESignClient()
    signer_email = request.approver_email
    if not signer_email:
        # Defensive invariant: APR-02 should already have blocked this path.
        raise RuntimeError("Validated production request has no approver email")
    if client.configured:
        handoff = client.create_human_approval_draft(
            pdf_bytes=pdf_bytes,
            signer_name=request.approver_name or "Human Approver",
            signer_email=signer_email,
            request_id=request.request_id,
            create_embedded_session=(os.getenv("POLICYGATE_EMBEDDED_SIGNING", "false").lower() == "true"),
            send_now=(os.getenv("POLICYGATE_FOXIT_SEND_NOW", "false").lower() == "true"),
        )
    else:
        handoff = mock_handoff(signer_email, request.request_id)

    audit = build_pre_sign_audit(evidence, pdf_bytes, handoff)

    # HARD STOP: no code path below this line signs, approves, or executes infra.
    return WorkflowResult(
        state=WorkflowState.AWAITING_HUMAN_APPROVAL,
        policy_result=policy_result,
        evidence=evidence,
        pdf_bytes=pdf_bytes,
        handoff=handoff,
        audit_record=audit,
    )

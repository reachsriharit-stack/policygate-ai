"""Judge-friendly PolicyGate UI. Run: streamlit run policygate/streamlit_app.py

This page reports evidence; it does not produce it. Every verified state comes
from demo-evidence.json, the sanitized record written by
.github/workflows/final-policygate-demo.yml. Nothing here calls Claude, AWS,
Terraform, Foxit MCP or Foxit eSign — the workflow is the source of truth, and
with no verified evidence present this page keeps its honest offline labels.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Streamlit Cloud runs this file directly, so sys.path[0] is policygate/ and
# the `policygate` package itself is not importable. Put the repository root
# on the path before any package import. Derived from __file__, so it works
# wherever the checkout lives.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from policygate import demo_evidence
from policygate.runtime_status import get_runtime_status
from policygate.schema import WorkflowState
from policygate.workflow import run_workflow

DASH = "—"


def _status_box(label: str, value: str, live_prefixes: tuple[str, ...] = ("LIVE", "CONFIGURED")) -> None:
    text = f"**{label}**\n\n{value}"
    if "fallback" in value.lower():
        st.warning(text)
    elif value.startswith(live_prefixes):
        st.success(text)
    elif value in {"MOCK", "OFFLINE PARSER", "NOT CONFIGURED", "DISABLED"}:
        st.warning(text)
    else:
        st.info(text)


def _plan_counts(summary: str) -> str | None:
    # Terraform prints e.g. "Plan: 4 to add, 0 to change, 0 to destroy."
    m = re.search(r"Plan:\s*(\d+\s+to add,\s*\d+\s+to change,\s*\d+\s+to destroy)", summary)
    return m.group(1) if m else None


def _yes_no(value) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return DASH


def _shown(evidence: dict, field: str) -> str:
    value = evidence.get(field)
    return DASH if value in (None, "") else str(value)


st.set_page_config(page_title="PolicyGate AI", page_icon="🛡️", layout="wide")
st.title("🛡️ PolicyGate AI")
st.caption("AI can propose. Policy can validate. Only a human can authorize.")

runtime = get_runtime_status()

# Badges come from evidence a final run actually produced, never from this
# process asserting anything about itself.
try:
    evidence = demo_evidence.load()
except demo_evidence.UnsafeEvidence as exc:
    evidence = None
    st.error(f"Demo evidence rejected as unsafe to display: {exc}")
badges = demo_evidence.badges(evidence)

if badges:
    st.success(
        "Verified evidence from a completed end-to-end run "
        "(final-policygate-demo.yml). Every value below is what that run "
        "observed; this page asserts nothing about itself."
    )
    badge_cols = st.columns(len(badges))
    for col, (label, value) in zip(badge_cols, badges.items()):
        with col:
            _status_box(label, value, live_prefixes=("LIVE", "PASS", "VERIFIED"))
else:
    cols = st.columns(5)
    with cols[0]:
        _status_box("Claude", runtime.claude)
    with cols[1]:
        _status_box("Foxit eSign", runtime.foxit_esign)
    with cols[2]:
        _status_box("Foxit MCP", runtime.foxit_mcp)
    with cols[3]:
        _status_box("Terraform", runtime.terraform_plan)
    with cols[4]:
        _status_box("Submission mode", "LIVE-ONLY" if runtime.submission_mode else "OFF")
    if evidence:
        st.info(
            "Demo evidence is present but does not describe a complete verified "
            "run, so the local runtime status is shown instead."
        )
    else:
        st.info(
            "No verified run evidence is loaded. These labels describe *this* "
            "process only. Run final-policygate-demo.yml and publish its "
            "demo-evidence.json to show the verified end-to-end story."
        )

# --------------------------------------------------------------------------
# The governed flow, told from the evidence of one real run.
# --------------------------------------------------------------------------
if evidence:
    st.divider()
    st.header("The governed change, end to end")
    st.caption(
        "Plain-English request → Claude intent → deterministic controls → generated "
        "Terraform → real plan and hash → approval evidence → Foxit MCP → human "
        "authorization → EXECUTED → final audit."
    )

    # 1 ---------------------------------------------------------------------
    st.subheader("1. Infrastructure Request")
    if evidence.get("request_text"):
        st.markdown(f"> {evidence['request_text']}")
        st.caption("The exact plain-English request the verified run was dispatched with.")
    else:
        st.info("The run did not record the request text.")

    # 2 ---------------------------------------------------------------------
    st.subheader("2. Claude Parsed Intent")
    intent_rows = [
        ("Environment", _shown(evidence, "parsed_environment")),
        ("Cloud", _shown(evidence, "parsed_cloud")),
        ("Region", _shown(evidence, "parsed_region")),
        ("Service", _shown(evidence, "parsed_service")),
        ("High availability", _yes_no(evidence.get("parsed_high_availability"))),
        (
            "Backup retention",
            f"{evidence['parsed_backup_retention_days']} days"
            if evidence.get("parsed_backup_retention_days") is not None
            else DASH,
        ),
        (
            "Budget ceiling",
            f"${evidence['parsed_budget_monthly']:,.0f}/month"
            if evidence.get("parsed_budget_monthly") is not None
            else DASH,
        ),
    ]
    left, right = st.columns([3, 1])
    with left:
        st.table({"Field": [r[0] for r in intent_rows], "Value": [r[1] for r in intent_rows]})
    with right:
        if evidence.get("claude_live") and evidence.get("claude_fallback_used") is False:
            _status_box("Claude API", "LIVE", live_prefixes=("LIVE",))
            st.caption("Live call, AI fallback disabled.")
        else:
            st.warning("**Claude API**\n\nNOT VERIFIED")
    st.caption("Structured intent only — no raw model output or prompts are displayed.")

    # 3 ---------------------------------------------------------------------
    st.subheader("3. Deterministic Policy Guardrails")
    st.info("Claude extracts intent. Deterministic PolicyGate code decides compliance.")
    requested = evidence.get("requested_controls") or []
    injected = evidence.get("policy_injected_controls") or []
    if requested or injected:
        req_col, inj_col = st.columns(2)
        with req_col:
            st.markdown("**Requested by the user**")
            for control in requested:
                st.markdown(f"- ✓ {control}")
            if not requested:
                st.caption("None recorded.")
        with inj_col:
            st.markdown("**Enforced by PolicyGate**")
            for control in injected:
                st.markdown(f"- ✓ {control}")
            if not injected:
                st.caption("None recorded.")

    rules = evidence.get("policy_rule_results") or []
    if rules:
        st.table(
            {
                "Rule": [r.get("code", DASH) for r in rules],
                "Control": [r.get("description", "") for r in rules],
                "Result": [r.get("result", DASH) for r in rules],
            }
        )
    if evidence.get("policy_result") == "PASS":
        st.success(f"Deterministic guardrails: {evidence['policy_result']}")
    elif evidence.get("policy_result"):
        st.error(f"Deterministic guardrails: {evidence['policy_result']}")

    # 4 ---------------------------------------------------------------------
    st.subheader("4. Generated Infrastructure")
    if evidence.get("terraform_generated"):
        generated_rows = [
            ("Resource type", _shown(evidence, "terraform_resource_type")),
            ("Region", _shown(evidence, "parsed_region")),
            ("Multi-AZ", "Enabled" if evidence.get("terraform_multi_az") else _yes_no(evidence.get("terraform_multi_az"))),
            ("Encryption at rest", "Enabled" if evidence.get("terraform_encrypted") else _yes_no(evidence.get("terraform_encrypted"))),
            (
                "Backup retention",
                f"{evidence['terraform_backup_retention_days']} days"
                if evidence.get("terraform_backup_retention_days") is not None
                else DASH,
            ),
            ("Publicly accessible", _yes_no(evidence.get("terraform_publicly_accessible"))),
            (
                "Credential management",
                "AWS Secrets Manager (RDS-managed)"
                if evidence.get("terraform_managed_password")
                else DASH,
            ),
        ]
        st.table(
            {"Setting": [r[0] for r in generated_rows], "Value": [r[1] for r in generated_rows]}
        )
        if evidence.get("terraform_managed_password"):
            st.code("manage_master_user_password = true", language="hcl")
            st.caption(
                "RDS creates and manages the master credential in Secrets Manager. "
                "PolicyGate never generates, logs or stores a database password."
            )
        preview = evidence.get("terraform_hcl_preview")
        if preview:
            with st.expander("View generated Terraform"):
                st.code(preview, language="hcl")
                st.caption("Sanitized excerpt of the configuration this run generated.")
        else:
            st.caption("No safe HCL excerpt was captured for this run; the summary above is evidence-derived.")
    else:
        st.info("The run did not record generated infrastructure details.")

    # 5 ---------------------------------------------------------------------
    st.subheader("5. Terraform Plan")
    if evidence.get("terraform_live_plan"):
        _status_box("Terraform", "LIVE PLAN", live_prefixes=("LIVE",))
    plan_cols = st.columns(3)
    plan_cols[0].metric("Resources to add", evidence.get("terraform_add", DASH))
    plan_cols[1].metric("Resources to change", evidence.get("terraform_change", DASH))
    plan_cols[2].metric("Resources to destroy", evidence.get("terraform_destroy", DASH))
    if evidence.get("terraform_plan_summary"):
        st.code(evidence["terraform_plan_summary"], language="text")
    if evidence.get("terraform_plan_sha256"):
        st.markdown("**Exact tfplan SHA-256**")
        st.code(evidence["terraform_plan_sha256"], language="text")
        st.caption(
            "This SHA-256 identifies the exact binary Terraform plan presented "
            "for human approval."
        )
    ran_cols = st.columns(2)
    ran_cols[0].write(f"**terraform apply**\n\n{'RAN' if evidence.get('terraform_apply_ran') else 'NOT RUN'}")
    ran_cols[1].write(f"**terraform destroy**\n\n{'RAN' if evidence.get('terraform_destroy_ran') else 'NOT RUN'}")

    # 6 ---------------------------------------------------------------------
    st.subheader("6. Change Approval Document")
    if evidence.get("approval_pdf_generated"):
        st.markdown(
            "The approval document contains:\n"
            "- ✓ Infrastructure request\n"
            "- ✓ Claude structured intent\n"
            "- ✓ Deterministic policy decisions\n"
            "- ✓ Terraform plan summary\n"
            "- ✓ Exact tfplan SHA-256\n"
            "- ✓ Human approval requirement"
        )
    if evidence.get("unsigned_pdf_sha256"):
        st.markdown("**Unsigned approval PDF SHA-256**")
        st.code(evidence["unsigned_pdf_sha256"], language="text")
    mcp_cols = st.columns(3)
    with mcp_cols[0]:
        if evidence.get("foxit_mcp_live"):
            _status_box("Foxit MCP", "LIVE", live_prefixes=("LIVE",))
        else:
            st.warning("**Foxit MCP**\n\nNOT VERIFIED")
    with mcp_cols[1]:
        if evidence.get("foxit_mcp_operation_verified"):
            _status_box("MCP operation", "PASS", live_prefixes=("PASS",))
        else:
            st.warning("**MCP operation**\n\nNOT VERIFIED")
    with mcp_cols[2]:
        if evidence.get("foxit_esign_live"):
            _status_box("Foxit eSign", "LIVE", live_prefixes=("LIVE",))
        else:
            st.warning("**Foxit eSign**\n\nNOT VERIFIED")
    if evidence.get("foxit_mcp_output_pdf_sha256"):
        st.markdown("**MCP output PDF SHA-256**")
        st.code(evidence["foxit_mcp_output_pdf_sha256"], language="text")
    st.caption("Approval metadata only: no signer identity, session URL, folder ID or token is recorded.")

    # 7 ---------------------------------------------------------------------
    st.subheader("7. Human Authorization")
    before, after = st.columns(2)
    with before:
        st.markdown("**Before human action**")
        st.warning(
            f"State: {_shown(evidence, 'pre_approval_state')}\n\n"
            f"Agent may sign: {_yes_no(evidence.get('agent_may_sign'))}\n\n"
            f"Agent signed: {_yes_no(evidence.get('agent_signed'))}\n\n"
            f"Provisioning allowed: {_yes_no(evidence.get('provisioning_allowed_before_approval'))}"
        )
        st.caption(
            "PolicyGate has completed everything the agent is authorized to do. "
            "Only the designated human can advance the approval."
        )
    with after:
        st.markdown("**After human action**")
        st.success(
            f"Foxit folder status: {_shown(evidence, 'foxit_status')}\n\n"
            f"Human signature: {'VERIFIED' if evidence.get('human_signature_verified') else 'NOT VERIFIED'}\n\n"
            f"Expected signer: {'MATCH' if evidence.get('signer_match') else 'NO MATCH'}\n\n"
            f"Verified signer: {'MATCH' if evidence.get('signer_match') else 'NO MATCH'}"
        )
        st.caption("Signer identity is deliberately not published here.")

    # 8 ---------------------------------------------------------------------
    st.subheader("8. Approved Plan Verification")
    binding_rows = [
        ("Plan generated before approval", "✓" if evidence.get("terraform_plan_sha256") else DASH),
        ("Plan SHA-256 placed in approval evidence", "✓" if evidence.get("unsigned_pdf_sha256") else DASH),
        (
            "Same plan SHA-256 after human approval",
            "✓ VERIFIED" if evidence.get("terraform_plan_hash_verified") else "NOT VERIFIED",
        ),
        (
            "Terraform re-plan after signing",
            "No" if evidence.get("terraform_replanned_after_signature") is False else "YES",
        ),
    ]
    st.table({"Check": [r[0] for r in binding_rows], "Result": [r[1] for r in binding_rows]})
    st.caption(
        "PolicyGate never substitutes a newly generated plan after approval. The "
        "plan verified after signing is the exact plan the human reviewed."
    )

    # 9 ---------------------------------------------------------------------
    st.subheader("9. Final Audit")
    audit_rows = [
        ("Foxit status", _shown(evidence, "foxit_status")),
        ("Human signature", "VERIFIED" if evidence.get("human_signature_verified") else "NOT VERIFIED"),
        ("Expected / verified signer", "MATCH" if evidence.get("signer_match") else "NO MATCH"),
        ("Terraform plan hash", "VERIFIED" if evidence.get("terraform_plan_hash_verified") else "NOT VERIFIED"),
        ("Signed PDF SHA-256", _shown(evidence, "signed_pdf_sha256")),
        ("terraform apply", "RAN" if evidence.get("terraform_apply_ran") else "NOT RUN"),
        ("terraform destroy", "RAN" if evidence.get("terraform_destroy_ran") else "NOT RUN"),
    ]
    st.table({"Field": [r[0] for r in audit_rows], "Value": [r[1] for r in audit_rows]})
    if str(evidence.get("final_audit_state", "")).upper() == "APPROVED":
        st.success(f"Final audit: {evidence['final_audit_state']}")
    elif evidence.get("final_audit_state"):
        st.warning(f"Final audit: {evidence['final_audit_state']}")

st.divider()

# --------------------------------------------------------------------------
# Local demonstration. This is the offline/mock path — never the verified run.
# --------------------------------------------------------------------------
if runtime.submission_mode:
    st.info(
        "Submission mode is on, so the local demonstration is hidden: this page "
        "shows verified run evidence only."
    )
else:
    st.header("Local demonstration")
    st.warning(
        "Local demonstration — not the verified live integration run. This uses "
        "this process's own parser and a mock Foxit handoff, and cannot start "
        "the GitHub Actions workflow."
    )

    request_text = st.text_area(
        "Plain-English database request",
        value=("Provision prod Postgres on AWS in us-east-1. HA required, 30-day backups, "
               "maximum budget $900/month. Approver: Jane Smith."),
        height=120,
    )
    col1, col2, col3 = st.columns(3)
    requested_by = col1.text_input("Requester", "Demo Engineer")
    approver_name = col2.text_input("Approver name", "Jane Smith")
    approver_email = col3.text_input("Approver email", "jane@example.com")

    if st.button("Run local demonstration", type="primary"):
        try:
            result = run_workflow(request_text, requested_by, approver_name, approver_email)
        except Exception as exc:
            st.error(f"Workflow stopped: {exc}")
            st.stop()

        req = result.policy_result.request
        plan = result.policy_result.plan

        st.subheader("AI interpretation")
        st.json({
            "request_id": req.request_id,
            "environment": req.environment,
            "cloud": req.cloud,
            "database_engine": req.database_engine,
            "region": req.region,
            "high_availability_requested": req.high_availability,
            "backup_retention_days_requested": req.backup_retention_days,
            "monthly_budget_usd": req.monthly_budget_usd,
        })

        st.subheader("Deterministic plan")
        st.json(plan.__dict__)

        st.subheader("Deterministic guardrails")
        for c in result.policy_result.checks:
            icon = "✅" if c.passed else "❌"
            st.write(f"{icon} **{c.code} — {c.description}** · actual `{c.actual}` · expected `{c.expected}`")

        if result.state == WorkflowState.BLOCKED:
            st.error("BLOCKED: policy violations prevent document routing.")
        else:
            terraform_plan = (result.evidence or {}).get("terraform_plan") or {}
            if terraform_plan:
                st.subheader("Terraform plan bound to approval")
                summary = terraform_plan.get("plan_summary", "")
                counts = _plan_counts(summary)
                if counts:
                    st.success(f"Terraform plan: {counts}")
                st.code(summary, language="text")
                st.code(f"Approved tfplan SHA-256: {terraform_plan.get('plan_file_sha256')}")
            else:
                st.caption("Terraform planning is disabled for this local run.")

            st.subheader("Change Approval Evidence Packet")
            st.download_button(
                "Download approval PDF",
                data=result.pdf_bytes,
                file_name=f"{req.request_id}-approval.pdf",
                mime="application/pdf",
            )
            st.code(f"Configuration plan SHA-256: {result.evidence['plan_sha256']}")

            st.subheader("Human approval boundary")
            if result.handoff.mock:
                st.error("FOXIT ESIGN: MOCK — this local run is not evidence of the live sponsor integration.")
            else:
                st.success("FOXIT ESIGN: LIVE handoff created")
            st.warning("🛑 AGENT EXECUTION STOPPED — AWAITING HUMAN APPROVAL")
            st.caption(
                "There is intentionally no agent-side sign or approve operation. "
                "Terraform apply is a separate post-sign command that re-verifies "
                "the signed plan."
            )

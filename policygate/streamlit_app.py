"""Judge-friendly PolicyGate UI. Run: streamlit run policygate/streamlit_app.py"""
from __future__ import annotations

import os
import re

import streamlit as st

from policygate.runtime_status import get_runtime_status
from policygate.schema import WorkflowState
from policygate.workflow import run_workflow


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


st.set_page_config(page_title="PolicyGate AI", page_icon="🛡️", layout="wide")
st.title("🛡️ PolicyGate AI")
st.caption("AI can propose. Policy can validate. Only a human can authorize.")

runtime = get_runtime_status()
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

if runtime.submission_mode:
    st.info("Submission mode is fail-closed: AI fallback, missing Foxit MCP/eSign credentials, ambiguous signing routes, or a disabled Terraform plan will stop the run.")

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

if st.button("Run governed workflow", type="primary"):
    try:
        result = run_workflow(request_text, requested_by, approver_name, approver_email)
    except Exception as exc:
        st.error(f"Workflow stopped: {exc}")
        st.stop()

    req = result.policy_result.request
    plan = result.policy_result.plan

    st.subheader("1 · AI interpretation")
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

    st.subheader("2 · Deterministic plan")
    st.json(plan.__dict__)

    st.subheader("3 · Deterministic guardrails")
    for c in result.policy_result.checks:
        icon = "✅" if c.passed else "❌"
        st.write(f"{icon} **{c.code} — {c.description}** · actual `{c.actual}` · expected `{c.expected}`")

    if result.state == WorkflowState.BLOCKED:
        st.error("BLOCKED: policy violations prevent document routing.")
    else:
        terraform_plan = (result.evidence or {}).get("terraform_plan") or {}
        if terraform_plan:
            st.subheader("4 · Exact Terraform plan bound to approval")
            summary = terraform_plan.get("plan_summary", "")
            counts = _plan_counts(summary)
            if counts:
                st.success(f"Terraform plan: {counts}")
            else:
                st.info("A real saved Terraform plan was generated.")
            st.code(summary, language="text")
            st.code(f"Approved tfplan SHA-256: {terraform_plan.get('plan_file_sha256')}")
        else:
            st.subheader("4 · Terraform plan")
            st.warning("Terraform planning is disabled for this run. Enable POLICYGATE_INCLUDE_TERRAFORM_PLAN=true for the submission demo.")

        st.subheader("5 · Change Approval Evidence Packet")
        st.download_button(
            "Download approval PDF",
            data=result.pdf_bytes,
            file_name=f"{req.request_id}-approval.pdf",
            mime="application/pdf",
        )
        st.code(f"Configuration plan SHA-256: {result.evidence['plan_sha256']}")

        st.subheader("6 · Foxit human approval boundary")
        if result.handoff.mock:
            st.error("FOXIT ESIGN: MOCK — do not use this run as evidence of the live sponsor integration.")
        else:
            st.success("FOXIT ESIGN: LIVE handoff created")
        st.warning("🛑 AGENT EXECUTION STOPPED — AWAITING HUMAN APPROVAL")
        st.write(f"Foxit folder: `{result.handoff.folder_id}`")
        st.write(f"Expected signer: `{result.handoff.signer_email}`")
        if result.handoff.embedded_session_url:
            st.link_button("Open Foxit human signing session", result.handoff.embedded_session_url)
        st.caption("There is intentionally no agent-side sign or approve operation. Terraform apply is a separate post-sign command that re-verifies the signed plan.")

        st.subheader("Sponsor integration visibility")
        st.write(f"**Foxit MCP:** {get_runtime_status().foxit_mcp}")
        st.caption(
            "Foxit's MCP server runs in the external MCP-compatible host (for example VS Code/Cursor/Claude Desktop). "
            "Capture the actual MCP tool invocation in the submission video; PolicyGate does not falsely label configuration as execution."
        )

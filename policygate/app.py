"""CLI demo for PolicyGate AI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import write_audit_record
from .schema import WorkflowState
from .workflow import run_workflow


def _print_result(result) -> None:
    req = result.policy_result.request
    plan = result.policy_result.plan

    print("=" * 76)
    print("POLICYGATE AI — HUMAN-GOVERNED DATABASE CHANGE CONTROL")
    print("=" * 76)
    print(f"Request ID: {req.request_id}")
    print(f"Requested by: {req.requested_by}")
    print(f"Parsed intent: {req.environment} {req.database_engine} on {req.cloud}/{req.region}")
    print()

    print("DETERMINISTIC PROVISIONING PLAN")
    print(f"  Instance: {plan.instance_class}")
    print(f"  HA: {plan.high_availability}")
    print(f"  Encryption: {plan.encryption_at_rest}")
    print(f"  Backup days: {plan.backup_retention_days}")
    print(f"  Public access: {plan.public_access}")
    print(f"  Estimated cost: ${plan.estimated_monthly_cost_usd:,.0f}/mo")
    print(f"  Estimate source: {plan.estimate_source}")
    print(f"  Policy-injected controls: {', '.join(plan.policy_injected_controls) or 'none'}")
    print()

    print("DETERMINISTIC GUARDRAILS")
    for check in result.policy_result.checks:
        mark = "PASS" if check.passed else "FAIL"
        print(f"  [{mark}] {check.code:<7} {check.description}")
        print(f"         actual={check.actual}; expected={check.expected}")

    if result.state == WorkflowState.BLOCKED:
        print("\nBLOCKED — no document is routed for signature.")
        return

    terraform_plan = (result.evidence or {}).get("terraform_plan")
    if terraform_plan:
        print("\nTERRAFORM PLAN (bound into the approval document)")
        print(f"  {terraform_plan.get('plan_summary', '').strip()}")
        print(f"  Plan file SHA-256: {terraform_plan.get('plan_file_sha256')}")

    print("\nFOXIT HUMAN APPROVAL HANDOFF")
    print(f"  Provider: {result.handoff.provider}")
    print(f"  Folder: {result.handoff.folder_id}")
    print(f"  Signer: {result.handoff.signer_email}")
    if result.handoff.embedded_session_url:
        print("  Embedded human signing session: created (URL intentionally omitted from logs)")
    print("\n🛑 AGENT EXECUTION STOPPED — AWAITING HUMAN APPROVAL")
    print("The agent cannot sign or authorize the production change. This workflow stops before infrastructure execution.")


def main() -> None:
    parser = argparse.ArgumentParser(description="PolicyGate AI hackathon demo")
    parser.add_argument("request_file", nargs="?", default="examples/approve_request.txt")
    parser.add_argument("--requested-by", default="Demo Engineer")
    parser.add_argument("--approver-name", default=None)
    parser.add_argument("--approver-email", default=None)
    parser.add_argument("--artifacts-dir", default="artifacts")
    parser.add_argument(
        "--include-terraform-plan",
        action="store_true",
        help="Generate real Terraform and run `terraform plan` against your configured "
             "AWS provider before building the approval PDF, binding the plan file's "
             "SHA-256 into the document the human signs. Requires terraform installed "
             "and working AWS credentials. No mock mode — see provisioning/plan_binding.py.",
    )
    args = parser.parse_args()

    request_text = Path(args.request_file).read_text(encoding="utf-8").strip()
    result = run_workflow(
        request_text,
        requested_by=args.requested_by,
        approver_name=args.approver_name,
        approver_email=args.approver_email,
        include_terraform_plan=args.include_terraform_plan or None,
    )
    _print_result(result)

    if result.evidence:
        out = Path(args.artifacts_dir)
        out.mkdir(parents=True, exist_ok=True)
        rid = result.policy_result.request.request_id
        (out / f"{rid}-evidence.json").write_text(json.dumps(result.evidence, indent=2), encoding="utf-8")
        (out / f"{rid}-approval.pdf").write_bytes(result.pdf_bytes)
        write_audit_record(result.audit_record, out / f"{rid}-audit-pre-sign.json")
        print(f"\nArtifacts written to: {out.resolve()}")


if __name__ == "__main__":
    main()

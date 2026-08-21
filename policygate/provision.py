"""python -m policygate.provision <evidence.json> [final-audit.json] [--apply]

Two entirely separate code paths, deliberately not sharing plan-generation
logic:

  plan_preview()  — no --apply. Generates Terraform, runs init/validate/plan,
                     hashes the result, writes a manifest. Safe, free,
                     read-only against AWS. This is what produces the plan
                     file that workflow.py binds into the signed PDF, or
                     that you'd run standalone to preview before requesting
                     an approval.

  apply_approved() — --apply. Never generates or re-plans anything. Loads
                     the signed final audit, verifies it, re-hashes whatever
                     plan file already exists on disk, and only if that
                     matches exactly what was signed does it call terraform
                     apply against that SAME file. Regenerating a plan here
                     would silently replace the artifact the human actually
                     looked at — see approval_gate.verify_plan_file_integrity.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .provisioning import terraform_generator, terraform_runner
from .provisioning.approval_gate import ProvisioningNotAuthorized, authorize_provisioning, verify_plan_file_integrity


def plan_preview(evidence: dict, workdir: Path) -> None:
    tf_path = terraform_generator.write_terraform(evidence, workdir)
    print(f"Wrote {tf_path}")

    terraform_runner.run_init(workdir)
    terraform_runner.run_validate(workdir)
    plan_result = terraform_runner.run_plan(workdir)
    print(plan_result.stdout)

    plan_file_hash = terraform_runner.hash_plan_file(workdir)
    show_result = terraform_runner.run_show(workdir)
    manifest_path = terraform_generator.write_plan_manifest(evidence, plan_file_hash, show_result.stdout, workdir)
    print(f"\nPlan file SHA-256: {plan_file_hash}")
    print(f"Plan manifest written to: {manifest_path}")
    print(
        "\nDRY-RUN MODE — terraform apply skipped. This plan file is what "
        "workflow.py binds into the signed PDF when "
        "POLICYGATE_INCLUDE_TERRAFORM_PLAN=true. Pass --apply with a signed "
        "final audit to create real resources (costs real money)."
    )


def apply_approved(evidence: dict, final_audit: dict, workdir: Path) -> None:
    """No terraform_generator or run_plan call anywhere in this function —
    that's the fix. It only ever reads the plan file that's already there."""
    try:
        authorize_provisioning(final_audit, evidence)
        # Re-hashes the EXISTING file in workdir. Raises if it's missing, if
        # the audit has no bound plan hash at all (no fallback — see
        # approval_gate.py), or if the hashes don't match.
        verify_plan_file_integrity(final_audit, workdir)
    except ProvisioningNotAuthorized as exc:
        print(f"PROVISIONING DENIED: {exc}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as exc:
        print(
            f"PROVISIONING DENIED: {exc}\nWas this evidence produced with "
            "POLICYGATE_INCLUDE_TERRAFORM_PLAN=true, and is --workdir pointing "
            "at the same directory that ran in?",
            file=sys.stderr,
        )
        sys.exit(1)

    print("APPROVAL VERIFIED — the existing plan file on disk matches exactly what was signed. No new plan was generated.")
    apply_result = terraform_runner.run_apply(workdir, authorized=True, allow_apply=True)
    print(apply_result.stdout)
    print(
        f"\nReal AWS resources now exist. For deliberate cleanup, set "
        f"POLICYGATE_ALLOW_DESTROY=true and run `python -m policygate.provision "
        f"<evidence.json> --destroy --confirm-request-id {evidence['request_id']} --workdir {workdir}`."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview or apply Terraform for a PolicyGate request")
    parser.add_argument("evidence_path", help="Path to {request_id}-evidence.json")
    parser.add_argument("final_audit_path", nargs="?", help="Path to {request_id}-audit-final.json (required for --apply)")
    parser.add_argument("--workdir", default=None, help="Terraform working directory (default: terraform/<request_id>)")
    parser.add_argument("--apply", action="store_true", help="Apply the EXISTING approved plan file. Costs real money. Never re-plans.")
    parser.add_argument("--destroy", action="store_true", help="Run gated terraform destroy in the workdir instead of plan/apply.")
    parser.add_argument("--confirm-request-id", default=None, help="Required with --destroy; must exactly match the evidence request_id.")
    args = parser.parse_args()

    evidence = json.loads(Path(args.evidence_path).read_text(encoding="utf-8"))
    workdir = Path(args.workdir or f"terraform/{evidence['request_id']}")

    if args.destroy:
        try:
            result = terraform_runner.run_destroy(
                workdir,
                allow_destroy=True,
                request_id=evidence["request_id"],
                confirm_request_id=args.confirm_request_id,
            )
        except PermissionError as exc:
            print(f"DESTROY DENIED: {exc}", file=sys.stderr)
            sys.exit(1)
        print(result.stdout)
        return

    if not args.apply:
        plan_preview(evidence, workdir)
        return

    if not args.final_audit_path:
        print("ERROR: --apply requires final_audit_path (the post-signature audit record).", file=sys.stderr)
        sys.exit(2)

    final_audit = json.loads(Path(args.final_audit_path).read_text(encoding="utf-8"))
    apply_approved(evidence, final_audit, workdir)


if __name__ == "__main__":
    main()

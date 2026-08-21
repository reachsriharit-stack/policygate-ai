"""Bridges workflow.py to the provisioning primitives in this package.

Deliberately a thin function, not a class: it exists so workflow.py can get
a {"plan_summary", "plan_file_sha256"} dict without importing terraform_*
directly, and so this is the one place that decides what "generate and plan
for the approval document" means.

This calls out to the real `terraform` CLI and a real AWS provider. It has
no mock mode — unlike foxit_client.py's mock, faking a plan file and its
hash would defeat the entire point of this feature, which is that the hash
in the signed document corresponds to something Terraform actually
evaluated. If you don't have terraform/AWS credentials available, don't
enable this — see workflow.py's include_terraform_plan option, which
defaults to off for exactly this reason.
"""
from __future__ import annotations

from pathlib import Path

from . import terraform_generator, terraform_runner


def generate_and_plan(evidence_without_terraform: dict, workdir: str | Path) -> dict:
    """evidence_without_terraform needs request_id, plan_sha256, and
    proposed_plan — i.e. an evidence packet built by build_evidence_packet()
    before the terraform_plan argument is known. Returns the dict to pass
    back into build_evidence_packet(..., terraform_plan=this_dict)."""
    terraform_generator.write_terraform(evidence_without_terraform, workdir)
    terraform_runner.run_init(workdir)
    terraform_runner.run_validate(workdir)
    terraform_runner.run_plan(workdir)

    plan_file_sha256 = terraform_runner.hash_plan_file(workdir)
    show_result = terraform_runner.run_show(workdir)

    return {
        "plan_summary": show_result.stdout.strip(),
        "plan_file_sha256": plan_file_sha256,
    }

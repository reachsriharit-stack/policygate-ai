"""Thin subprocess wrapper around the terraform CLI.

init / validate / plan never create or modify real infrastructure — they're
always allowed. apply is where real AWS resources (and real cost) start, so
it's gated three separate, independent ways. All three must be true:

  1. approval_gate.authorize_provisioning() returned True for this exact
     evidence/audit pair (caller's responsibility to call this first).
  2. The POLICYGATE_ALLOW_APPLY environment variable is exactly "true".
  3. The caller explicitly passes allow_apply=True to run_apply().

Any one of these being false/missing stops apply. This is deliberately
redundant — a bug in one gate should not be enough to spend real money.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


class TerraformNotInstalled(RuntimeError):
    pass


class TerraformCommandFailed(RuntimeError):
    def __init__(self, command: list[str], returncode: int, stdout: str, stderr: str):
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(f"{' '.join(command)} exited {returncode}:\n{stderr}")


@dataclass
class TerraformResult:
    command: list[str]
    stdout: str
    stderr: str


def _run(workdir: Path, args: list[str]) -> TerraformResult:
    command = ["terraform", *args]
    try:
        proc = subprocess.run(
            command, cwd=str(workdir), capture_output=True, text=True, timeout=600
        )
    except FileNotFoundError as exc:
        raise TerraformNotInstalled(
            "The `terraform` CLI was not found on PATH. Install it from "
            "https://developer.hashicorp.com/terraform/install before running "
            "this module."
        ) from exc

    if proc.returncode != 0:
        raise TerraformCommandFailed(command, proc.returncode, proc.stdout, proc.stderr)
    return TerraformResult(command=command, stdout=proc.stdout, stderr=proc.stderr)


def run_init(workdir: str | Path) -> TerraformResult:
    return _run(Path(workdir), ["init", "-input=false"])


def run_validate(workdir: str | Path) -> TerraformResult:
    return _run(Path(workdir), ["validate"])


def run_plan(workdir: str | Path, out_file: str = "tfplan") -> TerraformResult:
    return _run(Path(workdir), ["plan", "-input=false", f"-out={out_file}"])


def run_show(workdir: str | Path, plan_file: str = "tfplan") -> TerraformResult:
    """Human-readable summary of a saved plan file — e.g. 'Plan: 1 to add,
    0 to change, 0 to destroy.' This is what goes in front of the human
    approver, not a description of the plan — the plan itself."""
    return _run(Path(workdir), ["show", "-no-color", plan_file])


def hash_plan_file(workdir: str | Path, plan_file: str = "tfplan") -> str:
    """SHA-256 of the saved plan file's actual bytes. Pure file I/O — no
    subprocess, no terraform binary required, which is deliberate: this
    function has to be trustworthy even in contexts where invoking
    terraform itself would be inappropriate (e.g. re-verifying at apply
    time without re-planning, which would itself defeat the point)."""
    path = Path(workdir) / plan_file
    if not path.exists():
        raise FileNotFoundError(
            f"No plan file at {path}. Run run_plan() first — a plan file "
            "hash is only meaningful for a plan that was actually produced."
        )
    return sha256(path.read_bytes()).hexdigest()


def run_apply(
    workdir: str | Path,
    *,
    authorized: bool,
    allow_apply: bool = False,
    plan_file: str = "tfplan",
) -> TerraformResult:
    """Real infrastructure gets created here. All three gates must pass:
    authorized (from approval_gate), allow_apply (explicit caller opt-in),
    and POLICYGATE_ALLOW_APPLY=true in the environment."""
    if not authorized:
        raise PermissionError(
            "run_apply() called with authorized=False. Call "
            "approval_gate.authorize_provisioning() first and pass its result."
        )
    if not allow_apply:
        raise PermissionError(
            "run_apply() called with allow_apply=False. This is the explicit "
            "caller-side opt-in — pass allow_apply=True deliberately."
        )
    if os.environ.get("POLICYGATE_ALLOW_APPLY") != "true":
        raise PermissionError(
            "POLICYGATE_ALLOW_APPLY is not set to 'true' in the environment. "
            "This is the third independent gate on real spend — set it "
            "deliberately, and unset it again right after your demo."
        )
    return _run(Path(workdir), ["apply", "-input=false", "-auto-approve", plan_file])


def run_destroy(
    workdir: str | Path,
    *,
    allow_destroy: bool = False,
    request_id: str | None = None,
    confirm_request_id: str | None = None,
) -> TerraformResult:
    """Destroy real infrastructure only with deliberate operator confirmation.

    Destroy is not a human *approval* action in this demo, but it is still a
    destructive cloud operation. It therefore requires an explicit caller opt-in,
    POLICYGATE_ALLOW_DESTROY=true, and an exact request-ID confirmation.
    """
    if not allow_destroy:
        raise PermissionError("run_destroy() called with allow_destroy=False.")
    if os.environ.get("POLICYGATE_ALLOW_DESTROY") != "true":
        raise PermissionError(
            "POLICYGATE_ALLOW_DESTROY is not set to 'true'. Enable it only for deliberate demo cleanup."
        )
    if not request_id or confirm_request_id != request_id:
        raise PermissionError(
            "Destroy confirmation failed. Pass the exact request ID through --confirm-request-id."
        )
    return _run(Path(workdir), ["destroy", "-input=false", "-auto-approve"])

"""Runtime-mode helpers used by the UI and submission safety checks."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeStatus:
    claude: str
    foxit_esign: str
    foxit_mcp: str
    terraform_plan: str
    submission_mode: bool


def _truthy(name: str) -> bool:
    return os.getenv(name, "false").lower() == "true"


def _esign_configured() -> bool:
    """Credentials for the transport foxit_client will actually use.

    The Developer Platform transport authenticates with the FOXIT_CLOUD_API_*
    credentials, so checking only the portal's FOXIT_ESIGN_* pair would call a
    fully live gateway setup 'mock' — and would call a portal-only setup live
    even when the gateway transport is selected.
    """
    if os.getenv("FOXIT_ESIGN_TRANSPORT", "esign_oauth").strip().lower() == "developer_platform":
        return bool(
            os.getenv("FOXIT_CLOUD_API_CLIENT_ID") and os.getenv("FOXIT_CLOUD_API_CLIENT_SECRET")
        )
    return bool(os.getenv("FOXIT_ESIGN_CLIENT_ID") and os.getenv("FOXIT_ESIGN_CLIENT_SECRET"))


def get_runtime_status(include_terraform_plan: bool | None = None) -> RuntimeStatus:
    if os.getenv("ANTHROPIC_API_KEY"):
        claude = "LIVE (fallback enabled)" if _truthy("POLICYGATE_ALLOW_AI_FALLBACK") else "LIVE"
    else:
        claude = "OFFLINE PARSER"
    foxit_esign = "LIVE" if _esign_configured() else "MOCK"
    foxit_mcp = (
        "CONFIGURED (external MCP host)"
        if os.getenv("FOXIT_CLOUD_API_CLIENT_ID") and os.getenv("FOXIT_CLOUD_API_CLIENT_SECRET")
        else "NOT CONFIGURED"
    )
    if include_terraform_plan is None:
        include_terraform_plan = _truthy("POLICYGATE_INCLUDE_TERRAFORM_PLAN")
    terraform_plan = "LIVE PLAN" if include_terraform_plan else "DISABLED"
    return RuntimeStatus(
        claude=claude,
        foxit_esign=foxit_esign,
        foxit_mcp=foxit_mcp,
        terraform_plan=terraform_plan,
        submission_mode=_truthy("POLICYGATE_SUBMISSION_MODE"),
    )


def enforce_submission_mode(include_terraform_plan: bool) -> None:
    """Fail closed so a recorded submission cannot silently use mock paths."""
    if not _truthy("POLICYGATE_SUBMISSION_MODE"):
        return

    missing: list[str] = []
    if not os.getenv("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY (live Claude)")
    if _truthy("POLICYGATE_ALLOW_AI_FALLBACK"):
        missing.append("POLICYGATE_ALLOW_AI_FALLBACK=false")
    if not _esign_configured():
        missing.append("Foxit eSign credentials")
    if not (os.getenv("FOXIT_CLOUD_API_CLIENT_ID") and os.getenv("FOXIT_CLOUD_API_CLIENT_SECRET")):
        missing.append("Foxit PDF/MCP credentials")
    if not include_terraform_plan:
        missing.append("POLICYGATE_INCLUDE_TERRAFORM_PLAN=true")
    send_now = _truthy("POLICYGATE_FOXIT_SEND_NOW")
    embedded = _truthy("POLICYGATE_EMBEDDED_SIGNING")
    if not (send_now or embedded):
        missing.append("a live human signing route (FOXIT_SEND_NOW or EMBEDDED_SIGNING)")
    elif send_now and embedded:
        missing.append("exactly one human signing route (not both FOXIT_SEND_NOW and EMBEDDED_SIGNING)")

    if missing:
        raise RuntimeError(
            "POLICYGATE_SUBMISSION_MODE=true refuses mock/incomplete execution. Missing: "
            + ", ".join(missing)
        )

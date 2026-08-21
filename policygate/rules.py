"""Deterministic, auditable policy guardrails."""
from __future__ import annotations

import re

from .schema import ChangeRequest, OrganizationPolicy, PolicyResult, ProvisioningPlan, RuleCheck


def _check(code: str, description: str, passed: bool, actual, expected, detail: str) -> RuleCheck:
    return RuleCheck(
        code=code,
        description=description,
        passed=passed,
        actual=str(actual),
        expected=str(expected),
        detail=detail,
    )


def evaluate(
    request: ChangeRequest,
    plan: ProvisioningPlan,
    policy: OrganizationPolicy | None = None,
) -> PolicyResult:
    policy = policy or OrganizationPolicy()
    production = request.environment == "production"
    checks: list[RuleCheck] = []

    checks.append(_check(
        "REG-01",
        "AWS region is approved",
        plan.region in policy.approved_regions,
        plan.region,
        policy.approved_regions,
        "Region allow-list is deterministic policy.",
    ))

    if production:
        checks.append(_check(
            "SEC-01", "Encryption at rest required", plan.encryption_at_rest is True,
            plan.encryption_at_rest, True,
            "Production storage must be encrypted.",
        ))
        checks.append(_check(
            "HA-01", "Multi-AZ / high availability required", plan.high_availability is True,
            plan.high_availability, True,
            "Production databases must be highly available.",
        ))
        checks.append(_check(
            "BKP-01", "Backup retention meets minimum",
            plan.backup_retention_days >= policy.minimum_production_backup_days,
            plan.backup_retention_days, f">= {policy.minimum_production_backup_days}",
            "Production backup retention is policy-controlled.",
        ))
        checks.append(_check(
            "NET-01", "Public access prohibited", plan.public_access is False,
            plan.public_access, False,
            "Production databases must remain on private network paths.",
        ))

    user_budget = (
        request.monthly_budget_usd
        if request.monthly_budget_usd is not None
        else policy.maximum_monthly_budget_usd
    )
    allowed_budget = min(user_budget, policy.maximum_monthly_budget_usd)
    checks.append(_check(
        "COST-01", "Estimated monthly cost within allowed budget",
        plan.estimated_monthly_cost_usd <= allowed_budget,
        f"${plan.estimated_monthly_cost_usd:,.0f}", f"<= ${allowed_budget:,.0f}",
        "Uses the fixed demo cost catalog; replace with a live estimator in production.",
    ))

    approver_ok = (not production) or bool((request.approver_name or "").strip())
    checks.append(_check(
        "APR-01", "Named human approver required for production",
        approver_ok,
        request.approver_name or "UNSPECIFIED", "named human approver",
        "The AI is not an approver and cannot satisfy this control.",
    ))

    email = (request.approver_email or "").strip()
    email_ok = (not production) or bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email))
    checks.append(_check(
        "APR-02", "Routable human approver email required for production",
        email_ok,
        email or "UNSPECIFIED", "valid approver email",
        "Foxit routing must target an explicitly identified human account; demo fallback addresses are not permitted.",
    ))

    return PolicyResult(
        request=request,
        plan=plan,
        policy_version=policy.version,
        checks=checks,
    )

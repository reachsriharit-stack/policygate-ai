"""Deterministic AWS PostgreSQL demo planner.

This is intentionally NOT live AWS pricing. A fixed catalog makes the hackathon
demo replayable; the UI labels the estimate source so it cannot be mistaken for
a current quote.
"""
from __future__ import annotations

from .schema import ChangeRequest, OrganizationPolicy, ProvisioningPlan

DEMO_MONTHLY_COST = {
    "development": ("db.t4g.medium", 210.0),
    "staging": ("db.r6g.large", 560.0),
    "production": ("db.r6g.large", 817.0),
}


def _policy_or_explicit(value, policy_value, control_name: str, injected: list[str]):
    if value is None:
        injected.append(control_name)
        return policy_value
    return value


def build_plan(request: ChangeRequest, policy: OrganizationPolicy | None = None) -> ProvisioningPlan:
    policy = policy or OrganizationPolicy()
    injected: list[str] = []

    production = request.environment == "production"
    encryption = _policy_or_explicit(
        request.encryption_at_rest,
        policy.production_encryption_required if production else True,
        "encryption_at_rest",
        injected,
    )
    public_access = _policy_or_explicit(
        request.public_access,
        False if production and policy.production_private_access_required else False,
        "private_network_access",
        injected,
    )
    high_availability = _policy_or_explicit(
        request.high_availability,
        policy.production_high_availability_required if production else False,
        "high_availability",
        injected,
    )
    backup_retention_days = _policy_or_explicit(
        request.backup_retention_days,
        policy.minimum_production_backup_days if production else 1,
        "backup_retention_days",
        injected,
    )

    instance_class, estimated_cost = DEMO_MONTHLY_COST[request.environment]
    return ProvisioningPlan(
        cloud="aws",
        service="rds",
        database_engine="postgresql",
        environment=request.environment,
        region=request.region,
        instance_class=instance_class,
        high_availability=bool(high_availability),
        encryption_at_rest=bool(encryption),
        backup_retention_days=int(backup_retention_days),
        public_access=bool(public_access),
        estimated_monthly_cost_usd=estimated_cost,
        estimate_source="fixed hackathon demo catalog (not live AWS pricing)",
        policy_injected_controls=injected,
    )

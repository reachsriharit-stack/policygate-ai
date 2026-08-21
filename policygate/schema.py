"""Typed domain model for the PolicyGate AI MVP."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class WorkflowState(str, Enum):
    RECEIVED = "RECEIVED"
    PARSED = "PARSED"
    VALIDATED = "VALIDATED"
    BLOCKED = "BLOCKED"
    AWAITING_HUMAN_APPROVAL = "AWAITING_HUMAN_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass
class ChangeRequest:
    request_id: str
    requested_by: str
    environment: str
    cloud: str
    database_engine: str
    region: str = "us-east-1"
    high_availability: Optional[bool] = None
    encryption_at_rest: Optional[bool] = None
    backup_retention_days: Optional[int] = None
    public_access: Optional[bool] = None
    monthly_budget_usd: Optional[float] = None
    approver_name: Optional[str] = None
    approver_email: Optional[str] = None
    justification: Optional[str] = None


@dataclass
class OrganizationPolicy:
    version: str = "2026.08"
    approved_regions: tuple[str, ...] = ("us-east-1", "us-east-2", "us-west-2")
    production_encryption_required: bool = True
    production_private_access_required: bool = True
    production_high_availability_required: bool = True
    minimum_production_backup_days: int = 30
    maximum_monthly_budget_usd: float = 1000.0
    human_approval_required_for_production: bool = True


@dataclass
class ProvisioningPlan:
    cloud: str
    service: str
    database_engine: str
    environment: str
    region: str
    instance_class: str
    high_availability: bool
    encryption_at_rest: bool
    backup_retention_days: int
    public_access: bool
    estimated_monthly_cost_usd: float
    estimate_source: str
    policy_injected_controls: list[str] = field(default_factory=list)


@dataclass
class RuleCheck:
    code: str
    description: str
    passed: bool
    actual: str
    expected: str
    detail: str


@dataclass
class PolicyResult:
    request: ChangeRequest
    plan: ProvisioningPlan
    policy_version: str
    checks: list[RuleCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)

    @property
    def failed_checks(self) -> list[RuleCheck]:
        return [c for c in self.checks if not c.passed]

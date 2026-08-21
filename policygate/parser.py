"""Natural-language intent extraction.

Claude is allowed to interpret intent only. Compliance decisions live in
rules.py and authorization is always human.
"""
from __future__ import annotations

import os
import re
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .schema import ChangeRequest


class ParsedIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: Literal["production", "staging", "development"]
    cloud: Literal["aws"]
    database_engine: Literal["postgresql"]
    region: str = "us-east-1"
    high_availability: Optional[bool] = None
    encryption_at_rest: Optional[bool] = None
    backup_retention_days: Optional[int] = Field(default=None, ge=0, le=365)
    public_access: Optional[bool] = None
    monthly_budget_usd: Optional[float] = Field(default=None, gt=0)
    approver_name: Optional[str] = None
    approver_email: Optional[str] = None
    justification: Optional[str] = None


SYSTEM_PROMPT = """Extract database provisioning intent into the supplied schema.

Security and governance rules:
- You only EXTRACT what the requester asked for. You do not decide compliance.
- Never approve, reject, authorize, sign, or claim a production change is safe.
- This MVP supports only AWS PostgreSQL.
- Normalize prod -> production and stage -> staging.
- If a control was not stated, return null. Do not invent a compliant value.
- Do not estimate cloud cost. monthly_budget_usd is the user's stated budget only.
- Extract approver name/email only when explicitly present.
"""


def _next_request_id() -> str:
    return f"PG-{uuid.uuid4().hex[:10].upper()}"


def _to_request(intent: ParsedIntent, requested_by: str) -> ChangeRequest:
    return ChangeRequest(
        request_id=_next_request_id(),
        requested_by=requested_by,
        **intent.model_dump(),
    )


def parse_with_claude(nl_request: str, requested_by: str) -> ChangeRequest:
    from anthropic import Anthropic

    client = Anthropic()
    response = client.messages.parse(
        model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5"),
        max_tokens=700,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": nl_request}],
        output_format=ParsedIntent,
    )
    if response.parsed_output is None:
        raise RuntimeError(f"Claude returned no parsed output (stop_reason={response.stop_reason})")
    return _to_request(response.parsed_output, requested_by)


def parse_offline(nl_request: str, requested_by: str) -> ChangeRequest:
    """Deterministic heuristic parser for local demos with no API key.

    It is deliberately conservative: omitted controls remain None, while
    explicit negative requests are preserved so policy code can block them.
    """
    text = nl_request.lower()

    def contains(*phrases: str) -> bool:
        return any(p in text for p in phrases)

    environment = (
        "production" if contains("production", "prod ", "prod,")
        else "staging" if contains("staging", "stage ", "stage,")
        else "development"
    )

    region_match = re.search(r"\b(us-(?:east|west)-\d)\b", text)
    region = region_match.group(1) if region_match else "us-east-1"

    dollar_amounts = [float(x.replace(",", "")) for x in re.findall(r"\$\s?([\d,]+(?:\.\d+)?)", text)]
    budget = dollar_amounts[0] if dollar_amounts else None

    backup_match = re.search(r"(\d+)\s*[- ]?day(?:s)?\s+(?:backup|retention)", text)
    if not backup_match:
        backup_match = re.search(r"backup(?:s)?(?:\s+for)?\s+(\d+)\s*[- ]?day", text)
    backup_days = int(backup_match.group(1)) if backup_match else None

    if contains("single az", "single-az", "no ha", "without ha", "no high availability"):
        ha = False
    elif contains("multi-az", "multi az", "high availability", "ha required", "ha=true"):
        ha = True
    else:
        ha = None

    if contains("no encryption", "unencrypted", "encryption disabled"):
        encryption = False
    elif contains("encryption enabled", "encrypted", "encryption required"):
        encryption = True
    else:
        encryption = None

    if contains("public access enabled", "publicly accessible", "public access: yes"):
        public_access = True
    elif contains("no public access", "private only", "private network", "public access: no"):
        public_access = False
    else:
        public_access = None

    email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", nl_request)
    approver_email = email_match.group(0) if email_match else None
    name_match = re.search(r"approver\s*[:=-]\s*([A-Za-z][A-Za-z .'-]{1,60})", nl_request, re.I)
    approver_name = name_match.group(1).strip().rstrip(".,") if name_match else None

    return ChangeRequest(
        request_id=_next_request_id(),
        requested_by=requested_by,
        environment=environment,
        cloud="aws",
        database_engine="postgresql",
        region=region,
        high_availability=ha,
        encryption_at_rest=encryption,
        backup_retention_days=backup_days,
        public_access=public_access,
        monthly_budget_usd=budget,
        approver_name=approver_name,
        approver_email=approver_email,
    )


def parse(nl_request: str, requested_by: str = "Demo Engineer") -> ChangeRequest:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return parse_offline(nl_request, requested_by)

    try:
        return parse_with_claude(nl_request, requested_by)
    except Exception:
        if os.getenv("POLICYGATE_ALLOW_AI_FALLBACK", "false").lower() == "true":
            return parse_offline(nl_request, requested_by)
        raise

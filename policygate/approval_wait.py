"""Wait for a human to finish signing in Foxit eSign.

The wait is deliberately dumb and read-only: it polls one folder's status and
returns only when Foxit reports ``EXECUTED``. It cannot sign, cannot approve,
and cannot reach any provisioning code — the only thing it is allowed to do is
ask "has the human finished yet?".

``EXECUTED`` is the only status that counts. Foxit reports several states that
look encouraging and are not an executed signature — ``SENT`` (the invitation
went out), ``SHARED``, ``VIEWED``, and notably ``COMPLETED``, which can appear
before the final executed documents exist. Treating any of those as approval
would authorize a production change on the strength of an email being opened.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

APPROVED_STATUS = "EXECUTED"

#: Statuses Foxit reports that are explicitly *not* an executed signature.
#: Documented so a reader can see they were considered and rejected, not
#: overlooked; anything unrecognised is also treated as not-approved.
NON_APPROVING_STATUSES = frozenset(
    {
        "DRAFT",
        "SENT",
        "SHARED",
        "VIEWED",
        "IN PROGRESS",
        "INPROGRESS",
        "COMPLETED",
        "UNKNOWN",
    }
)


class ApprovalTimeout(RuntimeError):
    """The human did not finish signing inside the allotted window."""


class FolderMismatch(RuntimeError):
    """Foxit answered about a different folder than the one being watched."""


def folder_status(folder_response: dict) -> str:
    folder = folder_response.get("folder") or {}
    return str(folder.get("folderStatus") or "UNKNOWN").upper()


def wait_for_executed_folder(
    client,
    folder_id: str,
    *,
    timeout_seconds: int = 900,
    poll_interval_seconds: int = 10,
    on_status: Optional[Callable[[str, float], None]] = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict:
    """Poll ``client.get_folder(folder_id)`` until it reports EXECUTED.

    Returns the folder response for the caller to hand to
    ``audit.finalize_from_foxit_folder``. Raises ``ApprovalTimeout`` if the
    window closes first, and ``FolderMismatch`` if Foxit answers about a
    different folder — a completion from some other envelope must never
    finalize this approval.
    """
    if not folder_id:
        raise ValueError("A Foxit folder ID is required to wait for approval")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be positive")

    deadline = monotonic() + timeout_seconds
    while True:
        response = client.get_folder(folder_id)
        folder = response.get("folder") or {}
        returned = str(folder.get("folderId") or "")
        if returned and returned != str(folder_id):
            raise FolderMismatch(
                f"Foxit returned folder {returned!r} while waiting on {folder_id!r}"
            )

        status = folder_status(response)
        remaining = deadline - monotonic()
        if on_status is not None:
            on_status(status, max(remaining, 0.0))

        if status == APPROVED_STATUS:
            return response

        if remaining <= 0:
            raise ApprovalTimeout(
                f"Foxit folder {folder_id} did not reach {APPROVED_STATUS} within "
                f"{timeout_seconds} seconds (last status: {status})"
            )
        sleep(min(poll_interval_seconds, remaining))


def assert_plan_hash_unchanged(final_audit: dict, expected_plan_sha256: str) -> None:
    """The plan the human signed for must be the plan that was hashed before
    signing. Re-planning after approval would produce a different artifact than
    the one described in the signed document, so a mismatch fails closed."""
    actual = final_audit.get("terraform_plan_file_sha256")
    if not expected_plan_sha256:
        raise ValueError("No pre-sign Terraform plan hash to verify against")
    if actual != expected_plan_sha256:
        raise ValueError(
            "Terraform plan hash changed across the human approval boundary "
            f"(approved={expected_plan_sha256!r}, now={actual!r}). The signed "
            "document no longer describes this plan; refusing to finalize."
        )

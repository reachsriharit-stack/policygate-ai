# Security and trust boundary

PolicyGate AI is a hackathon MVP, not a production change-management system.

## Non-negotiable invariant

The AI agent may interpret a request, construct a proposed plan, evaluate
deterministic rules, generate evidence, and route a Foxit eSign approval request.
It may **not** approve, sign, impersonate the approver, or unlock infrastructure
execution by itself.

Optional Terraform execution exists only as a **post-human-approval executor**.
`terraform apply` is reachable only when all of these are true:

1. the final audit is `APPROVED`;
2. the same Foxit folder is `EXECUTED`;
3. the signer verified by Foxit matches the expected approver email;
4. the configuration plan hash still matches the evidence packet;
5. the exact saved `tfplan` bytes still match the SHA-256 embedded in the signed approval;
6. the caller deliberately opts in; and
7. `POLICYGATE_ALLOW_APPLY=true` is set.

No re-plan occurs between signature verification and apply.

## Database credentials and Terraform state

The generated RDS configuration uses `manage_master_user_password = true`, so
Amazon RDS generates and manages the master credential in AWS Secrets Manager.
PolicyGate does not create, print, or persist the database password.

Terraform state and saved plans can still contain sensitive infrastructure data.
Local Terraform directories, state files, and plan files are ignored by Git. A
production deployment should use an encrypted, access-controlled remote backend
with appropriate state locking and retention controls.

## Secrets

Never commit API keys. Use environment variables and keep `.env`, populated MCP
configuration, Terraform state, and plan files out of source control.

## Fail-closed behavior

If `ANTHROPIC_API_KEY` is present and the Claude parse fails, the application
raises an error by default. `POLICYGATE_ALLOW_AI_FALLBACK=true` is only for an
explicitly mocked development demo.

`POLICYGATE_SUBMISSION_MODE=true` rejects offline Claude, AI fallback, missing
Foxit PDF/MCP or eSign credentials, zero/multiple signing routes, or a disabled
Terraform plan. Use it while recording the final submission so the UI cannot
silently fall back to a mock path.

## Foxit routing and signer verification

`POLICYGATE_FOXIT_SEND_NOW=false` by default so credentials alone do not email a
real approver. Enable email routing deliberately, or use an embedded **human**
signing session. Short-lived embedded signing URLs are not written to CLI logs or
audit records; the Streamlit UI exposes them only as the human-facing link button.

The pre-sign audit records the expected signer email. Finalization correlates the
same Foxit folder, requires `folderStatus=EXECUTED`, verifies the expected email
against Foxit's recipient/signing-party data, and records `verified_signer_email`.
The post-sign provisioning gate requires expected and verified signer identities
to match.

Authenticate Foxit webhook requests at the HTTP boundary before calling
`finalize_from_foxit_webhook`. `verify_foxit_webhook_signature()` verifies Foxit's
HMAC-SHA-256/Base64 signature against the raw request body. Finalization then requires
`folder_executed`, `folderStatus=EXECUTED`, the original folder, and the expected
sign-capable recipient.

## Destructive cleanup

`terraform destroy` is separately gated. It requires:

- an explicit caller opt-in;
- `POLICYGATE_ALLOW_DESTROY=true`; and
- `--confirm-request-id` exactly matching the evidence request ID.

## Demo limitations

- Cost is a fixed demo catalog, not current AWS pricing.
- Terraform `plan` is real only when explicitly enabled with valid AWS credentials.
- Terraform `apply` is real and billable but intentionally not required for the submission demo.
- The offline parser is a test/development fallback, not a production NLP parser.
- Foxit MCP runs in the configured external MCP host; the Streamlit UI shows whether credentials are configured but does not falsely claim an MCP operation ran.

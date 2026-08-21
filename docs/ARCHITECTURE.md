# Architecture

```text
Plain-English request
        |
        v
Claude structured extraction        AI interprets intent only
        |
        v
Typed ChangeRequest
        |
        v
Deterministic planner + rule engine
        |
   FAIL +--------------------+ PASS
    |                           |
  BLOCK                   Evidence packet
                                |
                                v
                       Generate Terraform HCL
                                |
                                v
                  terraform init / validate / plan
                                |
                                v
                 saved tfplan + SHA-256 + show output
                                |
                                v
                     Approval PDF contains the
                     exact plan summary + hash
                                |
                                v
               Foxit reversible PDF/MCP demo step
                    (external MCP-compatible host)
                                |
                                v
                      Foxit eSign human handoff
                                |
                                v
                 🛑 AWAITING_HUMAN_APPROVAL
                                |
                           HUMAN SIGNS
                                |
                                v
              same folder EXECUTED + signer verified
                                |
                                v
              signed-PDF hash + final audit APPROVED
                                |
                                v
                 OPTIONAL post-sign executor
                                |
                  re-hash EXISTING saved tfplan
                                |
                      exact signed hash matches?
                         /              \
                       no                yes
                       |                  |
                     DENY          terraform apply
```

## Separation of duties

Claude is useful for interpreting ambiguous intent. It does not decide compliance.
The deterministic rule engine does not authorize. Foxit captures the human
accountability event. The post-sign executor accepts only a final audit that proves
that event and only for the exact Terraform plan that was included in the signed
document.

There is intentionally no agent `sign()` capability.

## Requested versus policy-injected controls

The parser preserves omitted values as `None`. The planner may inject mandatory
organization controls, while explicit unsafe requests such as "no encryption"
remain explicit and are rejected. This keeps the audit trail honest about what the
requester asked for versus what policy required.

## Exact-plan approval

When `POLICYGATE_INCLUDE_TERRAFORM_PLAN=true`, PolicyGate generates Terraform,
runs `init`, `validate`, and `plan -out=tfplan`, hashes the literal plan-file bytes,
and embeds both the `terraform show` output and SHA-256 in the approval PDF **before
Foxit routing**.

Two independent checks protect execution:

1. `authorize_provisioning()` re-derives the configuration-level plan hash from the evidence packet and requires a final Foxit audit with the expected/verified signer match.
2. `verify_plan_file_integrity()` re-hashes the saved `tfplan` immediately before apply and requires the bytes to match the hash covered by the human approval.

`apply_approved()` never runs `terraform plan`; a different plan requires a new
approval.

## Credential handling

The generated RDS resource uses AWS/RDS-managed master credentials via Secrets
Manager (`manage_master_user_password = true`). PolicyGate does not generate the
master password. Terraform state is still treated as sensitive and excluded from
source control.

## Foxit signer correlation

The pre-sign audit records `expected_signer_email`. Finalization requires the same
Foxit folder and `EXECUTED` state; webhook finalization accepts only the final
`folder_executed` event. It verifies the expected sign-capable recipient returned by
Foxit. The final audit records `verified_signer_email`; apply requires it to match
the expected signer. Webhook transport can be authenticated with the included
raw-body HMAC verification helper.

## Foxit MCP boundary

Foxit's official PDF API MCP server is designed to run in an MCP-compatible host.
PolicyGate exposes its configured/not-configured status in the judge UI and the
submission workflow requires the actual MCP tool invocation to be captured in the
video. eSign remains a direct human-authorization boundary rather than an agent
signing tool.

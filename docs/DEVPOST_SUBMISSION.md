# Devpost submission copy

## Project name

PolicyGate AI

## One-line pitch

PolicyGate AI turns a plain-English production database request into a
deterministically validated Terraform plan, binds the exact plan hash into a Foxit
approval document, and makes that plan executable only after the designated human
signs it.

## Inspiration

Regulated production changes need an evidence trail: what was requested, which
controls were checked, exactly what would change, and who authorized it. Much of
that workflow is still manual. PolicyGate automates the reversible work while
preserving a hard human accountability boundary.

## What it does

1. Accepts a plain-English AWS PostgreSQL provisioning request.
2. Uses Claude only to extract structured intent.
3. Applies deterministic organization policy and guardrails.
4. Blocks unsafe requests before an approval document can be routed.
5. Generates Terraform and a real saved `terraform plan` when live planning is enabled.
6. Hashes the exact `tfplan` bytes and embeds the hash plus human-readable plan in the approval PDF.
7. Demonstrates reversible PDF work through Foxit's official PDF API/MCP path.
8. Routes the document to a named human through Foxit eSign and stops at `AWAITING_HUMAN_APPROVAL`.
9. After the human signs, verifies the same Foxit folder reached `EXECUTED` (or receives the final `folder_executed` webhook) and that the verified signer matches the expected approver.
10. Hashes the signed PDF into the final audit record.
11. Optionally, a separately gated executor can apply only the exact already-approved `tfplan`; it never re-plans after signature.

## How we built it

- Python 3.11+
- Anthropic Claude structured outputs for intent extraction
- Deterministic Python planner and policy engine
- Terraform CLI + AWS provider for plan generation and plan-file integrity
- AWS RDS-managed master credentials in Secrets Manager
- Foxit PDF API/MCP for reversible sponsor-native PDF operations during the demo
- Foxit eSign REST API for the human authorization handoff and signed-document retrieval
- SHA-256 evidence locking for configuration, exact Terraform plan, unsigned packet, and signed document
- Streamlit judge UI with explicit LIVE/MOCK indicators
- Unit tests + GitHub Actions CI

## Human/AI boundary

The most important design decision is what the AI cannot do. Claude does not make
the policy decision. A passing policy result does not authorize production. The
agent has no signing capability. Terraform apply is not unlocked until Foxit has
recorded a human-completed approval, signer identity is verified, and the saved
plan still hashes to the exact value that appeared in the signed document.

## Foxit's role

Foxit is the document and authorization boundary. The approval artifact makes the
requested change, deterministic checks, Terraform diff, and exact plan hash human
reviewable. Foxit eSign captures the accountable human action. PolicyGate then
correlates that completion to the original folder and signer before the audit can
become `APPROVED`.

## Accomplishments

- Explicit separation of AI interpretation, deterministic compliance, human authorization, and post-approval execution
- Requested-vs-policy-injected control provenance
- Exact Terraform `tfplan` SHA-256 embedded before signature
- No re-plan between signature and apply
- Expected-versus-verified signer identity check
- RDS-managed Secrets Manager master credentials instead of a Terraform-generated DB password
- Fail-closed submission mode that refuses AI fallback, missing sponsor credentials, ambiguous signing routes, and a disabled Terraform plan during recording
- Separately gated apply and destroy operations

## What we learned

Human-in-the-loop is strongest when it is an architectural boundary rather than a
prompt instruction. Approval should cover the literal execution artifact, not just
a high-level description of a change.

## What's next

- Live AWS pricing and cost-policy integration
- Multi-cloud policy packs
- Policy-as-code versioning and exception workflows
- Authenticated production webhook receiver and durable evidence storage
- Remote encrypted Terraform state with enterprise locking/retention controls

> Before submission, edit this copy to describe only the live paths actually shown
> in the video. Do not claim a Foxit MCP, eSign, Claude, or AWS plan run that was
> not genuinely exercised.

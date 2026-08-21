# 3-minute demo script

## 0:00–0:15 — Trust model

"Production database changes need evidence of what was requested, what policy
checked, exactly what will execute, and who authorized it. PolicyGate lets AI do
the reversible work but makes human authorization a code boundary."

Point to the LIVE/MOCK badges. For the final recording, run with
`POLICYGATE_SUBMISSION_MODE=true` so AI fallback, missing Foxit credentials,
ambiguous signing routes, and a disabled Terraform plan are refused.

## 0:15–0:40 — Plain-English request

Paste the compliant AWS/PostgreSQL request. Show Claude's structured intent and
point out that omitted controls were not invented by the model.

## 0:40–1:05 — Deterministic controls

Show policy-injected encryption/private-network controls and the PASS checks.
Say: "Claude interpreted the request; deterministic code made the compliance
decision."

Briefly show the reject case to prove unsafe requests block before Foxit.

## 1:05–1:35 — Exact Terraform plan

Show the real Terraform plan summary and the `tfplan` SHA-256 in Streamlit. Open
the PDF and show that the same summary/hash appear **before the signature field**.

Say: "The human is approving the literal Terraform execution plan. If anyone
re-plans or changes the file after signature, apply fails."

## 1:35–1:55 — Foxit MCP proof

In the configured MCP host, show one reversible Foxit PDF operation on the approval
artifact (for example upload/compress/flatten according to the tool you actually
use). Capture the tool name and result on screen. Do not call configuration alone
an MCP execution.

## 1:55–2:25 — Foxit eSign + hard stop

Create the real Foxit eSign handoff. Show:

> 🛑 AGENT EXECUTION STOPPED — AWAITING HUMAN APPROVAL

Have the named human sign in their Foxit session. The agent does not sign.

## 2:25–2:45 — Verify the approval

Run `policygate-complete`. Show:

- same Foxit folder ID
- `EXECUTED`
- `expected_signer_email`
- `verified_signer_email`
- signed PDF SHA-256
- final state `APPROVED`

## 2:45–3:00 — Execution boundary

Show the apply command but do **not** spend money in the submission video unless
you intentionally want to. Explain that apply re-hashes the existing saved plan,
never re-plans, and requires an explicit environment gate.

Close with:

"AI can propose. Policy can validate. Only a human can authorize — and only the
exact plan they approved can execute."

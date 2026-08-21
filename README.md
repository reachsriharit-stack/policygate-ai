# PolicyGate AI

**Human-governed change control for AI infrastructure agents.**

> **AI can propose. Policy can validate. Only a human can authorize.**

Built for the **DevNetwork [API + Cloud + AI] Hackathon 2026**, targeting the
**Foxit Software — “Your Agent Shouldn't Sign That”** sponsor challenge.

## Why it exists

A production database change in a regulated environment needs a paper trail:
what was requested, what policy checked, what plan was proposed, and who signed
off. PolicyGate automates the reversible work but makes human authorization a
hard code boundary rather than a prompt instruction.

```text
Plain English
    -> Claude intent extraction
    -> deterministic plan + guardrails
    -> real Terraform saved plan (submission mode)
    -> exact tfplan SHA-256 bound into approval PDF
    -> Foxit PDF/MCP reversible step (external MCP host)
    -> Foxit eSign human handoff
    -> 🛑 AWAITING_HUMAN_APPROVAL
    -> human signature
    -> same folder EXECUTED + signer verification
    -> signed-PDF hash + final audit
    -> optional apply of that exact approved tfplan
```

## The trust model

| Layer | Responsibility | Can approve? |
|---|---|---:|
| Claude | Interpret request into typed fields | No |
| PolicyGate planner/rules | Build plan + deterministic PASS/FAIL evidence | No |
| Terraform preview | Materialize the exact execution plan | No |
| Foxit PDF/MCP | Reversible document operations | No |
| Foxit eSign + named human | Review and authorize the change | **Human only** |
| Post-sign executor | Apply only the already-approved saved plan | No new approval |

There is intentionally **no agent-side `sign()` operation**.

## MVP scope

- AWS PostgreSQL / RDS only
- approved-region allow-list
- encryption at rest
- Multi-AZ / high availability
- minimum 30-day production backups
- no public production access
- user budget + organization budget ceiling
- named human approver + routable approver email
- fixed, clearly labeled demo cost catalog (not live AWS pricing)

A key auditability feature: omitted controls remain `None` after AI parsing. The
planner may inject mandatory policy defaults; an explicitly unsafe request remains
explicit and is blocked.

## Quick start

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate               # Windows: .venv\Scripts\activate
# Pinned direct dependencies for the submission/demo environment:
pip install -r requirements.lock
# Contributors may instead use the compatible ranges in requirements.txt.
cp .env.example .env
python -m unittest discover -s tests -v
```

### CLI demo — passing request

```bash
python -m policygate.app examples/approve_request.txt \
  --approver-name "Jane Smith" \
  --approver-email "jane@example.com"
```

### CLI demo — blocked request

```bash
python -m policygate.app examples/reject_request.txt \
  --approver-name "Jane Smith" \
  --approver-email "jane@example.com"
```

### Judge-friendly UI

```bash
streamlit run policygate/streamlit_app.py
```


## Docker demo

```bash
docker build -t policygate-ai .
docker run --rm -p 8501:8501 --env-file .env policygate-ai
```

Then open `http://localhost:8501`. The image includes the Terraform CLI so the
real-plan path can run when AWS credentials are supplied.

## Live Claude mode

Without `ANTHROPIC_API_KEY`, PolicyGate uses a conservative offline parser so the
repo is reproducible. With a key, it uses Claude structured outputs:

```bash
export ANTHROPIC_API_KEY=...
export CLAUDE_MODEL=claude-sonnet-5
```

If the live model call fails, PolicyGate **fails closed** by default rather than
silently switching to heuristics. For an explicitly mocked demo only, set
`POLICYGATE_ALLOW_AI_FALLBACK=true`.

For the recorded submission, set `POLICYGATE_SUBMISSION_MODE=true`; it refuses
AI fallback, missing Foxit PDF/MCP or eSign credentials, zero/multiple human
signing routes, and a disabled Terraform plan.

## Live Foxit eSign mode

Foxit eSign uses a separate credential set from PDF Services:

```bash
export FOXIT_ESIGN_BASE_URL=https://na1.foxitesign.foxit.com
export FOXIT_ESIGN_CLIENT_ID=...
export FOXIT_ESIGN_CLIENT_SECRET=...
```

The client authenticates, uploads the approval PDF to
`/api/folders/createfolder`, sets `processTextTags=true`, adds the named human as
the signing party, and stops. The approval PDF contains Foxit signature/date Text
Tags for party 1.

Routing is intentionally explicit. To email the live signing invitation:

```bash
export POLICYGATE_FOXIT_SEND_NOW=true
```

Or request an embedded **human** signing session during the demo:

```bash
export POLICYGATE_EMBEDDED_SIGNING=true
```

Both modes preserve the same trust boundary: the human signs; the agent cannot.
After the human finishes, finalize the evidence trail with:

```bash
python -m policygate.complete_approval artifacts/PG-...-audit-pre-sign.json
```

That command verifies the same Foxit folder is `EXECUTED`, verifies the expected
sign-capable recipient, downloads the signed PDF, hashes it, and writes the final
audit record. A webhook receiver can use `verify_foxit_webhook_signature()` to
verify Foxit's HMAC signature over the raw request body before finalization.

## Foxit MCP server

Foxit's official open-source PDF API MCP server is the sponsor path for reversible
PDF work. See [`docs/FOXIT.md`](docs/FOXIT.md). PolicyGate keeps eSign outside the
agent's tool catalog by design. `POLICYGATE_SUBMISSION_MODE=true` requires the MCP
credentials to be configured, but the submission video must still show a genuine
MCP tool invocation rather than treating configuration as proof of execution.

## Generated artifacts

Passing CLI runs write to `artifacts/`:

- `*-evidence.json` — complete request/plan/check provenance
- `*-approval.pdf` — human-readable approval packet with eSign Text Tags
- `*-audit-pre-sign.json` — plan/PDF hashes + Foxit folder ID + workflow state
- `*-signed.pdf` + `*-audit-final.json` — created only after verified live Foxit execution

Blocked requests generate no signature artifact.

## Tests

```bash
python -m unittest discover -s tests -v
python -m compileall policygate
```

The current suite contains **83 tests** covering policy injection, explicit unsafe
requests, budgets, regions, human identity/routing requirements, the hard-stop state,
valid PDF generation, Foxit OAuth/create-folder/status/download behavior, webhook
signature verification, signer/folder correlation, Terraform generation, exact-plan
binding, apply regression protection, destroy gating, and submission-mode fail-closed
checks.

## Submission materials

- [`docs/DEVPOST_SUBMISSION.md`](docs/DEVPOST_SUBMISSION.md) — ready-to-paste copy
- [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) — 3-minute walkthrough
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — trust boundary + data flow
- [`docs/FOXIT.md`](docs/FOXIT.md) — sponsor integration notes
- [`docs/MCP_DEMO.md`](docs/MCP_DEMO.md) — Foxit MCP setup + sponsor demo path
- [`docs/SUBMISSION_CHECKLIST.md`](docs/SUBMISSION_CHECKLIST.md) — final pre-flight checklist
- [`docs/SOURCES.md`](docs/SOURCES.md) — public challenge/API sources used for alignment
- [`SECURITY.md`](SECURITY.md) — limitations and fail-closed behavior

## Optional: real provisioning after approval

`policygate/provisioning/` generates real Terraform from the exact approved plan, and can bind it directly into the document a human signs.

**Bind the plan into the approval PDF before signature** (the strongest version — this is what a judge should see):

```bash
POLICYGATE_INCLUDE_TERRAFORM_PLAN=true python -m policygate.app examples/approve_request.txt \
  --approver-name "Jane Smith" --approver-email jane@example.com
```

With this flag, `run_workflow()` generates Terraform, runs `terraform init`, `validate`, and `plan -out=tfplan` for real against your configured AWS provider *before* the PDF is built — `plan` is the step that actually proves live AWS accessibility (`init`/`validate` mostly check syntax and provider setup). The plan file's SHA-256 and a human-readable `terraform show` summary are embedded directly in the signed document — see the "Terraform plan" section it adds — and carried through the entire audit chain (pre-sign → final, after signature) as `terraform_plan_file_sha256`. No mock mode: faking this would defeat the point, so if terraform/AWS aren't ready, leave the flag off (the default) and everything else behaves exactly as before.

**Two independent integrity checks gate `apply`, and `apply` never re-plans.** `approval_gate.authorize_provisioning()` verifies the signed audit record's config hash matches the evidence packet, and `approval_gate.verify_plan_file_integrity()` re-hashes the plan file *already sitting on disk* and compares it to the hash on the signed audit record — catching replacement, mutation, or re-planning of the saved plan between approval and apply. Critically, `--apply` does not call `terraform plan` at all; it only ever applies the exact file that was there when the human signed. If the signed audit has no bound plan hash, there is no fallback to a freshly-generated one — apply is flatly denied:

```bash
POLICYGATE_ALLOW_APPLY=true python -m policygate.provision \
  artifacts/PG-...-evidence.json artifacts/PG-...-audit-final.json --apply
```

**Cost warning:** the production demo plan is a Multi-AZ `db.r6g.large` — not free-tier eligible. If you run `--apply` for a live demo, tear it down immediately after:

```bash
POLICYGATE_ALLOW_DESTROY=true python -m policygate.provision \
  artifacts/PG-...-evidence.json --destroy \
  --confirm-request-id PG-... --workdir terraform/PG-...
```

**For the submission itself: generate, validate, and plan for real, with the plan bound into the signed document — do not apply.** The claim being made is precise: *PolicyGate generates real Terraform, authenticates to the configured AWS environment during planning, and binds the exact plan file's hash into the document a human signs before any execution is possible. The demo intentionally does not execute the billable apply step.*

## Important limitations

This is a hackathon MVP. Terraform generation, `plan`, plan-file integrity binding
into the signed document, signer verification, and the layered apply/destroy gates are
implemented and tested. `terraform apply` is real but opt-in and is not required for
the submission video. Cost estimates elsewhere in the app are a replayable demo
catalog, not a live AWS quote. The repository includes Foxit webhook HMAC verification,
but a deployed HTTP receiver must invoke it on the raw request body before parsing or
finalizing any webhook.

## License

MIT

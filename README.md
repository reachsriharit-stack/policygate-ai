# PolicyGate AI

**Human-governed change control for AI infrastructure agents.**

> **AI can propose. Policy can validate. Only a human can authorize.**

Built for the **DevNetwork [API + Cloud + AI] Hackathon 2026**, targeting the
**Foxit Software — “Your Agent Shouldn't Sign That”** sponsor challenge.

## Why it exists

A production infrastructure change in a regulated environment needs a paper trail:
what was requested, what policy checked, what execution plan was proposed, and who
authorized it.

PolicyGate automates the reversible preparation work while making human authorization
a hard code boundary rather than a prompt instruction.

This hackathon demo uses AWS PostgreSQL provisioning as one concrete infrastructure
use case.

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

## Demo

🎥 **3-minute demo:** [Watch the PolicyGate demo](YOUR_YOUTUBE_LINK)

🖥️ **Interactive evidence UI:** [policygate.streamlit.app](https://policygate.streamlit.app)

🏗️ **Source:** This repository

### What to watch for

- Real Claude intent extraction
- Deterministic policy validation
- Real AWS-backed Terraform plan
- Exact `tfplan` SHA-256 bound into the approval document
- Real Foxit MCP document processing
- Real Foxit eSign human handoff
- `AWAITING_HUMAN_APPROVAL` hard stop
- Human signature verification
- Final `APPROVED` audit
- `terraform apply` intentionally not run

## Live integration workflows

Every claim above is exercised by a manual GitHub Actions workflow rather than
asserted in prose. Each is `workflow_dispatch` only, because each spends real
money, touches a real cloud account, or emails a real person.

| Workflow | What it proves |
|---|---|
| `final-policygate-demo.yml` | The whole chain in one run: live Claude → guardrails → AWS Terraform plan → approval PDF → Foxit MCP → eSign send → waits for the human → verifies the signature → `APPROVED` |
| `live-claude-test.yml` | One request through the real Claude API, with the offline parser tripwired so a fallback cannot pass as a live call |
| `live-terraform-plan.yml` | `init`/`validate`/`plan`/`show` against real AWS via GitHub OIDC, hashing the saved plan file. `apply` and `destroy` raise before a command line can be built |
| `live-foxit-pdf.yml` | A real upload to Foxit PDF Services |
| `live-foxit-mcp.yml` | The official Foxit MCP server, pinned to a commit, driven over stdio by a real MCP client |
| `live-foxit-esign-draft.yml` | A real eSign folder created with `sendNow: false` — nothing is emailed |
| `live-foxit-esign-send.yml` | A real signing invitation to a named human, stopping at `AWAITING_HUMAN_APPROVAL` |
| `live-foxit-esign-verify.yml` | Standalone verification of an already-signed envelope; also the recovery path if a final-demo run is interrupted |
| `show-oidc-ids.yml` | Prints the repository identifiers needed to write the AWS OIDC trust policy |

They share a discipline: credentials are never printed (every logged string is
scrubbed), generated PDFs and plans are deleted rather than uploaded, and the
run asserts a clean working tree before it finishes. `terraform apply` and
`terraform destroy` are tripwired in every workflow that touches Terraform.

Required configuration lives in repository **secrets** (`ANTHROPIC_API_KEY`,
`FOXIT_CLOUD_API_CLIENT_ID`, `FOXIT_CLOUD_API_CLIENT_SECRET`) and **variables**
(`AWS_ROLE_ARN`, `AWS_REGION`, `FOXIT_CLOUD_API_HOST`). AWS access is by OIDC —
no access-key secrets exist in this repository.

## Demo implementation scope

The governance architecture is infrastructure-oriented; the hackathon implementation
uses AWS RDS PostgreSQL as the concrete Terraform-managed resource.

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

The page **reports evidence; it does not produce it**. It never calls Claude,
AWS, Terraform, Foxit MCP or Foxit eSign. Instead it reads `demo-evidence.json`
— the sanitized record `final-policygate-demo.yml` writes — and walks a reader
through the nine stages of one real run: request, Claude intent, deterministic
controls, generated Terraform, the plan and its hash, approval evidence, the
human boundary, the plan-hash binding, and the final audit.

With no verified evidence present it keeps honest `OFFLINE` / `MOCK` /
`NOT CONFIGURED` labels. `LIVE` is never a constant in the UI: it is returned
only by `demo_evidence.badges()`, which yields nothing unless the evidence shows
a live Claude call with fallback disabled, passing guardrails, a real plan, a
verified MCP operation, a Foxit `EXECUTED` folder, a matching signer, an
unchanged plan hash, and no apply or destroy.

To publish a verified run: dispatch the final demo, download its
`policygate-demo-evidence` artifact, commit it as `demo-evidence.json` (or point
`POLICYGATE_DEMO_EVIDENCE` at it), and redeploy. **No sample evidence file ships
in this repository** — a committed example carrying `LIVE` values would be
indistinguishable on screen from a real run.

The interactive button is labelled **Run local demonstration** and marked as not
the verified integration run; it is hidden entirely when
`POLICYGATE_SUBMISSION_MODE=true`.


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

`foxit_client.py` reaches eSign over one of two transports, selected with
`FOXIT_ESIGN_TRANSPORT`.

The eSign portal with its own OAuth credentials (the default):

```bash
export FOXIT_ESIGN_TRANSPORT=esign_oauth     # default
export FOXIT_ESIGN_BASE_URL=https://na1.foxitesign.foxit.com
export FOXIT_ESIGN_CLIENT_ID=...
export FOXIT_ESIGN_CLIENT_SECRET=...
```

Or the Foxit Developer Platform gateway, which authenticates every request with
the same `FOXIT_CLOUD_API_*` credentials the PDF Services API uses — this is what
the live workflows run:

```bash
export FOXIT_ESIGN_TRANSPORT=developer_platform
export FOXIT_ESIGN_BASE_URL=https://na1.fusion.foxit.com
export FOXIT_CLOUD_API_CLIENT_ID=...
export FOXIT_CLOUD_API_CLIENT_SECRET=...
```

Only the host, route prefix and authentication differ. The request bodies and the
human-approval boundary are identical, and neither transport has a method that
signs.

The client authenticates, uploads the approval PDF to the createfolder endpoint,
sets `processTextTags=true`, adds the named human as the signing party, and
stops. The approval PDF contains Foxit signature/date Text
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
agent's tool catalog by design.

Configuration is not proof of execution, so the MCP path is exercised rather than
described: `live-foxit-mcp.yml` and `final-policygate-demo.yml` clone the official
server at a pinned commit, install the current Python implementation, drive it over
stdio with a real MCP client, discover its tools, and invoke `pdf_compress` on the
approval PDF. The tools report failure inside their JSON payload rather than as a
protocol error, so each payload's `success` flag is checked — a Foxit-side failure
fails the job instead of passing quietly.

## Generated artifacts

Passing CLI runs write to `artifacts/`:

- `*-evidence.json` — complete request/plan/check provenance
- `*-approval.pdf` — human-readable approval packet with eSign Text Tags
- `*-audit-pre-sign.json` — plan/PDF hashes + Foxit folder ID + workflow state
- `*-signed.pdf` + `*-audit-final.json` — created only after verified live Foxit execution

Blocked requests generate no signature artifact.

The live workflows upload non-secret metadata only:

- `policygate-final-pre-sign-audit` — request ID, folder ID, expected signer,
  approval PDF hash, approved plan hash
- `policygate-final-audit` — the same record after a verified signature
- `policygate-demo-evidence` — the sanitized record the Streamlit UI reads

Neither the approval PDF, the signed PDF, the saved `tfplan`, nor any credential
is ever uploaded.

## Tests

```bash
python -m unittest discover -s tests -v
python -m compileall policygate
```

The current suite contains **150 tests** covering policy injection, explicit unsafe
requests, budgets, regions, human identity/routing requirements, the hard-stop state,
valid PDF generation, Foxit OAuth/create-folder/status/download behavior on both
transports, webhook signature verification, signer/folder correlation, Terraform
generation, exact-plan binding, apply regression protection, destroy gating, and
submission-mode fail-closed checks.

It also covers the parts that only exist because of the live workflows: the
approval wait (only `EXECUTED` approves — `COMPLETED` does not), timeout failing
closed with the pre-sign record untouched, a changed plan hash refusing to
finalize, the demo-evidence allowlist and its rejection of emails, URLs, AWS
account IDs, ARNs, access keys, private IPs and Terraform state, and a guard that
no workflow interpolates dispatch input into a shell block.

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

Two things about the demo surfaces are worth stating plainly. The live workflows
are manual on purpose: each one spends money, assumes a real AWS role, or emails a
real person, so none of them run on push. And `demo-evidence.json` is a **snapshot
of one completed run**, not a live reading — the Streamlit page keeps showing that
run's result until the file is replaced, which is why its panel is captioned as
evidence from a completed run rather than as the app's own status.

## License

MIT

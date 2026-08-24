# 3-minute demo script

The strongest evidence this project has is a single GitHub Actions run that
touches four real services and then *stops*. The recording should show that run's
evidence, not a local simulation.

## Before you record

Do this the day before, not on camera:

1. Dispatch **PolicyGate AI — Final Demo** with your own name and email.
2. Sign the Foxit invitation inside the 15-minute window. The job continues by
   itself and finishes at `APPROVED`.
3. Download the run's **`policygate-demo-evidence`** artifact, commit it as
   `demo-evidence.json` at the repository root, and redeploy Streamlit. The nine
   numbered sections only appear once that file is present.
4. Keep the finished Actions run open in a tab — several shots come from its log.
5. Keep one approval PDF handy (any run's `*-approval.pdf`, or generate one with
   the local demonstration button) for the shot that shows the hash above the
   signature line.

**Rehearse the whole run once first.** The wait-and-verify phase is the one part
that depends on you signing promptly; a rehearsal tells you how long Foxit takes
to report `EXECUTED` on your account.

## Assets to capture

| # | Asset | Where it comes from |
|---|---|---|
| A | Streamlit page, top: title, tagline, six badges | deployed app with evidence published |
| B | Sections 1–2: request text and parsed intent | same page |
| C | Section 3: requested vs enforced controls, eight rule results | same page |
| D | Sections 4–5: generated Terraform, plan counts, tfplan SHA-256 | same page |
| E | Approval PDF, scrolled to the Terraform plan section above the signature line | any `*-approval.pdf` |
| F | Actions log: MCP tool discovery and `pdf_compress` | final-demo run |
| G | Actions log: `POLICYGATE HAS STOPPED` banner and the waiting countdown | final-demo run |
| H | The Foxit signing email / signing page | your inbox |
| I | Sections 7–9 and the job's step summary (PHASE 1 / PHASE 2) | page + run summary |

## The script

### 0:00–0:20 — The claim (asset A)

> "Production infrastructure changes need evidence: what was asked for, what
> policy decided, exactly what would execute, and who authorized it. PolicyGate
> lets an AI agent do all the reversible work — and makes human authorization a
> code boundary, not a prompt instruction."

Point at the six badges. Say they come from a completed run, not from the page:
this app never calls Claude, AWS, Terraform or Foxit.

### 0:20–0:40 — Request and intent (asset B)

> "One plain-English sentence. Claude extracts structured intent — environment,
> region, availability, retention, budget."

Note what Claude *didn't* do: it never invented a control that wasn't asked for.
Omitted controls stay null.

### 0:40–1:00 — The split that matters (asset C)

> "Claude extracts intent. Deterministic PolicyGate code decides compliance."

Point at the two columns: what the user requested, and what policy enforced on top
— encryption, private networking, managed credentials, human approval. Then the
eight rule results.

### 1:00–1:25 — Real plan, exact hash (asset D)

> "PolicyGate generated Terraform from the validated intent and ran a real plan
> against a real AWS account through OIDC. One resource to add. And this hash is
> the SHA-256 of the exact binary plan file."

Stress: not a description of the plan — the plan.

### 1:25–1:45 — The binding (asset E)

Open the approval PDF at the Terraform section.

> "That same hash is inside the document the human signs, above the signature
> line. The approval is bound to one specific plan file."

### 1:45–2:05 — Foxit MCP (asset F)

> "The approval document goes through Foxit's official MCP server — cloned at a
> pinned commit, driven over stdio by a real MCP client. Thirty-two tools
> discovered, `pdf_compress` invoked, a new document returned."

Say plainly: configuration is not proof of execution, so this is the tool call.

### 2:05–2:35 — The stop (assets G, H, and section 7)

Show the banner in the log:

```
POLICYGATE HAS STOPPED
State: AWAITING_HUMAN_APPROVAL
Agent may sign: NO
```

> "The agent has done everything it is authorized to do. There is no sign() in
> this codebase. It polls one folder, read-only, and waits."

Cut to the Foxit email and the signature. Then section 7's before/after panels.

The line worth landing here:

> "Before the signature, PolicyGate asked its own authorization gate whether it
> could provision. The gate said no."

### 2:35–2:55 — Verified, and bound (asset I)

> "Foxit reports EXECUTED. The signer matches the person it was routed to. The
> plan hash after signing is the same hash from before — Terraform is never
> re-run after approval. Final audit: APPROVED. And apply and destroy never ran."

### 2:55–3:00 — Close

> "AI can propose. Policy can validate. Only a human can authorize — and only the
> exact plan they approved can execute."

## If you must record before publishing evidence

The Streamlit page will honestly show `OFFLINE / MOCK / NOT CONFIGURED`, and the
nine sections stay hidden. In that case make the finished Actions run the primary
surface — its step summary already renders PHASE 1 and PHASE 2 as a clean panel —
and use the local demonstration button only for the parser and policy shots,
saying out loud that it is the local path.

Do not stage the evidence file by hand. A fabricated `demo-evidence.json` would
look identical on screen to a real run, which is exactly the claim this project
exists to make impossible.

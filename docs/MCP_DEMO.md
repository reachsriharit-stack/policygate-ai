# Foxit MCP sponsor demo path

The repository is runnable without sponsor credentials, but the **submission video
should exercise Foxit's official PDF API MCP server if credentials are available**.
That is the sponsor-native path for reversible PDF work. eSign remains a separate
REST/human boundary.

## Register the official server

1. Clone `foxitsoftware/foxit-pdf-api-mcp-server` outside this repository.
2. Install `uv` and follow the current Python-server README.
3. Copy `.vscode/mcp.json.example` to `.vscode/mcp.json` (ignored by Git) and replace
   the local server path/credential placeholders.
4. Start the server in your MCP-compatible host and verify the Foxit PDF tools are
   discovered.

Never paste Foxit client secrets into chat/prompt context or commit the populated
`.vscode/mcp.json`.

## Recommended challenge demo sequence

Use the MCP host for a visible, reversible document operation before eSign. For
example:

1. Give the agent the validated PolicyGate evidence content.
2. Ask the Foxit MCP tools to create or transform the approval document.
3. Download/open the resulting PDF and show the request ID + plan hash.
4. Route that approval PDF through PolicyGate's Foxit eSign handoff.
5. Show `AWAITING_HUMAN_APPROVAL` and stop agent execution.
6. Let the human sign.
7. Run `policygate-complete` to verify `EXECUTED`, download the signed PDF, and hash
   it into the final audit record.

The local ReportLab renderer in `policygate/pdf_render.py` is a reproducibility
fallback, **not a claim that the Foxit MCP path was executed**.

## What to capture on video

Capture the MCP tool invocation/result, the exact Terraform plan/hash, the Foxit
eSign signing surface, the hard PolicyGate stop banner, and the final audit record.
That makes the sponsor value and exact-plan human-approval boundary visible in one
short sequence.

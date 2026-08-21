# Foxit integration

## eSign boundary used by this repo

The live client follows Foxit eSign's documented flow:

1. OAuth client-credentials token at `/api/oauth2/access_token`.
2. Create a document folder at `/api/folders/createfolder`.
3. Upload the approval PDF as Base64.
4. Set `processTextTags=true` so the approval signature/date tags become fields.
5. Add the named approver as the `FILL_FIELDS_AND_SIGN` party.
6. Either send the invitation (`POLICYGATE_FOXIT_SEND_NOW=true`) **or** request an
   embedded human signing session (`POLICYGATE_EMBEDDED_SIGNING=true`).
7. Stop at `AWAITING_HUMAN_APPROVAL`. There is no `sign()` method in PolicyGate.
8. A person reviews and signs in Foxit.
9. Wait for the final `folder_executed` event (not merely `folder_completed`) or
   poll until `EXECUTED`; correlate the same folder and expected sign-capable
   recipient, download the signed PDF, and hash it into the final audit.

`POLICYGATE_FOXIT_SEND_NOW` defaults to `false` so a developer who adds real
credentials does not accidentally email a signer. Turn on a deliberate handoff
mode before the live demo.

For a conference demo, embedded signing changes only the UI surface: the human still
performs the signature. Do not pass a signer session URL to an autonomous agent.

## Finalize after the human signs

With live Foxit credentials:

```bash
python -m policygate.complete_approval \
  artifacts/PG-...-audit-pre-sign.json
```

The command verifies that the **same** Foxit folder is `EXECUTED`, downloads document
1, writes `*-signed.pdf`, and writes `*-audit-final.json` containing the signed-PDF
SHA-256. It never signs or authorizes anything itself.

## Foxit PDF API MCP server

Foxit maintains an open-source MCP server for PDF Services. Configure it in your
MCP-compatible host with `FOXIT_CLOUD_API_HOST`, client ID, and client secret. Use
it for reversible document operations (conversion, creation, merge, OCR, etc.)
when presenting the sponsor integration. Signing remains outside that tool catalog
and goes through the eSign API/human handoff.

Do not claim the MCP path was executed in a demo unless it actually was. The local
ReportLab renderer exists so the repository is runnable without sponsor keys.

## Webhook verification

Foxit can sign webhook requests with an HMAC-SHA-256/Base64 signature computed
over the **raw HTTP request body**. Configure `FOXIT_ESIGN_WEBHOOK_SECRET` in the
deployed receiver and call:

```python
from policygate.audit import verify_foxit_webhook_signature

if not verify_foxit_webhook_signature(raw_body, signature, webhook_secret):
    raise PermissionError("Invalid Foxit webhook signature")
```

Do this before JSON parsing/re-serialization. `finalize_from_foxit_webhook()` then
requires `event_name=folder_executed`, `folderStatus=EXECUTED`, the original folder
ID, and the expected signer identity.

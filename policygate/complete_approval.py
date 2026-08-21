"""Finalize a PolicyGate audit after a human has signed in Foxit eSign.

This command does not sign anything. It only verifies that the same Foxit folder
is EXECUTED, downloads the signed PDF, and hashes it into the final audit record.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import finalize_from_foxit_folder, write_audit_record
from .foxit_client import FoxitESignClient, FoxitNotConfigured


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalize a PolicyGate audit from Foxit eSign")
    parser.add_argument("pre_sign_audit", help="Path to *-audit-pre-sign.json")
    parser.add_argument("--output-dir", default="artifacts")
    args = parser.parse_args()

    pre_path = Path(args.pre_sign_audit)
    pre_sign = json.loads(pre_path.read_text(encoding="utf-8"))
    folder_id = str(pre_sign["foxit_folder_id"])
    if folder_id.startswith("MOCK-"):
        raise SystemExit("Cannot finalize a mock Foxit handoff. Use a real Foxit eSign folder.")

    client = FoxitESignClient()
    if not client.configured:
        raise FoxitNotConfigured("Foxit eSign credentials are required to finalize approval")

    folder_response = client.get_folder(folder_id)
    folder = folder_response.get("folder") or {}
    status = str(folder.get("folderStatus") or "UNKNOWN").upper()
    print(f"Foxit folder {folder_id}: {status}")
    if status != "EXECUTED":
        raise SystemExit("Human signature is not fully executed yet; audit remains pending.")

    signed_pdf = client.download_document(folder_id, doc_number=1)
    final = finalize_from_foxit_folder(pre_sign, folder_response, signed_pdf)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    request_id = pre_sign["request_id"]
    signed_path = out / f"{request_id}-signed.pdf"
    final_path = out / f"{request_id}-audit-final.json"
    signed_path.write_bytes(signed_pdf)
    write_audit_record(final, final_path)

    print(f"Signed PDF: {signed_path.resolve()}")
    print(f"Final audit: {final_path.resolve()}")
    print(f"Verified signer: {final.get('verified_signer_email')}")
    print("APPROVED — same Foxit folder, EXECUTED status, and expected signer identity verified.")


if __name__ == "__main__":
    main()

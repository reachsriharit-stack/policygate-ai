"""Local PDF renderer for offline/demo mode.

The PDF contains Foxit eSign Text Tags so the same artifact can be uploaded to
Foxit eSign with processTextTags=true. In a full sponsor-integrated demo, the
reversible document work can instead be performed through Foxit's official MCP
server; the eSign boundary remains the same.
"""
from __future__ import annotations

from io import BytesIO
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Preformatted
from reportlab.lib import colors

from .schema import WorkflowState


def render_evidence_pdf(evidence: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, title=f"PolicyGate {evidence['request_id']}")
    styles = getSampleStyleSheet()
    styles["Normal"].fontSize = 9
    styles["Normal"].leading = 12
    terraform_code_style = ParagraphStyle(
        "TerraformCode",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=5.5,
        leading=6.5,
        leftIndent=0,
        rightIndent=0,
        spaceBefore=0,
        spaceAfter=0,
    )
    hidden_tag_style = ParagraphStyle(
        "FoxitHiddenTag",
        parent=styles["Normal"],
        fontSize=1,
        leading=1,
        textColor=colors.white,
        spaceBefore=0,
        spaceAfter=0,
    )
    story = [
        Paragraph("PolicyGate AI — Change Approval Evidence Packet", styles["Title"]),
        Paragraph("AI can propose. Policy can validate. Only a human can authorize.", styles["Heading2"]),
        Spacer(1, 12),
    ]

    meta = [
        ["Request ID", evidence["request_id"]],
        ["Requested by", evidence["requested_by"]],
        ["Policy version", evidence["policy_version"]],
        ["Status", evidence["policy_status"]],
        ["Plan SHA-256", evidence["plan_sha256"]],
    ]
    table = Table(meta, colWidths=[120, 390])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story += [table, Spacer(1, 14), Paragraph("Proposed provisioning plan", styles["Heading2"])]

    plan = evidence["proposed_plan"]
    plan_rows = [[k.replace("_", " ").title(), str(v)] for k, v in plan.items()]
    plan_table = Table(plan_rows, colWidths=[180, 330])
    plan_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story += [plan_table, Spacer(1, 14), Paragraph("Deterministic policy checks", styles["Heading2"])]

    check_rows = [["Result", "Code", "Control", "Actual / Expected"]]
    for c in evidence["compliance_checks"]:
        check_rows.append([
            "PASS" if c["passed"] else "FAIL",
            c["code"],
            c["description"],
            f"{c['actual']} / {c['expected']}",
        ])
    checks = Table(check_rows, colWidths=[45, 55, 245, 165], repeatRows=1)
    checks.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [checks, Spacer(1, 16)]

    terraform_plan = evidence.get("terraform_plan")
    if terraform_plan:
        story += [
            Paragraph("Terraform plan", styles["Heading2"]),
            Paragraph(
                "Generated from the plan above and evaluated against the configured "
                "AWS environment. The hash below identifies the exact plan file — "
                "not just the intended configuration — that this approval covers.",
                styles["Normal"],
            ),
            Spacer(1, 6),
            Preformatted(terraform_plan.get("plan_summary", "").strip() or "(no plan summary available)", terraform_code_style),
            Spacer(1, 6),
            Paragraph(f"<b>Plan file SHA-256:</b> {terraform_plan.get('plan_file_sha256', 'N/A')}", styles["Normal"]),
            Spacer(1, 16),
        ]

    story += [Paragraph(evidence["ai_disclosure"], styles["Normal"])]

    if evidence["human_approval_required"]:
        story += [
            Spacer(1, 18),
            Paragraph("Human approval", styles["Heading2"]),
            Paragraph(
                "This document is not an authorization until a human approver signs it in Foxit eSign.",
                styles["Normal"],
            ),
            Spacer(1, 6),
            # The document should say, in as many words, where the agent
            # stopped. A reader should not have to infer it.
            Paragraph(
                f"<b>Workflow state:</b> {WorkflowState.AWAITING_HUMAN_APPROVAL.value} "
                "— the agent halted here and cannot sign, approve, or provision.",
                styles["Normal"],
            ),
            Spacer(1, 12),
            Paragraph("Approver signature: __________________________________________", styles["Normal"]),
            Paragraph("Date signed: ____________________", styles["Normal"]),
            Spacer(1, 4),
            # Keep Foxit Text Tags searchable in the PDF but visually unobtrusive.
            # With processTextTags=true Foxit converts them into signer fields.
            Paragraph("${signfield:1:y:approval_signature:200:30}", hidden_tag_style),
            Paragraph("${datefield:1:y:approval_date:100:20}", hidden_tag_style),
        ]

    doc.build(story)
    return buf.getvalue()

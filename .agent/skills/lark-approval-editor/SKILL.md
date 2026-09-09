---
name: lark-approval-editor
description: "Inspect and edit Lark Approval definitions through the official CLI/API."
---

# Lark Approval Editor

Use this skill for common tasks involving Lark Approval definitions, including
reading, translating, reorganizing, or updating a form or approval process.

## Letron PO implementation

- The editable source of truth for the PO Approval form/detail is
  `apps/auth-server/src/server/lark-po-approval-design.ts`.
- The official API synchronizer is
  `scripts/apply-lark-po-approval-design.ts`.
- The MR runtime mapper imports the same design file, so labels and the total
  row do not drift between the definition and newly created Approval records.
- After changing the design, run from `apps/auth-server`:
  `npx --yes tsx ../../scripts/apply-lark-po-approval-design.ts`.
- The compact item table uses five display columns: item/specification,
  supplier/RFQ, quantity, unit price, and line total. Keep the total row inside
  that table; do not reintroduce numeric `number`/`amount` children that cause
  Lark to render duplicate `Total-*` fields.

## Workflow

1. Confirm the target Approval and its `approval_code`.
2. Read the current definition before changing it.
3. Use the official typed CLI when available. In this repository, use the
   authenticated Lark API wrapper through the synchronizer when no usable
   `lark-cli` executable is installed.
4. Run a dry-run for every write. Make the actual change only after the user
   has authorized that change.
5. Read the definition back and verify the requested change, active status, and
   unchanged parts of the workflow.
6. Report the exact result and any remaining verification gate.

## Rules

- Edit the existing definition when the user asks to edit one; do not create a
  replacement definition unless explicitly requested.
- Preserve the existing Approval code, viewers, approvers, and process unless
  the user asks to change them.
- Prefer CLI/API over browser automation for Approval definition changes.
- Do not use Playwright for Approval definition edits or for creating test MR
  records when the authenticated API path is available.
- Never print or save secrets, tokens, cookies, or credentials.
- Do not claim end-to-end completion from a definition readback alone. If a
  business flow is requested, verify it through the real application flow.
- A valid PO handoff must create a new MR, RFQ, and Approval instance; the
  instance must be `PENDING` with a pending task assigned to
  `leducanh@ledb.vn`. Read back the instance form and verify the table rows,
  totals, labels, and absence of duplicate aggregate fields.
- Read the current official Lark documentation when the API behavior or CLI
  command is uncertain.

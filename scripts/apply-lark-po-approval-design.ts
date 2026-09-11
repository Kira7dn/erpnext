import { larkTenantJson } from "../apps/auth-server/src/server/lark";
import { getEnv } from "../apps/auth-server/src/server/env";
import { LARK_PO_APPROVAL_DESIGN } from "../apps/erp/src/lib/lark-po-approval-design";
import { LARK_PO_APPROVAL_CODE, LARK_PO_APPROVER_EMAIL } from "../apps/erp/src/lib/lark-runtime-config";

type Row = Record<string, any>;
const i18nKey = (value: string) => `@i18n@letron_po_${value}`;
const optionKey = (value: string) => i18nKey(`option_${value}`);
const fieldFor = (fields: Row[], wanted: Row): Row | undefined => {
  const matches = fields.filter((field) => field.name === wanted.label && field.type === wanted.type);
  if (matches.length > 1) throw new Error(`Approval semantic contract is ambiguous at ${wanted.key}`);
  return matches[0];
};
const columnFor = (fields: Row[], wanted: Row): Row | undefined => {
  const matches = fields.filter((field) => field.name === wanted.label && field.type === "input");
  if (matches.length > 1) throw new Error(`Approval table semantic contract is ambiguous at ${wanted.key}`);
  return matches[0];
};
getEnv();
const approvalCode = LARK_PO_APPROVAL_CODE;

async function main(): Promise<void> {
  const apply = process.argv.includes("--apply") || process.argv.includes("--dry-run");
  const current = (await larkTenantJson<{ data: Row }>(`/open-apis/approval/v4/approvals/${encodeURIComponent(approvalCode)}?user_id_type=user_id`)).data;
  const source = JSON.parse(String(current.form ?? "[]")) as Row[];
  const design = LARK_PO_APPROVAL_DESIGN.fields as readonly Row[];
  if (process.argv.includes("--dump")) {
    console.log(JSON.stringify({ mode: "dump", status: current.status, form: source, node_list: current.node_list, viewers: current.viewers }, null, 2));
    return;
  }
  if (source.length !== design.length) throw new Error(`Approval field count mismatch: live=${source.length}, design=${design.length}`);
  for (const wanted of design) {
    const actual = fieldFor(source, wanted);
    if (!actual) throw new Error(`Approval field contract mismatch at ${wanted.key}`);
  }
  const details = fieldFor(source, LARK_PO_APPROVAL_DESIGN.fields.find((field) => field.key === "details") as Row);
  const children = Array.isArray(details?.children) ? details.children : [];
  if (children.length !== LARK_PO_APPROVAL_DESIGN.table.columns.length) throw new Error("Approval field-list column count mismatch");
  for (const wanted of LARK_PO_APPROVAL_DESIGN.table.columns) {
    const actual = columnFor(children, wanted);
    if (!actual) throw new Error(`Approval column contract mismatch at ${wanted.key}`);
  }
  const purchaseType = fieldFor(source, LARK_PO_APPROVAL_DESIGN.fields.find((field) => field.key === "purchaseType") as Row);
  const options = Array.isArray(purchaseType?.option) ? purchaseType.option : [];
  const expectedOptions = Object.entries(LARK_PO_APPROVAL_DESIGN.purchaseTypeOptions);
  if (options.length !== expectedOptions.length || expectedOptions.some(([value, text], index) => options[index]?.value !== value || (!apply && options[index]?.text !== text))) {
    throw new Error("Approval purchase-type option contract mismatch");
  }
  const report = source.map((field) => ({ runtime_id: field.id, name: field.name, type: field.type }));
  const node = (Array.isArray(current.node_list) ? current.node_list : []).find((item: Row) => item.name || item.custom_node_id || item.node_id);
  if (!node) throw new Error("Approval approval node is missing");
  if (!apply) {
    console.log(JSON.stringify({
      mode: "check",
      status: current.status,
      approval_name: current.approval_name,
      i18n_resources: current.i18n_resources,
      settings: current.settings,
      config: current.config,
      fields: report,
      approval_node: { id: String(node.custom_node_id ?? node.node_id), need_approver: node.need_approver === true },
    }, null, 2));
    return;
  }

  const approverEmail = LARK_PO_APPROVER_EMAIL;
  const userResult = await larkTenantJson<{ data?: { user_list?: Array<{ user_id?: string }> } }>(
    "/open-apis/contact/v3/users/batch_get_id?user_id_type=user_id",
    { method: "POST", body: JSON.stringify({ emails: [approverEmail] }) },
  );
  const approverId = String(userResult.data?.user_list?.[0]?.user_id ?? "").trim();
  if (!approverId || userResult.data?.user_list?.length !== 1) throw new Error("Approval approver email did not resolve to exactly one user");
  const update = {
    approval_code: approvalCode,
    approval_name: "@i18n@letron_po_approval_name",
    form: { form_content: JSON.stringify(source.map((sourceField) => {
      const wanted = design.find((field) => field.label === sourceField.name && field.type === sourceField.type);
      const field: Row = { ...sourceField, name: wanted ? i18nKey(wanted.key) : sourceField.name };
      if (wanted?.type === "radioV2") {
        const liveOptions = Array.isArray(sourceField.option) ? sourceField.option : [];
        field.value = liveOptions.map((option: Row) => ({ key: String(option.value ?? ""), text: optionKey(String(option.value ?? "")) }));
        delete field.option;
      }
      if (wanted?.type === "fieldList" && Array.isArray(sourceField.children)) {
        field.option = {
          ...(sourceField.option ?? {}),
          inputType: LARK_PO_APPROVAL_DESIGN.table.inputType,
          printType: LARK_PO_APPROVAL_DESIGN.table.printType,
        };
        field.value = sourceField.children.map((child: Row) => {
          const column = LARK_PO_APPROVAL_DESIGN.table.columns.find((item) => item.label === child.name && child.type === "input");
          return { ...child, name: column ? i18nKey(column.key) : child.name };
        });
        delete field.children;
      }
      return field;
    })) },
    node_list: [
      { id: "START" },
      {
        id: LARK_PO_APPROVAL_DESIGN.process.approvalNode.sourceId,
        name: "@i18n@letron_po_node_approval",
        node_type: String(node.node_type ?? "AND"),
        need_approver: true,
        approver_chosen_multi: false,
        approver: [{ type: "Personal", user_id: approverId }],
      },
      { id: "END" },
    ],
    i18n_resources: [{
      locale: "zh-CN",
      is_default: true,
      texts: [
        { key: "@i18n@letron_po_approval_name", value: "Phê duyệt mua hàng" },
        { key: "@i18n@letron_po_node_approval", value: "Phê duyệt" },
        ...design.map((field) => ({ key: i18nKey(field.key), value: field.label })),
        ...LARK_PO_APPROVAL_DESIGN.table.columns.map((column) => ({ key: i18nKey(column.key), value: column.label })),
        ...Object.entries(LARK_PO_APPROVAL_DESIGN.purchaseTypeOptions).map(([value, text]) => ({ key: optionKey(value), value: text })),
      ],
    }],
    viewers: [{ viewer_type: "TENANT" }],
    status: current.status,
  };
  if (process.argv.includes("--dry-run")) {
    console.log(JSON.stringify({ mode: "dry-run", approval_code: approvalCode, approval_node: update.node_list[1], status: current.status }, null, 2));
    return;
  }
  const result = await larkTenantJson<Row>("/open-apis/approval/v4/approvals?user_id_type=user_id", {
    method: "POST",
    body: JSON.stringify(update),
  });
  console.log(JSON.stringify({ mode: "apply", code: result.code ?? 0, status: current.status, approver: approverEmail }, null, 2));
}
main().catch((error: unknown) => { console.error(error instanceof Error ? error.message : error); process.exitCode = 1; });

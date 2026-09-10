import { larkTenantJson } from "../apps/auth-server/src/server/lark.ts";
import { getEnv } from "../apps/auth-server/src/server/env.ts";
import { LARK_PO_APPROVAL_DESIGN, larkI18nKey } from "../apps/erp/src/lib/lark-approval-design.ts";

type Row = Record<string, any>;
getEnv();
const code = process.env.LARK_PO_APPROVAL_CODE?.trim();
if (!code) throw new Error("LARK_PO_APPROVAL_CODE is required");
const key = (suffix: string) => larkI18nKey(suffix);

const labels: Record<string, string> = Object.fromEntries([
  ...LARK_PO_APPROVAL_DESIGN.fields.map((field: { sourceId: string; label: string }) => [field.sourceId, field.label]),
  ...LARK_PO_APPROVAL_DESIGN.table.columns.map((column: { id: string; label: string }) => [column.id, column.label]),
]);
const optionLabels: Record<string, string> = LARK_PO_APPROVAL_DESIGN.purchaseTypeOptions;
const topLabelKeys = LARK_PO_APPROVAL_DESIGN.fields.map((field: { sourceId: string }) => field.sourceId);

function rename(field: Row, labelKey: string): Row {
  const copy = { ...field };
  if (labels[labelKey]) copy.name = key(labelKey);
  return copy;
}

async function main(): Promise<void> {
  const current = await larkTenantJson<{ data: Row }>(
    `/open-apis/approval/v4/approvals/${encodeURIComponent(code)}?user_id_type=user_id`,
  );
  const definition = current.data;
  const sourceForm = JSON.parse(String(definition.form ?? "[]")) as Row[];
  const usedSourceFields = new Set<Row>();
  const sourceFormOrdered = LARK_PO_APPROVAL_DESIGN.fields
    .map((wanted: { sourceId: string; type: string }) => {
      const source = sourceForm.find(
        (field) =>
          !usedSourceFields.has(field) &&
          (field.id === wanted.sourceId || field.custom_id === wanted.sourceId || field.name === wanted.label),
      ) ?? sourceForm.find((field) => !usedSourceFields.has(field) && field.type === wanted.type);
      if (source) usedSourceFields.add(source);
      return source;
    })
    .filter((field): field is Row => Boolean(field));
  const form = sourceFormOrdered.map((source, index) => {
    const wanted = LARK_PO_APPROVAL_DESIGN.fields[index];
    const field = rename(source, topLabelKeys[index] ?? String(source.custom_id ?? source.id ?? index));
    if (wanted?.type) field.type = wanted.type;
    if (field.type === "radioV2") {
      const options = Array.isArray(source.option) ? source.option : [];
      field.value = options.map((option: Row) => ({
        key: String(option.value ?? ""),
        text: key(`option_${String(option.value ?? "").replaceAll("-", "_")}`),
      }));
      delete field.option;
    }
    if (field.type === "fieldList") {
      const oldChildren = Array.isArray(source.children) ? source.children : [];
      const oldItem = oldChildren.find((child: Row) => child.type === "input") ?? oldChildren[0];
      const oldQuantity = oldChildren.find((child: Row) => child.type === "number");
      const oldAmounts = oldChildren.filter((child: Row) => child.type === "amount");
      const inputField = (id: string, labelKey: string, sourceField?: Row): Row => {
        const result = { ...(sourceField ?? {}), id, custom_id: id, type: "input", name: key(labelKey), required: false, printable: true, visible: true };
        delete result.option;
        delete result.options;
        delete result.value;
        return result;
      };
      const columns = LARK_PO_APPROVAL_DESIGN.table.columns;
      const children = [
        inputField(columns[0].id, columns[0].id, oldItem),
        inputField(columns[1].id, columns[1].id),
        inputField(columns[2].id, columns[2].id, oldQuantity),
        inputField(columns[3].id, columns[3].id, oldAmounts[0]),
        inputField(columns[4].id, columns[4].id, oldAmounts[1]),
      ];
      field.value = children;
      field.option = {
        inputType: LARK_PO_APPROVAL_DESIGN.table.inputType,
        printType: LARK_PO_APPROVAL_DESIGN.table.printType,
      };
      delete field.children;
    }
    if (field.type === "amount") field.value = "VND";
    return field;
  });
  const i18nTexts = Object.entries(labels).map(([id, value]) => ({ key: key(id), value }));
  for (const [option, value] of Object.entries(optionLabels)) {
    i18nTexts.push({ key: key(`option_${option.replaceAll("-", "_")}`), value });
  }
  i18nTexts.push({ key: key(LARK_PO_APPROVAL_DESIGN.approvalName.key), value: LARK_PO_APPROVAL_DESIGN.approvalName.label });
  i18nTexts.push({ key: key(LARK_PO_APPROVAL_DESIGN.process.approvalNode.key), value: LARK_PO_APPROVAL_DESIGN.process.approvalNode.label });

  const sourceNodes = Array.isArray(definition.node_list) ? definition.node_list : [];
  const sourceApprovalNode = sourceNodes.find((node: Row) => node.name || node.custom_node_id) ?? sourceNodes[0] ?? {};
  const payload = {
    approval_code: code,
    approval_name: key(LARK_PO_APPROVAL_DESIGN.approvalName.key),
    form: { form_content: JSON.stringify(form) },
    node_list: [
      { id: "START" },
      {
        id: String(sourceApprovalNode.custom_node_id ?? sourceApprovalNode.node_id ?? "approval_node"),
        name: key(LARK_PO_APPROVAL_DESIGN.process.approvalNode.key),
        node_type: String(sourceApprovalNode.node_type ?? "AND"),
        approver: [{ type: "Personal", user_id: LARK_PO_APPROVAL_DESIGN.process.approvalNode.approverUserId }],
      },
      { id: "END" },
    ],
    viewers: (Array.isArray(definition.viewers) ? definition.viewers : []).map((viewer: Row) => ({
      viewer_type: String(viewer.viewer_type ?? viewer.type ?? LARK_PO_APPROVAL_DESIGN.process.viewerType),
      ...(viewer.viewer_user_id ? { viewer_user_id: viewer.viewer_user_id } : {}),
      ...(viewer.viewer_department_id ? { viewer_department_id: viewer.viewer_department_id } : {}),
    })),
    status: definition.status,
    i18n_resources: [{ locale: LARK_PO_APPROVAL_DESIGN.locale, is_default: true, texts: i18nTexts }],
    process_manager_ids: [LARK_PO_APPROVAL_DESIGN.process.approvalNode.approverUserId],
  };
  const result = await larkTenantJson<Row>(
    "/open-apis/approval/v4/approvals?user_id_type=user_id",
    { method: "POST", body: JSON.stringify(payload) },
  );
  const updated = await larkTenantJson<{ data: Row }>(
    `/open-apis/approval/v4/approvals/${encodeURIComponent(code)}?user_id_type=user_id`,
  );
  const updatedForm = JSON.parse(String(updated.data.form ?? "[]")) as Row[];
  const names = updatedForm.flatMap((field) => [field.name, ...(Array.isArray(field.children) ? field.children.map((child: Row) => child.name) : [])]);
  if (names.some((name) => String(name).includes("?"))) throw new Error("Approval labels still contain '?'");
  console.log(JSON.stringify({ updated: true, response: result, approval_name: updated.data.approval_name, status: updated.data.status, labels: names }, null, 2));
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});

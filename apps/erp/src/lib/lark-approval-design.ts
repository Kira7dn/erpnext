export type ApprovalDesignField = { key: string; sourceId: string; label: string; type: string };
export type ApprovalDesignTableColumn = { key: string; id: string; label: string };

export const LARK_PO_APPROVAL_DESIGN = {
  locale: "zh-CN",
  approvalName: { key: "approval_name", label: "Phê duyệt mua hàng" },
  process: { approvalNode: { key: "node_approval", label: "Phê duyệt", approverUserId: "2619cbfe" }, viewerType: "TENANT" },
  fields: [
    { key: "reason", sourceId: "widget17889414560", label: "Lý do mua hàng", type: "textarea" },
    { key: "reference", sourceId: "widget17889414561", label: "Đường dẫn chi tiết", type: "input" },
    { key: "purchaseType", sourceId: "widget17889414562", label: "Loại mua hàng", type: "radioV2" },
    { key: "deliveryDate", sourceId: "widget17889414563", label: "Ngày cần giao hàng", type: "date" },
    { key: "details", sourceId: "widget17889414567", label: "Chi tiết mua hàng", type: "fieldList" },
    { key: "paymentTerms", sourceId: "widget17889414565", label: "Điều khoản thanh toán", type: "textarea" },
    { key: "deliveryTerms", sourceId: "widget17889414566", label: "Điều kiện giao hàng", type: "textarea" },
    { key: "attachments", sourceId: "widget178894145613", label: "Tài liệu đính kèm", type: "attachmentV2" },
  ] satisfies ApprovalDesignField[],
  table: {
    inputType: "FORM",
    printType: "FORM",
    columns: [
      { key: "itemSummary", id: "letron_po_item_summary", label: "Hàng hóa / Quy cách" },
      { key: "supplierRfq", id: "letron_po_supplier_rfq", label: "Nhà cung cấp / RFQ" },
      { key: "quantity", id: "letron_po_qty", label: "SL" },
      { key: "unitPrice", id: "letron_po_unit_price", label: "Đơn giá" },
      { key: "lineTotal", id: "letron_po_line_total", label: "Thành tiền" },
    ] satisfies ApprovalDesignTableColumn[],
  },
  purchaseTypeOptions: {
    "k3qy4q8h-ssvnqr2zmyl-0": "Văn phòng phẩm",
    "k3qy4q90-7zxkc97h7ny-1": "Hoạt động",
    "k3qy4q90-ya5zdx7hyh-3": "Nguyên vật liệu sản xuất",
    "k3qy4q90-6gm9nps0bwj-5": "Khác",
  } as Record<string, string>,
} as const;

export function larkI18nKey(suffix: string): string { return `@i18n@letron_po_${suffix}`; }

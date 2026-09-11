export type ApprovalDesignColumn = {
  key: string;
  label: string;
};

export type ApprovalDesignField = {
  key: string;
  label: string;
  type: string;
  selected?: string;
};

export const LARK_PO_APPROVAL_DESIGN = {
  locale: "zh-CN",
  textLanguage: "vi-VN",
  approvalName: { key: "approval_name", label: "Phê duyệt mua hàng" },
  process: { approvalNode: { key: "node_approval", label: "Phê duyệt", sourceId: "7106864726566" }, viewerType: "TENANT" },
  fields: [
    { key: "reason", label: "Lý do mua hàng", type: "textarea" },
    { key: "reference", label: "Thông tin tham chiếu", type: "input" },
    { key: "purchaseType", label: "Loại mua hàng", type: "radioV2", selected: "Nguyên vật liệu sản xuất" },
    { key: "deliveryDate", label: "Ngày cần giao hàng", type: "date" },
    { key: "details", label: "Chi tiết mua hàng", type: "fieldList" },
    { key: "paymentTerms", label: "Điều khoản thanh toán", type: "textarea" },
    { key: "deliveryTerms", label: "Điều kiện giao hàng", type: "textarea" },
    { key: "attachments", label: "Tài liệu đính kèm", type: "attachmentV2" },
  ] as const satisfies readonly ApprovalDesignField[],
  table: {
    inputType: "FORM",
    printType: "FORM",
    columns: [
      { key: "itemSummary", label: "Hàng hóa / Quy cách" },
      { key: "supplierRfq", label: "Nhà cung cấp / RFQ" },
      { key: "quantity", label: "SL" },
      { key: "unitPrice", label: "Đơn giá" },
      { key: "lineTotal", label: "Thành tiền" },
    ] as const satisfies readonly ApprovalDesignColumn[],
  },
  purchaseTypeOptions: {
    "k3qy4q8h-ssvnqr2zmyl-0": "Văn phòng phẩm",
    "k3qy4q90-7zxkc97h7ny-1": "Hoạt động",
    "k3qy4q90-ya5zdx7hyh-3": "Nguyên vật liệu sản xuất",
    "k3qy4q90-6gm9nps0bwj-5": "Khác",
  } as const,
} as const;

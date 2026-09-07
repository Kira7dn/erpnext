const ACCOUNTING_LABELS: Record<string, string> = {
  banks: "Ngân hàng",
  "bank-accounts": "Tài khoản ngân hàng",
  "bank-transactions": "Giao dịch ngân hàng",
  "bank-transaction-rules": "Quy tắc giao dịch ngân hàng",
  "cost-centers": "Trung tâm chi phí",
  "journal-entries": "Journal Entry",
  "modes-of-payment": "Phương thức thanh toán",
  "payment-entries": "Payment Entry",
  "payment-orders": "Lệnh thanh toán",
  "payment-requests": "Yêu cầu thanh toán",
  "purchase-invoices": "Purchase Invoice",
  "sales-invoices": "Sales Invoice",
};

const ASSET_LABELS: Record<string, string> = {
  assets: "Tài sản",
  "asset-categories": "Nhóm tài sản",
  "asset-capitalizations": "Asset Capitalization",
  "asset-maintenance": "Bảo trì tài sản",
  "asset-movements": "Điều chuyển tài sản",
  "asset-repairs": "Sửa chữa tài sản",
  "asset-value-adjustments": "Điều chỉnh giá trị tài sản",
  "asset-maintenance-teams": "Đội bảo trì",
  "asset-maintenance-logs": "Nhật ký bảo trì",
  "asset-depreciation-schedules": "Lịch khấu hao",
  "asset-shift-factors": "Hệ số ca tài sản",
  "asset-shift-allocations": "Phân bổ ca tài sản",
  locations: "Địa điểm",
};

const FIELD_LABELS: Record<string, string> = {
  name: "Tên / Mã",
  company: "Công ty",
  account: "Tài khoản sổ cái",
  account_name: "Tên tài khoản",
  bank: "Ngân hàng",
  bank_account: "Tài khoản ngân hàng",
  posting_date: "Ngày hạch toán",
  transaction_date: "Ngày giao dịch",
  description: "Mô tả",
  status: "Trạng thái",
  disabled: "Đã vô hiệu hóa",
  amount: "Số tiền",
  cost_center: "Trung tâm chi phí",
  asset: "Tài sản",
  location: "Địa điểm",
};

export function accountingLabel(resource: string): string { return ACCOUNTING_LABELS[resource] ?? humanize(resource); }
export function assetLabel(resource: string): string { return ASSET_LABELS[resource] ?? humanize(resource); }
export function fieldLabel(field: string): string { return FIELD_LABELS[field] ?? humanize(field); }
export function humanize(value: string): string { return value.replaceAll("_", " ").replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }

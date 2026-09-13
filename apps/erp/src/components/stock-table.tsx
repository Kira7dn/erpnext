import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const labels: Record<string, string> = { name: "Mã", warehouse_name: "Tên kho", company: "Công ty", parent_warehouse: "Kho cha", warehouse_type: "Loại", is_group: "Kho nhóm", disabled: "Vô hiệu", supplier: "Nhà cung cấp", posting_date: "Ngày nhập", set_warehouse: "Kho", status: "Trạng thái", docstatus: "Trạng thái" };
const shown: Record<string, string[]> = { warehouses: ["name", "warehouse_name", "company", "parent_warehouse", "warehouse_type", "is_group", "disabled"], "purchase-receipts": ["name", "supplier", "posting_date", "company", "set_warehouse", "status", "docstatus"] };
function value(value: unknown): string { if (value === null || value === undefined || value === "") return "—"; if (typeof value === "boolean" || typeof value === "number") return value ? "Có" : "Không"; return String(value); }

export function StockTable({ resource, rows, basePath = "/stock" }: Readonly<{ resource: "warehouses" | "purchase-receipts"; rows: Record<string, unknown>[]; basePath?: string }>) {
  const columns = shown[resource];
  return <div className="overflow-hidden rounded-xl border bg-card shadow-sm"><Table><TableHeader><TableRow>{columns.map((column) => <TableHead key={column}>{labels[column] ?? column}</TableHead>)}<TableHead> </TableHead></TableRow></TableHeader><TableBody>{rows.map((row) => { const name = String(row.name ?? ""); const href = resource === "warehouses" ? `${basePath}/warehouses/${encodeURIComponent(name)}` : `${basePath}/receipts/${encodeURIComponent(name)}`; return <TableRow key={name}>{columns.map((column) => <TableCell key={column}>{column === "name" ? <Link className="font-medium text-emerald-700 hover:underline" href={href}>{name}</Link> : value(row[column])}</TableCell>)}<TableCell><Badge variant={Number(row.docstatus) === 1 ? "default" : "secondary"}>{Number(row.docstatus) === 1 ? "Đã submit" : resource === "purchase-receipts" ? "Draft" : row.disabled ? "Đã vô hiệu" : "Hoạt động"}</Badge></TableCell></TableRow>; })}</TableBody></Table>{!rows.length ? <div className="p-12 text-center text-sm text-muted-foreground">API không trả về bản ghi nào.</div> : null}</div>;
}

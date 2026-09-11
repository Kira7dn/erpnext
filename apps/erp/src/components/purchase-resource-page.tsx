"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { larkLoginHref } from "@/lib/auth-navigation";

type Row = Record<string, unknown>;
type Kind = "supplier" | "item" | "request";
type Field = {
  name: string;
  label: string;
  required?: boolean;
  type?: "date" | "number" | "boolean" | "select" | "link";
  options?: string[];
  link?: "contacts" | "addresses";
};
type ItemRow = {
  item_code: string;
  qty: number | string;
  schedule_date: string;
  warehouse: string;
  uom: string;
  stock_uom: string;
  conversion_factor: number;
  rate: number | string;
};
type ActiveOrchestration = {
  id: string;
  status:
    | "started"
    | "mr_created"
    | "partial_failure"
    | "rfq_created"
    | "waiting_supplier_quotes"
    | "failed";
  material_request_name?: string;
  request_for_quotation_name?: string;
  retry_count: number;
  error?: string;
  updated_at: string;
};
type ListFilter = { field: string; value: string };
type Toast = { message: string; tone: "success" | "error" | "warning" };

const filterFields: Record<Kind, { field: string; label: string }[]> = {
  supplier: [
    { field: "supplier_name", label: "Tên" },
    { field: "supplier_group", label: "Nhóm" },
    { field: "supplier_type", label: "Loại" },
    { field: "disabled", label: "Trạng thái" },
  ],
  item: [
    { field: "item_code", label: "Mã" },
    { field: "item_name", label: "Tên" },
    { field: "item_group", label: "Nhóm" },
    { field: "disabled", label: "Trạng thái" },
  ],
  request: [
    { field: "name", label: "Mã request" },
    { field: "company", label: "Công ty" },
    { field: "material_request_type", label: "Loại" },
    { field: "docstatus", label: "Trạng thái" },
    { field: "owner", label: "Người tạo" },
  ],
};
const listFields: Record<Kind, { field: string; label: string }[]> = {
  supplier: [
    { field: "name", label: "Mã" },
    { field: "supplier_name", label: "Tên" },
    { field: "supplier_type", label: "Loại" },
    { field: "supplier_group", label: "Nhóm" },
    { field: "country", label: "Quốc gia" },
    { field: "disabled", label: "Inactive" },
  ],
  item: [
    { field: "name", label: "Mã" },
    { field: "item_code", label: "Item code" },
    { field: "item_name", label: "Tên" },
    { field: "item_group", label: "Nhóm" },
    { field: "stock_uom", label: "UOM" },
    { field: "is_stock_item", label: "Tồn kho" },
    { field: "disabled", label: "Inactive" },
  ],
  request: [
    { field: "name", label: "Mã request" },
    { field: "title", label: "Tiêu đề" },
    { field: "company", label: "Công ty" },
    { field: "material_request_type", label: "Loại" },
    { field: "schedule_date", label: "Ngày cần" },
    { field: "owner", label: "Người tạo" },
    { field: "docstatus", label: "Trạng thái" },
  ],
};

const config: Record<
  Kind,
  { code: string; title: string; endpoint: string; fields: Field[] }
> = {
  supplier: {
    code: "PUR-01",
    title: "Nhà cung cấp",
    endpoint: "suppliers",
    fields: [
      { name: "supplier_name", label: "Tên nhà cung cấp", required: true },
      {
        name: "supplier_type",
        label: "Loại",
        required: true,
        type: "select",
        options: ["Company", "Individual", "Partnership"],
      },
      { name: "supplier_group", label: "Nhóm nhà cung cấp", required: true },
      { name: "country", label: "Quốc gia" },
      { name: "tax_id", label: "Mã số thuế" },
      { name: "default_currency", label: "Tiền tệ mặc định" },
      { name: "default_price_list", label: "Bảng giá mua" },
      { name: "payment_terms", label: "Điều khoản thanh toán" },
      { name: "website", label: "Website" },
      {
        name: "supplier_primary_contact",
        label: "Contact chính",
        type: "link",
        link: "contacts",
      },
      {
        name: "supplier_primary_address",
        label: "Address chính",
        type: "link",
        link: "addresses",
      },
      { name: "disabled", label: "Vô hiệu hóa", type: "boolean" },
      {
        name: "is_transporter",
        label: "Là đơn vị vận chuyển",
        type: "boolean",
      },
      {
        name: "is_internal_supplier",
        label: "Nhà cung cấp nội bộ",
        type: "boolean",
      },
      { name: "represents_company", label: "Đại diện công ty" },
      { name: "warn_rfqs", label: "Cảnh báo RFQ", type: "boolean" },
      { name: "prevent_rfqs", label: "Chặn RFQ", type: "boolean" },
      { name: "on_hold", label: "Tạm giữ", type: "boolean" },
      { name: "hold_type", label: "Phạm vi tạm giữ" },
      { name: "release_date", label: "Ngày mở lại", type: "date" },
    ],
  },
  item: {
    code: "PUR-02",
    title: "Item / Vật tư",
    endpoint: "items",
    fields: [
      { name: "item_code", label: "Mã Item", required: true },
      { name: "item_name", label: "Tên Item" },
      { name: "item_group", label: "Nhóm Item", required: true },
      { name: "stock_uom", label: "Đơn vị tồn kho", required: true },
      { name: "description", label: "Mô tả" },
      { name: "brand", label: "Thương hiệu" },
      { name: "is_stock_item", label: "Theo dõi tồn kho", type: "boolean" },
      { name: "is_purchase_item", label: "Cho phép mua", type: "boolean" },
      { name: "purchase_uom", label: "Đơn vị mua" },
      {
        name: "min_order_qty",
        label: "Số lượng mua tối thiểu",
        type: "number",
      },
      {
        name: "lead_time_days",
        label: "Thời gian giao hàng (ngày)",
        type: "number",
      },
      {
        name: "default_material_request_type",
        label: "Loại Material Request mặc định",
      },
      {
        name: "inspection_required_before_purchase",
        label: "Kiểm tra trước khi mua",
        type: "boolean",
      },
      { name: "has_batch_no", label: "Có Batch", type: "boolean" },
      { name: "has_serial_no", label: "Có Serial No", type: "boolean" },
      { name: "disabled", label: "Vô hiệu hóa", type: "boolean" },
    ],
  },
  request: {
    code: "PUR-03",
    title: "Material Request",
    endpoint: "material-requests",
    fields: [
      { name: "naming_series", label: "Naming Series", required: true },
      { name: "company", label: "Công ty", required: true },
      {
        name: "material_request_type",
        label: "Loại yêu cầu",
        required: true,
        type: "select",
        options: [
          "Purchase",
          "Material Transfer",
          "Material Issue",
          "Manufacture",
        ],
      },
      {
        name: "transaction_date",
        label: "Ngày giao dịch",
        required: true,
        type: "date",
      },
      { name: "schedule_date", label: "Ngày cần hàng", type: "date" },
      { name: "title", label: "Tiêu đề" },
      { name: "customer", label: "Khách hàng" },
      { name: "set_warehouse", label: "Kho nhận" },
      { name: "set_from_warehouse", label: "Kho xuất" },
      { name: "buying_price_list", label: "Bảng giá mua" },
    ],
  },
};

function messageFor(status: number) {
  return status === 401
    ? "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại bằng Lark."
    : status === 403
      ? "Tài khoản chưa được cấp quyền cho phân hệ này."
      : status >= 502
        ? "Letron Gateway hiện không khả dụng."
        : `Yêu cầu thất bại (${status}).`;
}

class PurchaseApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "PurchaseApiError";
  }
}

async function api(path: string, init?: RequestInit) {
  const isMultipart =
    typeof FormData !== "undefined" && init?.body instanceof FormData;
  const response = await fetch(`/api/purchase/${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(init?.body && !isMultipart
        ? { "Content-Type": "application/json" }
        : {}),
      ...init?.headers,
    },
  });
  if (!response.ok)
    throw new PurchaseApiError(response.status, messageFor(response.status));
  const body = (await response.json()) as { data?: unknown; message?: unknown };
  return body.data ?? body.message ?? body;
}
const ATTACHMENT_DOCTYPES: Record<Kind, string> = {
  supplier: "Supplier",
  item: "Item",
  request: "Material Request",
};
function text(value: unknown) {
  return value === null || value === undefined || value === ""
    ? "—"
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
}
function displayCell(field: string, value: unknown) {
  if (field === "disabled" || field === "is_stock_item")
    return value ? "Có" : "Không";
  if (field === "docstatus")
    return value === 1 ? "Submitted" : value === 2 ? "Cancelled" : "Draft";
  return text(value);
}
function dateValue(value?: unknown) {
  return typeof value === "string" && value
    ? value.slice(0, 10)
    : new Date().toISOString().slice(0, 10);
}
function initialValues(kind: Kind, row?: Row): Row {
  return Object.fromEntries(
    config[kind].fields.map((field) => [
      field.name,
      row?.[field.name] ??
        (field.type === "boolean"
          ? false
          : field.name === "naming_series"
            ? "MR-.YYYYMMDD.-.####"
            : field.type === "date"
              ? dateValue()
              : ""),
    ]),
  );
}

export function PurchaseResourcePage({ kind }: Readonly<{ kind: Kind }>) {
  const meta = config[kind];
  const [rows, setRows] = useState<Row[]>([]);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [orchestrationId, setOrchestrationId] = useState<string | null>(() => {
    if (kind !== "request" || typeof window === "undefined") return null;
    return new URLSearchParams(window.location.search).get("orchestration");
  });
  const [filter, setFilter] = useState<ListFilter>(() => {
    if (typeof window === "undefined")
      return { field: filterFields[kind][0].field, value: "" };
    const params = new URLSearchParams(window.location.search);
    return {
      field: params.get("filter_field") ?? filterFields[kind][0].field,
      value: params.get("filter") ?? "",
    };
  });
  const [sort, setSort] = useState("modified desc");
  const [toast, setToast] = useState<Toast | null>(null);
  const [editing, setEditing] = useState<Row | null>(null);
  const [creating, setCreating] = useState(false);
  const [opening, setOpening] = useState(false);
  const [hasNext, setHasNext] = useState(false);
  const [activeOrchestrations, setActiveOrchestrations] = useState<
    ActiveOrchestration[]
  >([]);
  const [activeBusy, setActiveBusy] = useState(false);
  const [activeError, setActiveError] = useState<string | null>(null);
  const [retryingActiveId, setRetryingActiveId] = useState<string | null>(null);
  const load = useCallback(
    async (nextPage = 1) => {
      setBusy(true);
      setError(null);
      setErrorStatus(null);
      try {
        const params = new URLSearchParams({
          limit_page_length: "26",
          limit_start: String((nextPage - 1) * 25),
          order_by: sort,
          fields: JSON.stringify(listFields[kind].map((item) => item.field)),
        });
        if (filter.value.trim())
          params.set(
            "filters",
            JSON.stringify([
              [filter.field, "like", `%${filter.value.trim()}%`],
            ]),
          );
        const result = await api(`${meta.endpoint}?${params.toString()}`);
        const data = Array.isArray(result) ? (result as Row[]) : [];
        const enriched = await Promise.all(
          data.slice(0, 25).map(async (row) => {
            if (!row.name || Object.keys(row).length > 2) return row;
            try {
              return (await api(
                `${meta.endpoint}/${encodeURIComponent(String(row.name))}`,
              )) as Row;
            } catch {
              return row;
            }
          }),
        );
        setHasNext(data.length > 25);
        setRows(enriched);
        setPage(nextPage);
      } catch (cause) {
        setErrorStatus(cause instanceof PurchaseApiError ? cause.status : null);
        setError(
          cause instanceof Error ? cause.message : "Không thể tải dữ liệu.",
        );
      } finally {
        setBusy(false);
      }
    },
    [filter.field, filter.value, kind, meta.endpoint, sort],
  );
  useEffect(() => {
    const timer = window.setTimeout(() => void load(1), 0);
    return () => window.clearTimeout(timer);
  }, [load]);
  const loadActive = useCallback(async () => {
    if (kind !== "request") return;
    setActiveBusy(true);
    setActiveError(null);
    try {
      const result = await api("requests/orchestrations/active");
      setActiveOrchestrations(
        Array.isArray(result) ? (result as ActiveOrchestration[]) : [],
      );
    } catch (cause) {
      setActiveError(
        cause instanceof Error
          ? cause.message
          : "Không thể tải danh sách cần xử lý.",
      );
    } finally {
      setActiveBusy(false);
    }
  }, [kind]);
  useEffect(() => {
    const timer = window.setTimeout(() => void loadActive(), 0);
    return () => window.clearTimeout(timer);
  }, [loadActive]);
  useEffect(() => {
    if (kind !== "request" || !orchestrationId) return;
    let cancelled = false;
    const openOrchestration = async () => {
      setOpening(true);
      setError(null);
      setErrorStatus(null);
      try {
        let materialRequestName = "";
        try {
          const orchestration = (await api(
            `requests/orchestrations/${encodeURIComponent(orchestrationId)}`,
          )) as ActiveOrchestration;
          materialRequestName = String(
            orchestration.material_request_name ?? "",
          );
        } catch (cause) {
          if (!(cause instanceof PurchaseApiError) || cause.status !== 404)
            throw cause;
        }
        if (!materialRequestName) {
          const filters = encodeURIComponent(
            JSON.stringify([
              [
                "Material Request",
                "custom_letron_orchestration_id",
                "=",
                orchestrationId,
              ],
            ]),
          );
          const matches = await api(
            `material-requests?filters=${filters}&fields=${encodeURIComponent(
              JSON.stringify(["name"]),
            )}&limit_page_length=2`,
          );
          const match = Array.isArray(matches) ? (matches[0] as Row) : null;
          materialRequestName = String(match?.name ?? "");
        }
        if (!materialRequestName)
          throw new Error(
            "Orchestration chưa có Material Request để mở chi tiết.",
          );
        const materialRequest = (await api(
          `material-requests/${encodeURIComponent(materialRequestName)}`,
        )) as Row;
        if (!cancelled) setEditing(materialRequest);
      } catch (cause) {
        if (!cancelled) {
          setErrorStatus(
            cause instanceof PurchaseApiError ? cause.status : null,
          );
          setError(
            cause instanceof Error
              ? cause.message
              : "Không thể mở Material Request từ orchestration.",
          );
        }
      } finally {
        if (!cancelled) setOpening(false);
      }
    };
    void openOrchestration();
    return () => {
      cancelled = true;
    };
  }, [kind, orchestrationId]);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (query) params.set("q", query);
    else params.delete("q");
    if (filter.value) {
      params.set("filter", filter.value);
      params.set("filter_field", filter.field);
    } else {
      params.delete("filter");
      params.delete("filter_field");
    }
    if (sort !== "modified desc") params.set("sort", sort);
    else params.delete("sort");
    if (orchestrationId) params.set("orchestration", orchestrationId);
    else params.delete("orchestration");
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${params.toString() ? `?${params}` : ""}`,
    );
  }, [filter, orchestrationId, query, sort]);
  async function retryActive(id: string) {
    if (retryingActiveId) return;
    setRetryingActiveId(id);
    setActiveError(null);
    try {
      const result = (await api(
        `requests/orchestrations/${encodeURIComponent(id)}/retry-rfq`,
        { method: "POST" },
      )) as ActiveOrchestration;
      if (result.status === "waiting_supplier_quotes") {
        setActiveOrchestrations((current) =>
          current.filter((item) => item.id !== id),
        );
        setToast({ message: "Đã retry RFQ thành công.", tone: "success" });
      } else {
        setActiveOrchestrations((current) =>
          current.map((item) => (item.id === id ? result : item)),
        );
      }
    } catch (cause) {
      setActiveError(
        cause instanceof Error ? cause.message : "Không thể retry RFQ.",
      );
      setToast({
        message: cause instanceof Error ? cause.message : "Retry RFQ thất bại.",
        tone: "error",
      });
      await loadActive();
    } finally {
      setRetryingActiveId(null);
    }
  }
  const filtered = useMemo(
    () =>
      rows.filter(
        (row) =>
          JSON.stringify(row).toLowerCase().includes(query.toLowerCase()) &&
          (!filter.value.trim() ||
            String(row[filter.field] ?? "")
              .toLowerCase()
              .includes(filter.value.trim().toLowerCase())),
      ),
    [filter.field, filter.value, rows, query],
  );
  const columns = listFields[kind];
  const applyFilter = () => {
    setPage(1);
    void load(1);
  };
  const openDetail = async (row: Row) => {
    if (!row.name || opening) return;
    setOpening(true);
    try {
      setEditing(
        (await api(
          `${meta.endpoint}/${encodeURIComponent(String(row.name))}`,
        )) as Row,
      );
    } catch (cause) {
      setErrorStatus(cause instanceof PurchaseApiError ? cause.status : null);
      setError(
        cause instanceof Error ? cause.message : "Không thể tải chi tiết.",
      );
    } finally {
      setOpening(false);
    }
  };
  return (
    <main className="mx-auto max-w-7xl space-y-6 p-5 md:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-violet-700">
            {meta.code}
          </div>
          <h1 className="text-3xl font-bold tracking-tight">{meta.title}</h1>
          <p className="mt-2 text-muted-foreground">
            ERPNext native fields · dữ liệu live qua Letron Gateway.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>Tạo mới</Button>
      </div>
      {kind === "request" ? (
        <section
          aria-label="Các Purchase orchestration cần xử lý"
          className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-amber-950 shadow-sm"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-semibold">Cần xử lý</h2>
              <p className="text-sm text-amber-900/80">
                Các Material Request đã tạo nhưng RFQ chưa hoàn tất.
              </p>
            </div>
            <Button
              variant="outline"
              disabled={activeBusy}
              onClick={() => void loadActive()}
            >
              {activeBusy ? "Đang làm mới..." : "Làm mới"}
            </Button>
          </div>
          {activeError ? (
            <p className="mt-3 rounded-md bg-red-100 p-3 text-sm text-red-800">
              {activeError}
            </p>
          ) : null}
          {!activeBusy && !activeError && !activeOrchestrations.length ? (
            <p className="mt-3 text-sm text-amber-900/70">
              Không có orchestration nào cần xử lý.
            </p>
          ) : null}
          <div className="mt-3 space-y-3">
            {activeOrchestrations.map((item) => (
              <div
                className="flex flex-col gap-3 rounded-lg border border-amber-200 bg-background p-4 sm:flex-row sm:items-center sm:justify-between"
                key={item.id}
              >
                <div className="text-sm">
                  <p className="font-medium">
                    {item.material_request_name ??
                      "Material Request đang xử lý"}
                  </p>
                  <p className="text-muted-foreground">
                    {item.status === "partial_failure"
                      ? "MR đã tạo, RFQ chưa tạo được"
                      : item.status === "rfq_created"
                        ? "RFQ đã tạo, đang tạo Lark Approval"
                        : item.status === "started"
                          ? "Đang xử lý"
                          : "Cần kiểm tra lại"}
                    {item.retry_count ? ` · ${item.retry_count} lần retry` : ""}
                  </p>
                  {item.error ? (
                    <p className="mt-1 text-red-700">{item.error}</p>
                  ) : null}
                </div>
                <Button
                  disabled={
                    Boolean(retryingActiveId) ||
                    (!item.material_request_name && item.status !== "started")
                  }
                  onClick={() => void retryActive(item.id)}
                >
                  {retryingActiveId === item.id
                    ? "Đang tiếp tục luồng..."
                    : "Tiếp tục luồng"}
                </Button>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      {toast ? (
        <div
          role="status"
          aria-live="polite"
          className={`fixed right-5 top-5 z-[70] max-w-sm rounded-lg border p-4 shadow-lg ${toast.tone === "success" ? "bg-emerald-50 text-emerald-800" : toast.tone === "warning" ? "bg-amber-50 text-amber-900" : "bg-red-50 text-red-800"}`}
        >
          <div className="flex items-start gap-3">
            <span>{toast.message}</span>
            <button
              type="button"
              aria-label="Đóng thông báo"
              onClick={() => setToast(null)}
            >
              ×
            </button>
          </div>
        </div>
      ) : null}
      <section className="rounded-xl border bg-card shadow-sm">
        <div className="flex flex-col gap-4 border-b p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="font-semibold">Danh sách {meta.title}</h2>
            <p className="text-sm text-muted-foreground">
              {filtered.length} bản ghi · trang {page}
            </p>
          </div>
          <Input
            className="sm:max-w-xs"
            placeholder="Tìm kiếm..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <div className="flex flex-wrap gap-2 border-b p-5">
          <select
            className="h-10 rounded-md border bg-background px-3 text-sm"
            value={filter.field}
            onChange={(event) =>
              setFilter({ field: event.target.value, value: filter.value })
            }
            aria-label="Trường lọc"
          >
            {filterFields[kind].map((item) => (
              <option key={item.field} value={item.field}>
                {item.label}
              </option>
            ))}
          </select>
          <Input
            className="max-w-xs"
            placeholder="Giá trị lọc native..."
            value={filter.value}
            onChange={(event) =>
              setFilter((current) => ({
                ...current,
                value: event.target.value,
              }))
            }
          />
          <select
            className="h-10 rounded-md border bg-background px-3 text-sm"
            value={sort}
            onChange={(event) => {
              setSort(event.target.value);
              setPage(1);
            }}
            aria-label="Sắp xếp"
          >
            <option value="modified desc">Mới cập nhật</option>
            <option value="modified asc">Cũ nhất</option>
            <option value="name asc">Tên A → Z</option>
            <option value="name desc">Tên Z → A</option>
          </select>
          <Button type="button" onClick={applyFilter}>
            Áp dụng
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setQuery("");
              setFilter({ field: filterFields[kind][0].field, value: "" });
              setSort("modified desc");
              setPage(1);
            }}
          >
            Xóa lọc
          </Button>
        </div>
        {busy ? (
          <div className="p-12 text-center text-sm text-muted-foreground">
            Đang tải dữ liệu...
          </div>
        ) : error ? (
          <div className="space-y-3 p-8 text-sm text-destructive">
            <p>{error}</p>
            {errorStatus === 401 ? (
              <a
                className="block w-fit underline"
                href="/api/auth/login"
                target="_top"
                rel="noopener"
                onClick={(event) => {
                  event.preventDefault();
                  window.top?.location.assign(
                    larkLoginHref(
                      `${window.location.pathname}${window.location.search}`,
                    ),
                  );
                }}
              >
                Đăng nhập lại bằng Lark
              </a>
            ) : null}
            <Button variant="outline" onClick={() => void load(page)}>
              Thử lại
            </Button>
          </div>
        ) : filtered.length ? (
          <div className="overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-muted/50">
                <tr>
                  {columns.map(({ field, label }) => (
                    <th className="whitespace-nowrap px-4 py-3" key={field}>
                      {label}
                    </th>
                  ))}
                  <th className="px-4 py-3">Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row, index) => (
                  <tr className="border-t" key={String(row.name ?? index)}>
                    {columns.map(({ field }) => (
                      <td className="whitespace-nowrap px-4 py-3" key={field}>
                        {displayCell(field, row[field])}
                      </td>
                    ))}
                    <td className="px-4 py-3">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={opening}
                        onClick={() => void openDetail(row)}
                      >
                        Chi tiết / Sửa
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-12 text-center text-sm text-muted-foreground">
            Chưa có dữ liệu.
          </div>
        )}
        <div className="flex justify-end gap-2 border-t p-4">
          <Button
            variant="outline"
            disabled={page === 1 || busy}
            onClick={() => void load(page - 1)}
          >
            Trang trước
          </Button>
          <Button
            variant="outline"
            disabled={!hasNext || busy}
            onClick={() => void load(page + 1)}
          >
            Trang sau
          </Button>
        </div>
      </section>
      {creating || editing ? (
        <ResourceModal
          kind={kind}
          initial={editing ?? undefined}
          onClose={() => {
            setCreating(false);
            setEditing(null);
            setOrchestrationId(null);
          }}
          onSaved={() => {
            setCreating(false);
            setEditing(null);
            setOrchestrationId(null);
            void load(page);
            void loadActive();
            setToast({
              message: `Đã lưu ${meta.title} thành công.`,
              tone: "success",
            });
          }}
          onToast={setToast}
          onOrchestrationChanged={() => void loadActive()}
        />
      ) : null}
    </main>
  );
}

function ResourceModal({
  kind,
  initial,
  onClose,
  onSaved,
  onOrchestrationChanged,
  onToast,
}: Readonly<{
  kind: Kind;
  initial?: Row;
  onClose: () => void;
  onSaved: () => void;
  onOrchestrationChanged: () => void;
  onToast: (toast: Toast) => void;
}>) {
  const meta = config[kind];
  const [values, setValues] = useState<Row>(() => initialValues(kind, initial));
  const [items, setItems] = useState<ItemRow[]>(() => {
    const source = Array.isArray(initial?.items)
      ? (initial.items as Row[])
      : [];
    return source.length
      ? source.map((item) => ({
          item_code: text(item.item_code) === "—" ? "" : text(item.item_code),
          qty: Number(item.qty) || 1,
          schedule_date: dateValue(item.schedule_date),
          warehouse: text(item.warehouse) === "—" ? "" : text(item.warehouse),
          uom: text(item.uom) === "—" ? "" : text(item.uom),
          stock_uom: text(item.stock_uom) === "—" ? "" : text(item.stock_uom),
          conversion_factor: Number(item.conversion_factor) || 1,
          rate: Number(item.rate ?? item.price_list_rate) || 0,
        }))
      : [
          {
            item_code: "",
            qty: 1,
            schedule_date: dateValue(),
            warehouse: "",
            uom: "",
            stock_uom: "",
            conversion_factor: 1,
            rate: 0,
          },
        ];
  });
  const [suppliers, setSuppliers] = useState<string[]>(() =>
    Array.isArray(initial?.suppliers)
      ? (initial.suppliers as Row[])
          .map((supplier) => text(supplier.supplier ?? supplier.name))
          .filter((supplier) => supplier !== "—")
      : [],
  );
  const [options, setOptions] = useState<Row[]>([]);
  const [linkOptions, setLinkOptions] = useState<{
    contacts: Row[];
    addresses: Row[];
    suppliers: Row[];
  }>({ contacts: [], addresses: [], suppliers: [] });
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [attachment, setAttachment] = useState<File | null>(null);
  const [createdName, setCreatedName] = useState<string | null>(null);
  const [orchestrationId, setOrchestrationId] = useState<string | null>(null);
  const [orchestrationStatus, setOrchestrationStatus] = useState<
    ActiveOrchestration["status"] | null
  >(null);
  const [requestIdempotencyKey] = useState(() => crypto.randomUUID());
  useEffect(() => {
    if (kind !== "request") return;
    void Promise.all([
      api("items?limit_page_length=100"),
      api("suppliers?limit_page_length=100"),
    ])
      .then(([itemResult, supplierResult]) => {
        setOptions(Array.isArray(itemResult) ? (itemResult as Row[]) : []);
        setLinkOptions((current) => ({
          ...current,
          suppliers: Array.isArray(supplierResult)
            ? (supplierResult as Row[])
            : [],
        }));
      })
      .catch(() => undefined);
  }, [kind]);
  useEffect(() => {
    if (kind !== "supplier") return;
    void Promise.all([
      api("contacts?limit_page_length=100"),
      api("addresses?limit_page_length=100"),
    ])
      .then(([contacts, addresses]) =>
        setLinkOptions((current) => ({
          ...current,
          contacts: Array.isArray(contacts) ? (contacts as Row[]) : [],
          addresses: Array.isArray(addresses) ? (addresses as Row[]) : [],
        })),
      )
      .catch(() => undefined);
  }, [kind]);
  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (dirty) event.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);
  const close = () => {
    if (!dirty || window.confirm("Form chưa lưu. Bạn có chắc muốn đóng không?"))
      onClose();
  };
  const set = (name: string, value: unknown) => {
    setDirty(true);
    setValues((current) => ({ ...current, [name]: value }));
  };
  const setItem = (index: number, patch: Partial<ItemRow>) => {
    setDirty(true);
    setItems((current) =>
      current.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...patch } : item,
      ),
    );
  };
  const buildItems = () =>
    items
      .filter((item) => item.item_code.trim())
      .map((item) => ({
        item_code: item.item_code.trim(),
        qty: Number(item.qty),
        schedule_date: item.schedule_date,
        warehouse: item.warehouse || undefined,
        uom: item.uom || item.stock_uom || undefined,
        stock_uom: item.stock_uom || item.uom || undefined,
        conversion_factor: Number(item.conversion_factor) || 1,
        rate: Number(item.rate) || 0,
      }));
  async function uploadAttachment(name: string) {
    if (!attachment) return;
    const body = new FormData();
    body.append("file", attachment);
    const metadata = new URLSearchParams({
      attached_to_doctype: ATTACHMENT_DOCTYPES[kind],
      attached_to_name: name,
      is_private: "true",
    });
    await api(`attachments?${metadata.toString()}`, { method: "POST", body });
  }
  async function retryRfq() {
    if (!orchestrationId || saving) return;
    setSaving(true);
    setError(null);
    try {
      const result = (await api(
        `requests/orchestrations/${encodeURIComponent(orchestrationId)}/retry-rfq`,
        { method: "POST" },
      )) as Row;
      if (result.status !== "waiting_supplier_quotes") {
        setOrchestrationStatus(result.status as ActiveOrchestration["status"]);
        setError(String(result.error ?? "Không thể tạo RFQ."));
        onToast({
          message: String(result.error ?? "Không thể tạo RFQ."),
          tone: "error",
        });
        return;
      }
      setOrchestrationStatus(result.status as ActiveOrchestration["status"]);
      const materialRequestName = String(result.material_request_name ?? "");
      if (attachment && materialRequestName)
        await uploadAttachment(materialRequestName);
      setDirty(false);
      onToast({ message: "Đã retry RFQ thành công.", tone: "success" });
      onSaved();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Không thể retry RFQ.");
    } finally {
      setSaving(false);
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    if (createdName) {
      setSaving(true);
      setError(null);
      try {
        await uploadAttachment(createdName);
        onSaved();
      } catch (cause) {
        setError(
          cause instanceof Error
            ? cause.message
            : "Không thể upload attachment.",
        );
      } finally {
        setSaving(false);
      }
      return;
    }
    setError(null);
    setStatus(null);
    const missing = meta.fields.find(
      (field) => field.required && !String(values[field.name] ?? "").trim(),
    );
    if (missing) {
      setError(`${missing.label} là bắt buộc.`);
      return;
    }
    if (
      kind === "supplier" &&
      !Boolean(initial?.disabled) &&
      Boolean(values.disabled) &&
      !window.confirm(
        "Supplier sẽ bị vô hiệu hóa và không dùng được cho RFQ. Tiếp tục?",
      )
    )
      return;
    const requestItems = kind === "request" ? buildItems() : [];
    if (kind === "request" && !requestItems.length) {
      setError("Material Request cần ít nhất một Item.");
      return;
    }
    if (kind === "request" && !suppliers.length) {
      setError("Cần chọn ít nhất một Supplier để tạo đồng thời RFQ.");
      return;
    }
    if (
      requestItems.some((item) => !Number.isFinite(item.qty) || item.qty <= 0)
    ) {
      setError("Số lượng Item phải lớn hơn 0.");
      return;
    }
    if (
      kind === "request" &&
      items.some((item) => {
        if (!item.item_code.trim()) return false;
        const selected = options.find(
          (row) => text(row.name ?? row.item_code) === item.item_code,
        );
        return selected?.is_stock_item !== false && !item.warehouse.trim();
      })
    ) {
      setError("Kho là bắt buộc cho Item tồn kho.");
      return;
    }
    setSaving(true);
    try {
      const payload: Row = Object.fromEntries(
        Object.entries(values).filter(([, value]) => value !== ""),
      );
      if (kind === "request") payload.items = requestItems;
      if (kind === "supplier" && !initial) payload.address_contacts = [];
      if (kind === "request" && !initial) {
        const result = (await api("requests/create", {
          method: "POST",
          headers: { "X-Idempotency-Key": requestIdempotencyKey },
          body: JSON.stringify({ material_request: payload, suppliers }),
        })) as Row;
        if (result.status !== "waiting_supplier_quotes") {
          setOrchestrationId(String(result.id));
          setOrchestrationStatus(
            result.status as ActiveOrchestration["status"],
          );
          onOrchestrationChanged();
          if (result.status === "partial_failure") {
            setStatus(
              "Đã tạo Material Request nhưng RFQ chưa tạo được. Hãy retry RFQ.",
            );
            setError(String(result.error ?? "RFQ chưa được tạo."));
          } else if (result.status === "started") {
            setStatus(
              "Yêu cầu đang được xử lý. Giữ nguyên context này và kiểm tra lại trạng thái trước khi thử lại.",
            );
          } else {
            setStatus("Không thể hoàn tất Material Request và RFQ.");
            setError(String(result.error ?? "Purchase orchestration failed."));
          }
          return;
        }
        const materialRequestName = String(result.material_request_name ?? "");
        if (attachment && materialRequestName) {
          try {
            await uploadAttachment(materialRequestName);
          } catch (cause) {
            setCreatedName(materialRequestName);
            setStatus(
              "Đã tạo Material Request và RFQ; attachment chưa upload được. Có thể thử lại.",
            );
            throw cause;
          }
        }
        setStatus(
          attachment
            ? "Đã tạo Material Request, RFQ và attachment thành công."
            : "Đã tạo Material Request và RFQ thành công.",
        );
        onToast({
          message: attachment
            ? "Đã tạo Material Request, RFQ và attachment."
            : "Đã tạo Material Request và RFQ.",
          tone: "success",
        });
        setDirty(false);
        onSaved();
        return;
      }
      const saved = await api(
        `${meta.endpoint}${initial?.name ? `/${encodeURIComponent(String(initial.name))}` : ""}`,
        { method: initial ? "PUT" : "POST", body: JSON.stringify(payload) },
      );
      const savedName = String((saved as Row).name ?? initial?.name ?? "");
      if (attachment && savedName) await uploadAttachment(savedName);
      onSaved();
      onToast({ message: `Đã lưu ${meta.title} thành công.`, tone: "success" });
      setDirty(false);
    } catch (cause) {
      if (!initial && kind !== "request") {
        const message =
          cause instanceof Error
            ? cause.message
            : "Không thể upload attachment.";
        setError(message);
      }
      setError(
        cause instanceof Error ? cause.message : "Không thể lưu bản ghi.",
      );
      onToast({
        message:
          cause instanceof Error ? cause.message : "Không thể lưu bản ghi.",
        tone: "error",
      });
    } finally {
      setSaving(false);
    }
  }
  async function lifecycle(action: "submit" | "cancel") {
    if (
      !initial?.name ||
      saving ||
      !window.confirm(
        action === "submit"
          ? "Submit Material Request này?"
          : "Cancel Material Request này?",
      )
    )
      return;
    setSaving(true);
    setError(null);
    try {
      await api(
        `material-requests/${encodeURIComponent(String(initial.name))}/${action}`,
        { method: "POST" },
      );
      setStatus(
        action === "submit"
          ? "Đã submit Material Request."
          : "Đã cancel Material Request.",
      );
      onToast({
        message:
          action === "submit"
            ? "Đã submit Material Request."
            : "Đã cancel Material Request.",
        tone: "success",
      });
      setDirty(false);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Không thể cập nhật trạng thái.",
      );
    } finally {
      setSaving(false);
    }
  }
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
    >
      <form
        className="max-h-[90vh] w-full max-w-4xl overflow-auto rounded-xl border bg-background p-6 shadow-xl"
        onSubmit={submit}
      >
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold">
              {initial ? "Chi tiết / Sửa" : "Tạo"} {meta.title}
            </h2>
            <p className="text-sm text-muted-foreground">
              Các trường có * là bắt buộc theo ERPNext.
            </p>
          </div>
          <Button type="button" variant="ghost" onClick={close}>
            Đóng
          </Button>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {meta.fields.map((field) => (
            <div className="space-y-2" key={field.name}>
              <Label htmlFor={`purchase-${field.name}`}>
                {field.label}
                {field.required ? " *" : ""}
              </Label>
              {field.type === "boolean" ? (
                <input
                  className="h-4 w-4"
                  id={`purchase-${field.name}`}
                  type="checkbox"
                  checked={Boolean(values[field.name])}
                  onChange={(event) => set(field.name, event.target.checked)}
                />
              ) : field.type === "select" ? (
                <select
                  className="flex h-10 w-full rounded-md border bg-background px-3 text-sm"
                  id={`purchase-${field.name}`}
                  value={String(values[field.name] ?? "")}
                  onChange={(event) => set(field.name, event.target.value)}
                >
                  <option value="">Chọn...</option>
                  {field.options?.map((option) => (
                    <option key={option}>{option}</option>
                  ))}
                </select>
              ) : field.type === "link" ? (
                <select
                  className="flex h-10 w-full rounded-md border bg-background px-3 text-sm"
                  id={`purchase-${field.name}`}
                  value={String(values[field.name] ?? "")}
                  onChange={(event) => set(field.name, event.target.value)}
                >
                  <option value="">Chọn...</option>
                  {(field.link ? linkOptions[field.link] : []).map((option) => (
                    <option key={text(option.name)} value={text(option.name)}>
                      {text(option.name)}
                    </option>
                  ))}
                </select>
              ) : (
                <Input
                  id={`purchase-${field.name}`}
                  autoFocus={field.name === meta.fields[0]?.name}
                  required={field.required}
                  type={field.type ?? "text"}
                  value={String(values[field.name] ?? "")}
                  onChange={(event) => set(field.name, event.target.value)}
                />
              )}
            </div>
          ))}
        </div>
        {kind === "request" ? (
          <p className="mt-4 rounded-md bg-muted/40 p-3 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Người tạo:</span>{" "}
            {initial?.owner
              ? text(initial.owner)
              : "ERPNext sẽ tự gán sau khi lưu"}
          </p>
        ) : null}
        {kind === "supplier" ? (
          <ContactAddressPanel
            supplier={String(initial?.name ?? values.supplier_name ?? "")}
            onToast={onToast}
            onPrimaryChange={(field, value) => set(field, value)}
          />
        ) : null}
        {kind === "request" ? (
          <RequestItems
            items={items}
            options={options}
            onAdd={() => {
              setDirty(true);
              setItems((current) => [
                ...current,
                {
                  item_code: "",
                  qty: 1,
                  schedule_date: dateValue(values.schedule_date),
                  warehouse: "",
                  uom: "",
                  stock_uom: "",
                  conversion_factor: 1,
                  rate: 0,
                },
              ]);
            }}
            onRemove={(index) => {
              setDirty(true);
              setItems((current) =>
                current.length > 1
                  ? current.filter((_, itemIndex) => itemIndex !== index)
                  : current,
              );
            }}
            onChange={setItem}
            suppliers={suppliers}
            supplierOptions={linkOptions.suppliers}
            setSuppliers={(next) => {
              setDirty(true);
              setSuppliers(next);
            }}
          />
        ) : null}
        <div className="mt-6 space-y-2 rounded-lg border bg-muted/30 p-4">
          <Label htmlFor="purchase-attachment">Tệp đính kèm</Label>
          <Input
            id="purchase-attachment"
            type="file"
            onChange={(event) => {
              setDirty(true);
              setAttachment(event.target.files?.[0] ?? null);
            }}
          />
          <p className="text-xs text-muted-foreground">
            Tệp sẽ được lưu private và gắn vào bản ghi sau khi lưu thành công.
          </p>
        </div>
        {error ? (
          <p className="mt-5 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </p>
        ) : null}
        {status ? (
          <p className="mt-5 rounded-md bg-emerald-50 p-3 text-sm text-emerald-700">
            {status}
          </p>
        ) : null}
        {orchestrationId &&
        orchestrationStatus !== "waiting_supplier_quotes" ? (
          <div className="mt-3 flex justify-end">
            <Button
              type="button"
              variant="outline"
              disabled={saving}
              onClick={() => void retryRfq()}
            >
              {saving ? "Đang tiếp tục luồng..." : "Tiếp tục luồng"}
            </Button>
          </div>
        ) : null}
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" onClick={close}>
            Hủy
          </Button>
          {kind === "request" && initial?.name ? (
            <Button
              type="button"
              variant="outline"
              disabled={saving}
              onClick={() =>
                void lifecycle(
                  Number(initial.docstatus) === 1 ? "cancel" : "submit",
                )
              }
            >
              {Number(initial.docstatus) === 1 ? "Cancel" : "Submit"}
            </Button>
          ) : null}
          <Button disabled={saving} type="submit">
            {saving ? "Đang lưu..." : initial ? "Lưu thay đổi" : "Tạo bản ghi"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function RequestItems({
  items,
  options,
  supplierOptions,
  onAdd,
  onRemove,
  onChange,
  suppliers,
  setSuppliers,
}: Readonly<{
  items: ItemRow[];
  options: Row[];
  supplierOptions: Row[];
  onAdd: () => void;
  onRemove: (index: number) => void;
  onChange: (index: number, patch: Partial<ItemRow>) => void;
  suppliers: string[];
  setSuppliers: (next: string[]) => void;
}>) {
  const [supplier, setSupplier] = useState("");
  const totalQuantity = items.reduce(
    (sum, item) => sum + (Number(item.qty) || 0),
    0,
  );
  return (
    <>
      <div className="mt-6 flex items-center justify-between">
        <div>
          <h3 className="font-semibold">Items *</h3>
          <p className="text-xs text-muted-foreground">
            Tổng số lượng: {totalQuantity}
          </p>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={onAdd}>
          Thêm dòng
        </Button>
      </div>
      <div className="space-y-3">
        {items.map((item, index) => (
          <div
            className="grid gap-2 rounded-lg border p-3 md:grid-cols-[1fr_100px_120px_1fr_1fr_auto]"
            key={index}
          >
            <Input
              aria-label="Item"
              role="combobox"
              aria-autocomplete="list"
              list={`purchase-items-${index}`}
              placeholder="Nhập mã hoặc tên Item..."
              value={item.item_code}
              onChange={(event) => {
                const selected =
                  options.find(
                    (row) =>
                      text(row.name ?? row.item_code) === event.target.value,
                  ) ??
                  options.find(
                    (row) => text(row.item_name) === event.target.value,
                  );
                const stockUom = text(selected?.stock_uom);
                const purchaseUom = text(selected?.purchase_uom);
                onChange(index, {
                  item_code: event.target.value,
                  stock_uom: stockUom === "—" ? "" : stockUom,
                  uom:
                    purchaseUom === "—"
                      ? stockUom === "—"
                        ? ""
                        : stockUom
                      : purchaseUom,
                });
              }}
            />
            <datalist id={`purchase-items-${index}`}>
              {options.map((row) => (
                <option
                  key={text(row.name ?? row.item_code)}
                  value={text(row.name ?? row.item_code)}
                >
                  {text(row.item_name ?? row.item_code)}
                </option>
              ))}
            </datalist>
            <Input
              aria-label="Số lượng"
              type="number"
              min="0.001"
              step="any"
              value={String(item.qty)}
              onChange={(event) => onChange(index, { qty: event.target.value })}
            />
            <Input
              aria-label="Đơn giá"
              type="number"
              min="0"
              step="any"
              value={String(item.rate)}
              onChange={(event) =>
                onChange(index, { rate: event.target.value })
              }
            />
            <Input
              aria-label="Ngày cần hàng"
              type="date"
              value={item.schedule_date}
              onChange={(event) =>
                onChange(index, { schedule_date: event.target.value })
              }
            />
            <Input
              aria-label="Kho"
              placeholder="Warehouse"
              required={
                options.find(
                  (row) => text(row.name ?? row.item_code) === item.item_code,
                )?.is_stock_item !== false
              }
              value={item.warehouse}
              onChange={(event) =>
                onChange(index, { warehouse: event.target.value })
              }
            />
            <Button
              type="button"
              variant="ghost"
              onClick={() => onRemove(index)}
            >
              ×
            </Button>
          </div>
        ))}
      </div>
      <div className="mt-6 space-y-2 rounded-lg border p-4">
        <Label>Supplier cho RFQ (có thể chọn nhiều) *</Label>
        <div className="flex gap-2">
          <select
            className="h-10 flex-1 rounded-md border bg-background px-3 text-sm"
            value={supplier}
            onChange={(event) => setSupplier(event.target.value)}
          >
            <option value="">Chọn Supplier...</option>
            {supplierOptions.map((row) => (
              <option key={text(row.name)} value={text(row.name)}>
                {text(row.supplier_name ?? row.name)}
              </option>
            ))}
          </select>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              if (supplier && !suppliers.includes(supplier))
                setSuppliers([...suppliers, supplier]);
              setSupplier("");
            }}
          >
            Thêm
          </Button>
        </div>
        {suppliers.length ? (
          <div className="flex flex-wrap gap-2">
            {suppliers.map((value) => (
              <button
                className="rounded-full bg-violet-100 px-3 py-1 text-xs"
                type="button"
                key={value}
                onClick={() =>
                  setSuppliers(suppliers.filter((item) => item !== value))
                }
              >
                {value} ×
              </button>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">Chưa chọn Supplier.</p>
        )}
      </div>
    </>
  );
}

function ContactAddressPanel({
  supplier,
  onToast,
  onPrimaryChange,
}: Readonly<{
  supplier: string;
  onToast: (toast: Toast) => void;
  onPrimaryChange: (field: string, value: string) => void;
}>) {
  const [open, setOpen] = useState(false);
  const [records, setRecords] = useState<{ contacts: Row[]; addresses: Row[] }>(
    { contacts: [], addresses: [] },
  );
  const [editing, setEditing] = useState<{
    kind: "contacts" | "addresses";
    row?: Row;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const refresh = useCallback(async () => {
    if (!supplier) return;
    setLoading(true);
    try {
      const [contacts, addresses] = await Promise.all([
        api("contacts?limit_page_length=100"),
        api("addresses?limit_page_length=100"),
      ]);
      const linked = (value: unknown) =>
        Array.isArray(value) &&
        value.some((link) => {
          const item = link as Row;
          return (
            item.link_doctype === "Supplier" &&
            String(item.link_name) === supplier
          );
        });
      const readDetails = async (
        kind: "contacts" | "addresses",
        value: unknown,
      ) => {
        const list = Array.isArray(value) ? (value as Row[]) : [];
        const details = await Promise.all(
          list.map(async (row) => {
            if (!row.name) return row;
            try {
              return (await api(
                `${kind}/${encodeURIComponent(String(row.name))}`,
              )) as Row;
            } catch {
              return row;
            }
          }),
        );
        return details.filter((row) => linked(row.links));
      };
      const [linkedContacts, linkedAddresses] = await Promise.all([
        readDetails("contacts", contacts),
        readDetails("addresses", addresses),
      ]);
      setRecords({ contacts: linkedContacts, addresses: linkedAddresses });
    } catch (cause) {
      onToast({
        message:
          cause instanceof Error
            ? cause.message
            : "Không thể làm mới Contact/Address.",
        tone: "error",
      });
    } finally {
      setLoading(false);
    }
  }, [onToast, supplier]);
  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);
  async function setPrimary(
    field: "supplier_primary_contact" | "supplier_primary_address",
    value: string,
  ) {
    try {
      await api(`suppliers/${encodeURIComponent(supplier)}`, {
        method: "PUT",
        body: JSON.stringify({ [field]: value }),
      });
      onPrimaryChange(field, value);
      onToast({ message: "Đã cập nhật liên kết chính.", tone: "success" });
    } catch (cause) {
      onToast({
        message:
          cause instanceof Error
            ? cause.message
            : "Không thể cập nhật liên kết chính.",
        tone: "error",
      });
    }
  }
  return (
    <div className="mt-6 rounded-lg border bg-muted/30 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold">Contact / Address</h3>
          <p className="text-xs text-muted-foreground">
            Tạo trong cùng context Supplier.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => void refresh()}
            disabled={loading}
          >
            {loading ? "Đang tải..." : "Làm mới"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!supplier}
            onClick={() => {
              setEditing(null);
              setOpen(true);
            }}
          >
            {supplier ? "Thêm Contact / Address" : "Lưu Supplier trước"}
          </Button>
        </div>
      </div>
      {!supplier ? (
        <p className="mt-2 text-xs text-muted-foreground">
          Contact và Address cần Supplier đã tồn tại để tạo liên kết.
        </p>
      ) : null}
      {supplier ? (
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {(["contacts", "addresses"] as const).map((recordKind) => (
            <div key={recordKind} className="rounded border bg-background p-3">
              <p className="mb-2 text-sm font-medium">
                {recordKind === "contacts" ? "Contact" : "Address"}
              </p>
              {records[recordKind].length ? (
                records[recordKind].map((row) => (
                  <div
                    className="flex items-center justify-between gap-2 border-t py-2 text-sm"
                    key={text(row.name)}
                  >
                    <span>
                      {text(row.name ?? row.first_name ?? row.address_title)}
                    </span>
                    <div className="flex gap-1">
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          setPrimary(
                            recordKind === "contacts"
                              ? "supplier_primary_contact"
                              : "supplier_primary_address",
                            text(row.name),
                          )
                        }
                      >
                        Chọn chính
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setEditing({ kind: recordKind, row });
                          setOpen(true);
                        }}
                      >
                        Sửa
                      </Button>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-xs text-muted-foreground">
                  Chưa có bản ghi liên kết.
                </p>
              )}
            </div>
          ))}
        </div>
      ) : null}
      {open ? (
        <ContactAddressModal
          supplier={supplier}
          initial={editing?.row}
          kind={editing?.kind}
          onClose={() => {
            setOpen(false);
            setEditing(null);
          }}
          onSaved={(saved) => {
            setOpen(false);
            setEditing(null);
            if (saved?.name) {
              setRecords((current) => ({
                ...current,
                [editing?.kind ?? "contacts"]: [
                  ...current[editing?.kind ?? "contacts"],
                  saved,
                ],
              }));
              const primaryField =
                (editing?.kind ?? "contacts") === "contacts"
                  ? "supplier_primary_contact"
                  : "supplier_primary_address";
              void setPrimary(primaryField, String(saved.name));
            }
            if (!saved?.name) void refresh();
            onToast({ message: "Đã lưu Contact/Address.", tone: "success" });
          }}
        />
      ) : null}
    </div>
  );
}
function ContactAddressModal({
  supplier,
  onClose,
  initial,
  kind: initialKind,
  onSaved,
}: Readonly<{
  supplier: string;
  onClose: () => void;
  onSaved: (saved?: Row) => void;
  initial?: Row;
  kind?: "contacts" | "addresses";
}>) {
  const [kind, setKind] = useState<"contacts" | "addresses">(
    initialKind ?? "contacts",
  );
  const [values, setValues] = useState<Row>({
    first_name: "",
    address_title: "",
    address_type: "Billing",
    address_line1: "",
    city: "",
    country: "Vietnam",
    ...initial,
  });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  async function save() {
    if (saving) return;
    const requiredValues =
      kind === "contacts"
        ? [values.first_name]
        : [
            values.address_title,
            values.address_line1,
            values.city,
            values.country,
          ];
    if (requiredValues.some((value) => !String(value ?? "").trim())) {
      setError("Vui lòng điền đủ trường bắt buộc.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload =
        kind === "contacts"
          ? {
              first_name: values.first_name,
              links: [{ link_doctype: "Supplier", link_name: supplier }],
            }
          : {
              address_title: values.address_title,
              address_type: values.address_type,
              address_line1: values.address_line1,
              city: values.city,
              country: values.country,
              links: [{ link_doctype: "Supplier", link_name: supplier }],
            };
      const saved = await api(
        `${kind}${initial?.name ? `/${encodeURIComponent(String(initial.name))}` : ""}`,
        { method: initial ? "PUT" : "POST", body: JSON.stringify(payload) },
      );
      onSaved(saved as Row);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Không thể lưu.");
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="mt-4 rounded-lg border bg-background p-4">
      <div className="space-y-3">
        <select
          className="h-10 rounded-md border bg-background px-3 text-sm"
          value={kind}
          onChange={(event) => setKind(event.target.value as typeof kind)}
        >
          <option value="contacts">Contact</option>
          <option value="addresses">Address</option>
        </select>
        {kind === "contacts" ? (
          <Input
            required
            placeholder="Tên Contact"
            value={String(values.first_name)}
            onChange={(event) =>
              setValues({ ...values, first_name: event.target.value })
            }
          />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            <Input
              required
              placeholder="Tiêu đề Address"
              value={String(values.address_title)}
              onChange={(event) =>
                setValues({ ...values, address_title: event.target.value })
              }
            />
            <Input
              required
              placeholder="Địa chỉ"
              value={String(values.address_line1)}
              onChange={(event) =>
                setValues({ ...values, address_line1: event.target.value })
              }
            />
            <Input
              required
              placeholder="Thành phố"
              value={String(values.city)}
              onChange={(event) =>
                setValues({ ...values, city: event.target.value })
              }
            />
            <Input
              required
              placeholder="Quốc gia"
              value={String(values.country)}
              onChange={(event) =>
                setValues({ ...values, country: event.target.value })
              }
            />
          </div>
        )}
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <div className="flex gap-2">
          <Button disabled={saving} type="button" onClick={() => void save()}>
            {saving ? "Đang lưu..." : "Lưu"}
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Hủy
          </Button>
        </div>
      </div>
    </div>
  );
}

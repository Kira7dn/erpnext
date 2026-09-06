"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";

export interface BackupFileItem {
  key: string;
  filename: string;
  size: number;
  sizeHuman: string;
  role: string;
}

export interface BackupSetItem {
  timestamp: string;
  dateStr: string;
  isoDate: string;
  totalSize: number;
  totalSizeHuman: string;
  fileCount: number;
  isCompliant: boolean;
  files: BackupFileItem[];
}

export function BackupCard() {
  const [activeTab, setActiveTab] = useState<"erp">("erp");
  const [items, setItems] = useState<BackupSetItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | undefined>(undefined);
  const [hasMore, setHasMore] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(true);
  const [loadingMore, setLoadingMore] = useState<boolean>(false);
  const [isBackingUp, setIsBackingUp] = useState<boolean>(false);

  // Time filters
  const [quickFilter, setQuickFilter] = useState<"all" | "today" | "7days" | "30days">("all");
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");

  // Notification state
  const [statusMessage, setStatusMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  // Restore Modal State
  const [selectedBackup, setSelectedBackup] = useState<BackupSetItem | null>(null);
  const [restoreMode, setRestoreMode] = useState<"drill" | "live">("drill");
  const [isRestoring, setIsRestoring] = useState<boolean>(false);
  const [restoreResult, setRestoreResult] = useState<string | null>(null);

  const observerTarget = useRef<HTMLDivElement | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);

  // Calculate date range based on quick filters
  const applyQuickFilter = (type: "all" | "today" | "7days" | "30days") => {
    setQuickFilter(type);
    const now = new Date();
    const format = (d: Date) => d.toISOString().split("T")[0];

    if (type === "all") {
      setFromDate("");
      setToDate("");
    } else if (type === "today") {
      const todayStr = format(now);
      setFromDate(todayStr);
      setToDate(todayStr);
    } else if (type === "7days") {
      const past7 = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      setFromDate(format(past7));
      setToDate(format(now));
    } else if (type === "30days") {
      const past30 = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      setFromDate(format(past30));
      setToDate(format(now));
    }
  };

  // Refresh backups manually or after action
  const refreshBackups = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      params.set("limit", "7");
      if (fromDate) params.set("from", fromDate);
      if (toDate) params.set("to", toDate);

      const res = await fetch(`/api/backup/list?${params.toString()}`);
      if (!res.ok) throw new Error("Không thể tải danh sách backup");
      const data = await res.json();

      setItems(data.items || []);
      setNextCursor(data.nextCursor);
      setHasMore(Boolean(data.hasMore));
    } catch (err) {
      console.error(err);
      setStatusMessage({ text: "Lỗi kết nối khi tải danh sách từ AWS S3", type: "error" });
    } finally {
      setLoading(false);
    }
  }, [fromDate, toDate]);

  // Synchronize backups list whenever date filter changes
  useEffect(() => {
    let isCurrent = true;

    async function loadData() {
      try {
        const params = new URLSearchParams();
        params.set("limit", "7");
        if (fromDate) params.set("from", fromDate);
        if (toDate) params.set("to", toDate);

        const res = await fetch(`/api/backup/list?${params.toString()}`);
        if (!res.ok) throw new Error("Không thể tải danh sách backup");
        const data = await res.json();

        if (isCurrent) {
          setItems(data.items || []);
          setNextCursor(data.nextCursor);
          setHasMore(Boolean(data.hasMore));
        }
      } catch (err) {
        if (isCurrent) {
          console.error(err);
          setStatusMessage({ text: "Lỗi kết nối khi tải danh sách từ AWS S3", type: "error" });
        }
      } finally {
        if (isCurrent) {
          setLoading(false);
        }
      }
    }

    void loadData();

    return () => {
      isCurrent = false;
    };
  }, [fromDate, toDate]);

  // Infinite scroll load more
  const loadMore = useCallback(async () => {
    if (!hasMore || loadingMore || !nextCursor) return;
    try {
      setLoadingMore(true);
      const params = new URLSearchParams();
      params.set("limit", "6");
      params.set("cursor", nextCursor);
      if (fromDate) params.set("from", fromDate);
      if (toDate) params.set("to", toDate);

      const res = await fetch(`/api/backup/list?${params.toString()}`);
      if (!res.ok) throw new Error("Lỗi khi tải thêm bản ghi");
      const data = await res.json();

      setItems((prev) => [...prev, ...(data.items || [])]);
      setNextCursor(data.nextCursor);
      setHasMore(Boolean(data.hasMore));
    } catch (err) {
      console.error("Infinite scroll error:", err);
    } finally {
      setLoadingMore(false);
    }
  }, [hasMore, loadingMore, nextCursor, fromDate, toDate]);

  // IntersectionObserver for Infinite Scroll
  useEffect(() => {
    const target = observerTarget.current;
    if (!target) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMore && !loadingMore && !loading) {
          loadMore();
        }
      },
      {
        root: scrollContainerRef.current,
        threshold: 0.1,
      }
    );

    observer.observe(target);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, loading, loadMore]);

  // Trigger Backup
  const handleTriggerBackup = async () => {
    setIsBackingUp(true);
    setStatusMessage(null);
    try {
      const res = await fetch("/api/backup/create", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.details || data.error || "Sao lưu thất bại");

      setStatusMessage({
        text: "Tạo bản sao lưu ERP thành công và đã đồng bộ lên AWS S3!",
        type: "success",
      });
      // Refresh list
      await refreshBackups();
    } catch (err) {
      setStatusMessage({
        text: err instanceof Error ? err.message : "Kích hoạt sao lưu thất bại",
        type: "error",
      });
    } finally {
      setIsBackingUp(false);
    }
  };

  // Trigger Restore
  const handleConfirmRestore = async () => {
    if (!selectedBackup) return;
    setIsRestoring(true);
    setRestoreResult(null);
    try {
      const res = await fetch("/api/backup/restore", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          timestamp: selectedBackup.timestamp,
          mode: restoreMode,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.details || data.error || "Khôi phục thất bại");

      setRestoreResult(data.message || "Khôi phục thành công!");
    } catch (err) {
      setRestoreResult(err instanceof Error ? err.message : "Khôi phục thất bại");
    } finally {
      setIsRestoring(false);
    }
  };

  return (
    <div className="rounded-3xl border border-slate-200 bg-white shadow-xl shadow-slate-100 transition">
      {/* Card Header & Tabs */}
      <div className="border-b border-slate-100 p-6 sm:p-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3.5">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-200">
              <svg className="h-6 w-6 stroke-current stroke-2 fill-none" viewBox="0 0 24 24">
                <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242M12 12v9m-4-4 4-4 4 4" />
              </svg>
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-xl font-extrabold text-slate-900">Backup & Disaster Recovery</h3>
                <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-bold text-emerald-700 border border-emerald-200">
                  AWS S3 Active
                </span>
              </div>
              <p className="mt-0.5 text-xs text-slate-500">
                Tự động hóa sao lưu hằng ngày (01:00 AM) & lưu trữ đám mây 10 năm theo Luật Kế toán.
              </p>
            </div>
          </div>

          {/* Action: Trigger Backup Button */}
          <div className="flex items-center gap-2.5">
            <button
              onClick={() => refreshBackups()}
              disabled={loading || isBackingUp}
              title="Làm mới danh sách"
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition disabled:opacity-50"
            >
              <svg className={`h-4 w-4 fill-none stroke-current stroke-2 ${loading ? "animate-spin" : ""}`} viewBox="0 0 24 24">
                <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8m0 0V3m0 5h5M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16m0 0v5m0-5h-5" />
              </svg>
            </button>

            <button
              onClick={handleTriggerBackup}
              disabled={isBackingUp}
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2.5 text-xs font-bold text-white shadow-md shadow-blue-200 hover:from-blue-700 hover:to-indigo-700 transition disabled:opacity-50 cursor-pointer"
            >
              {isBackingUp ? (
                <>
                  <svg className="h-4 w-4 animate-spin fill-none stroke-current stroke-2" viewBox="0 0 24 24">
                    <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeLinecap="round" />
                  </svg>
                  <span>Đang sao lưu...</span>
                </>
              ) : (
                <>
                  <svg className="h-4 w-4 fill-none stroke-current stroke-2" viewBox="0 0 24 24">
                    <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242M12 12v9m-4-4 4-4 4 4" />
                  </svg>
                  <span>Sao lưu tự động ngay</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Status Toast Message */}
        {statusMessage && (
          <div
            className={`mt-4 flex items-center justify-between rounded-xl px-4 py-3 text-xs font-medium ${
              statusMessage.type === "success"
                ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                : "bg-rose-50 text-rose-800 border border-rose-200"
            }`}
          >
            <span>{statusMessage.text}</span>
            <button
              onClick={() => setStatusMessage(null)}
              className="text-slate-400 hover:text-slate-700 font-bold ml-3"
            >
              ✕
            </button>
          </div>
        )}

        {/* Tab Selection */}
        <div className="mt-6 flex items-center gap-2 border-b border-slate-100 pb-px">
          <button
            onClick={() => setActiveTab("erp")}
            className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs font-bold transition cursor-pointer ${
              activeTab === "erp"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-slate-500 hover:text-slate-900"
            }`}
          >
            <span className="h-2 w-2 rounded-full bg-blue-600" />
            <span>ERP Next (Production)</span>
            <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-bold text-blue-600">
              {items.length} bản sao lưu
            </span>
          </button>
        </div>
      </div>

      {/* Tab Content: ERP Backups */}
      <div className="p-6 sm:p-8">
        {/* Time Query & Filters Bar */}
        <div className="mb-6 flex flex-col gap-3.5 rounded-2xl bg-slate-50/80 p-4 border border-slate-100 sm:flex-row sm:items-center sm:justify-between">
          {/* Quick Date Filters */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-semibold text-slate-500 mr-1">Bộ lọc thời gian:</span>
            {(
              [
                { id: "all", label: "Tất cả" },
                { id: "today", label: "Hôm nay" },
                { id: "7days", label: "7 ngày qua" },
                { id: "30days", label: "30 ngày qua" },
              ] as const
            ).map((btn) => (
              <button
                key={btn.id}
                onClick={() => applyQuickFilter(btn.id)}
                className={`rounded-lg px-2.5 py-1 text-xs font-bold transition cursor-pointer ${
                  quickFilter === btn.id
                    ? "bg-blue-600 text-white shadow-sm"
                    : "bg-white text-slate-600 hover:bg-slate-200/80 border border-slate-200"
                }`}
              >
                {btn.label}
              </button>
            ))}
          </div>

          {/* Custom Date Range Picker */}
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={fromDate}
              onChange={(e) => {
                setFromDate(e.target.value);
                setQuickFilter("all");
              }}
              aria-label="Từ ngày"
              className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 focus:border-blue-500 focus:outline-none"
            />
            <span className="text-xs text-slate-400">→</span>
            <input
              type="date"
              value={toDate}
              onChange={(e) => {
                setToDate(e.target.value);
                setQuickFilter("all");
              }}
              aria-label="Đến ngày"
              className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 focus:border-blue-500 focus:outline-none"
            />
            {(fromDate || toDate) && (
              <button
                onClick={() => applyQuickFilter("all")}
                className="text-[11px] font-bold text-slate-400 hover:text-slate-700"
              >
                Đặt lại
              </button>
            )}
          </div>
        </div>

        {/* Backup List with Infinite Scroll Container */}
        <div
          ref={scrollContainerRef}
          className="max-h-[480px] overflow-y-auto pr-1.5 space-y-3 divide-y divide-slate-100"
        >
          {loading && items.length === 0 ? (
            // Skeleton Loader
            <div className="space-y-3">
              {[1, 2, 3].map((n) => (
                <div key={n} className="animate-pulse rounded-2xl bg-slate-50 p-4 border border-slate-100 flex items-center justify-between">
                  <div className="space-y-2">
                    <div className="h-4 w-44 bg-slate-200 rounded" />
                    <div className="h-3 w-64 bg-slate-100 rounded" />
                  </div>
                  <div className="h-8 w-24 bg-slate-200 rounded-xl" />
                </div>
              ))}
            </div>
          ) : items.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-200 p-10 text-center">
              <span className="text-3xl text-slate-300">📁</span>
              <p className="mt-2 text-sm font-bold text-slate-700">Không tìm thấy bản sao lưu nào</p>
              <p className="text-xs text-slate-400 mt-1">Không có bản backup khớp với khoảng thời gian đã chọn.</p>
            </div>
          ) : (
            items.map((item) => (
              <div
                key={item.timestamp}
                className="group flex flex-col gap-3 pt-3 first:pt-0 sm:flex-row sm:items-center sm:justify-between transition hover:bg-slate-50/50 p-3 rounded-2xl"
              >
                {/* Backup Metadata */}
                <div className="flex items-start gap-3.5">
                  <span className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600 font-mono text-xs font-bold border border-blue-100">
                    S3
                  </span>
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-bold text-slate-900 font-mono">
                        {item.dateStr}
                      </span>
                      <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">
                        {item.totalSizeHuman}
                      </span>
                      {item.isCompliant ? (
                        <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700 border border-emerald-200">
                          <i className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                          5/5 Thành phần
                        </span>
                      ) : (
                        <span className="rounded-md bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                          {item.fileCount} files
                        </span>
                      )}
                    </div>

                    {/* Component Chips */}
                    <div className="mt-1.5 flex flex-wrap gap-1.5 text-[10px] text-slate-500">
                      <span className="rounded bg-slate-100 px-1.5 py-0.5">Database (.sql.gz)</span>
                      <span className="rounded bg-slate-100 px-1.5 py-0.5">Config (Encryption Key)</span>
                      <span className="rounded bg-slate-100 px-1.5 py-0.5">Files VAT & Public</span>
                      <span className="rounded bg-slate-100 px-1.5 py-0.5">Manifest SHA-256</span>
                    </div>
                  </div>
                </div>

                {/* Restore Button */}
                <div className="flex shrink-0 items-center gap-2 sm:self-center">
                  <button
                    onClick={() => {
                      setSelectedBackup(item);
                      setRestoreResult(null);
                      setRestoreMode("drill");
                    }}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 shadow-xs hover:border-blue-300 hover:bg-blue-50/50 hover:text-blue-700 transition cursor-pointer"
                  >
                    <svg className="h-3.5 w-3.5 fill-none stroke-current stroke-2" viewBox="0 0 24 24">
                      <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8m0 0V3m0 5h-5M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16m0 0v5m0-5h5" />
                    </svg>
                    <span>Khôi phục</span>
                  </button>
                </div>
              </div>
            ))
          )}

          {/* Infinite Scroll Trigger Sentinel */}
          <div ref={observerTarget} className="py-4 text-center">
            {loadingMore && (
              <div className="inline-flex items-center gap-2 text-xs text-blue-600 font-semibold">
                <svg className="h-4 w-4 animate-spin fill-none stroke-current stroke-2" viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeLinecap="round" />
                </svg>
                <span>Đang tải thêm từ AWS S3...</span>
              </div>
            )}
            {!hasMore && items.length > 0 && (
              <p className="text-[11px] text-slate-400 font-medium">
                ✓ Đã tải hết toàn bộ {items.length} bản sao lưu trên AWS S3
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Restore Confirmation Modal */}
      {selectedBackup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg rounded-3xl bg-white p-6 sm:p-8 shadow-2xl border border-slate-100 transition animate-in fade-in zoom-in duration-150">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-50 text-amber-600 border border-amber-200">
                  <svg className="h-6 w-6 fill-none stroke-current stroke-2" viewBox="0 0 24 24">
                    <path d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
                  </svg>
                </span>
                <div>
                  <h4 className="text-lg font-bold text-slate-900">Khôi phục bản sao lưu ERP</h4>
                  <p className="text-xs text-slate-500">
                    Bản ghi: <strong className="font-mono text-slate-800">{selectedBackup.dateStr}</strong>
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedBackup(null)}
                className="text-slate-400 hover:text-slate-700 font-bold"
              >
                ✕
              </button>
            </div>

            {/* Mode Selection */}
            <div className="mt-6 space-y-3">
              <label
                onClick={() => setRestoreMode("drill")}
                className={`flex items-start gap-3 rounded-2xl border p-4 cursor-pointer transition ${
                  restoreMode === "drill"
                    ? "border-blue-500 bg-blue-50/40 text-blue-950"
                    : "border-slate-200 bg-white hover:bg-slate-50 text-slate-700"
                }`}
              >
                <input
                  type="radio"
                  name="restoreMode"
                  checked={restoreMode === "drill"}
                  onChange={() => setRestoreMode("drill")}
                  className="mt-1"
                />
                <div>
                  <strong className="block text-xs font-bold">
                    Diễn tập thử nghiệm (Restore Drill - Khuyên dùng)
                  </strong>
                  <p className="mt-0.5 text-[11px] text-slate-500 leading-normal">
                    Kéo bản backup từ S3 về, bung vào một database tạm để kiểm tra tính toàn vẹn và audit dữ liệu. An toàn 100%, không ảnh hưởng dữ liệu đang chạy.
                  </p>
                </div>
              </label>

              <label
                onClick={() => setRestoreMode("live")}
                className={`flex items-start gap-3 rounded-2xl border p-4 cursor-pointer transition ${
                  restoreMode === "live"
                    ? "border-rose-500 bg-rose-50/40 text-rose-950"
                    : "border-slate-200 bg-white hover:bg-slate-50 text-slate-700"
                }`}
              >
                <input
                  type="radio"
                  name="restoreMode"
                  checked={restoreMode === "live"}
                  onChange={() => setRestoreMode("live")}
                  className="mt-1"
                />
                <div>
                  <strong className="block text-xs font-bold text-rose-700">
                    Khôi phục Thực sự (Disaster Recovery)
                  </strong>
                  <p className="mt-0.5 text-[11px] text-slate-500 leading-normal">
                    Bung đè toàn bộ dữ liệu vào site production. Sử dụng khi máy chủ gặp sự cố thảm họa và cần phục hồi hoàn toàn.
                  </p>
                </div>
              </label>
            </div>

            {/* Result Message */}
            {restoreResult && (
              <div className="mt-4 rounded-xl bg-slate-50 p-3.5 border border-slate-200 text-xs text-slate-800 font-medium">
                {restoreResult}
              </div>
            )}

            {/* Modal Actions */}
            <div className="mt-6 flex items-center justify-end gap-3 border-t border-slate-100 pt-4">
              <button
                onClick={() => setSelectedBackup(null)}
                disabled={isRestoring}
                className="rounded-xl px-4 py-2 text-xs font-bold text-slate-500 hover:text-slate-800 transition"
              >
                Đóng
              </button>
              <button
                onClick={handleConfirmRestore}
                disabled={isRestoring}
                className={`inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-xs font-bold text-white shadow-md transition cursor-pointer ${
                  restoreMode === "drill"
                    ? "bg-blue-600 hover:bg-blue-700 shadow-blue-200"
                    : "bg-rose-600 hover:bg-rose-700 shadow-rose-200"
                } disabled:opacity-50`}
              >
                {isRestoring ? (
                  <>
                    <svg className="h-4 w-4 animate-spin fill-none stroke-current stroke-2" viewBox="0 0 24 24">
                      <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeLinecap="round" />
                    </svg>
                    <span>Đang xử lý...</span>
                  </>
                ) : (
                  <span>
                    {restoreMode === "drill" ? "Bắt đầu Diễn tập" : "Xác nhận Khôi phục Production"}
                  </span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

"""Small compatibility shims for the pinned Frappe runtime."""

from __future__ import annotations


def install_scheduler_compatibility() -> None:
    """Keep the pinned Frappe DuckDB scheduler hook callable.

    Frappe v16.31.1 registers ``cleanup_old_syncs`` but the controller exposes
    the implementation as ``DuckDBSync.clear_old_logs``.  Reuse that native
    implementation instead of modifying the vendor app or inventing a second
    cleanup implementation.
    """

    try:
        from frappe.core.doctype.duckdb_sync import duckdb_sync
    except ImportError:
        return
    if not hasattr(duckdb_sync, "cleanup_old_syncs"):
        duckdb_sync.cleanup_old_syncs = duckdb_sync.DuckDBSync.clear_old_logs

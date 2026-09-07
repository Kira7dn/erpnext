"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AssetResource } from "@/lib/letron-api";

const label = (resource: AssetResource) => resource.split("-").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
function display(value: unknown) { return value == null || value === "" ? "—" : typeof value === "object" ? JSON.stringify(value) : String(value); }

export function AssetResourceTable({ resource, rows }: Readonly<{ resource: AssetResource; rows: Record<string, unknown>[] }>) { const [query, setQuery] = useState(""); const columns = useMemo(() => [...new Set(rows.flatMap((row) => Object.keys(row)))].filter((key) => !["doctype", "owner", "modified"].includes(key)).slice(0, 7), [rows]); const filtered = useMemo(() => rows.filter((row) => JSON.stringify(row).toLowerCase().includes(query.toLowerCase())), [rows, query]); return <div className="rounded-xl border bg-card shadow-sm"><div className="flex flex-col gap-4 border-b p-5 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="font-semibold">{label(resource)}</h2><p className="text-sm text-muted-foreground">{filtered.length} of {rows.length} records</p></div><Input className="w-full sm:max-w-xs" placeholder={`Search ${label(resource).toLowerCase()}...`} value={query} onChange={(event) => setQuery(event.target.value)} /></div><Table><TableHeader><TableRow>{columns.map((column) => <TableHead key={column}>{column.replaceAll("_", " ")}</TableHead>)}<TableHead>Status</TableHead></TableRow></TableHeader><TableBody>{filtered.map((row, index) => { const name = String(row.name ?? row.id ?? index); return <TableRow key={name}>{columns.map((column) => <TableCell key={column}><Link className="hover:underline" href={`/assets/${resource}/${encodeURIComponent(name)}`}>{display(row[column])}</Link></TableCell>)}<TableCell><Badge variant={row.disabled ? "secondary" : "default"}>{row.disabled ? "Disabled" : String(row.status ?? row.docstatus ?? "Active")}</Badge></TableCell></TableRow>; })}</TableBody></Table>{!filtered.length ? <div className="p-12 text-center text-sm text-muted-foreground">No records returned by the API.</div> : null}</div>; }

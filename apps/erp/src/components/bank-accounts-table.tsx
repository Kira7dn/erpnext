"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { BankAccount } from "@/lib/letron-api";

export function BankAccountsTable({ accounts }: Readonly<{ accounts: BankAccount[] }>) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => accounts.filter((account) => [account.name, account.account_name, account.bank, account.company, account.account].join(" ").toLowerCase().includes(query.toLowerCase())), [accounts, query]);
  return <div className="rounded-xl border bg-card shadow-sm">
    <div className="flex flex-col gap-4 border-b p-5 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="font-semibold">Bank accounts</h2><p className="text-sm text-muted-foreground">{filtered.length} of {accounts.length} accounts</p></div><Input className="w-full sm:max-w-xs" placeholder="Search accounts..." value={query} onChange={(event) => setQuery(event.target.value)} /></div>
    <Table><TableHeader><TableRow><TableHead>Account</TableHead><TableHead>Bank</TableHead><TableHead>Company</TableHead><TableHead>Ledger account</TableHead><TableHead>Status</TableHead></TableRow></TableHeader><TableBody>
      {filtered.map((account) => <TableRow key={account.name}><TableCell><div className="font-medium">{account.account_name || account.name}</div><div className="text-xs text-muted-foreground">{account.name}</div></TableCell><TableCell>{account.bank || "—"}</TableCell><TableCell>{account.company || "—"}</TableCell><TableCell>{account.account || "—"}</TableCell><TableCell><Badge variant={account.disabled ? "secondary" : "default"}>{account.disabled ? "Disabled" : "Active"}</Badge></TableCell></TableRow>)}
    </TableBody></Table>{filtered.length === 0 ? <div className="p-12 text-center text-sm text-muted-foreground">No bank accounts returned by the API.</div> : null}
  </div>;
}

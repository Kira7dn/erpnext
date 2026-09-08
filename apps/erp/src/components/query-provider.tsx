"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function QueryProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        gcTime: 5 * 60_000,
        retry: (failureCount, error) => error instanceof ErpQueryError && [401, 403, 422].includes(error.status) ? false : failureCount < 1,
        refetchOnWindowFocus: false,
      },
    },
  }));
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

export class ErpQueryError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    this.name = "ErpQueryError";
  }
}

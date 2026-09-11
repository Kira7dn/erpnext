"use client";

import { useEffect } from "react";
import { redirectToLarkLogin } from "@/lib/auth-navigation";

export function ClientAuthRecovery() {
  useEffect(() => {
    redirectToLarkLogin();
  }, []);
  return null;
}

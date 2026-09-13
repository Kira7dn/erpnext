import { createPurchaseReceiptRequestSchema } from "@/generated/zod";
import type { createPurchaseReceiptRequest } from "@/generated/zod";

/** Compatibility names for the real-test harness; validation is generated. */
export type PurchaseReceiptCreate = createPurchaseReceiptRequest;
export type PurchaseReceiptItemCreate = PurchaseReceiptCreate["items"][number];

export function parsePurchaseReceiptCreate(input: unknown): PurchaseReceiptCreate {
  return createPurchaseReceiptRequestSchema.parse(input);
}

export function assertPurchaseReceiptCreate(value: unknown): PurchaseReceiptCreate {
  return createPurchaseReceiptRequestSchema.parse(value);
}

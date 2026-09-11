import { decrypt, encrypt, sha256 } from "./crypto";
import { getDb } from "./db";

const TRANSACTION_TTL_MS = 10 * 60 * 1000;
export const LARK_TRANSACTION_COOKIE = "letron_lark_tx";
export const LARK_TRANSACTION_TTL_SECONDS = TRANSACTION_TTL_MS / 1000;

export async function saveOAuthTransaction(input: {
  state: string;
  browserBinding: string;
  codeVerifier: string;
    interactionUid?: string;
    returnTo?: string;
    handoff?: boolean;
}): Promise<void> {
  await getDb().oAuthTransaction.create({
    data: {
      stateHash: sha256(input.state),
      browserBindingHash: sha256(input.browserBinding),
      encryptedCodeVerifier: encrypt(input.codeVerifier),
      interactionUid: input.interactionUid,
      returnTo: input.returnTo,
      handoff: input.handoff ?? false,
      expiresAt: new Date(Date.now() + TRANSACTION_TTL_MS),
    },
  });
}

export async function consumeOAuthTransaction(state: string, browserBinding: string): Promise<{
  codeVerifier: string;
  interactionUid: string | null;
  returnTo: string | null;
  handoff: boolean;
} | null> {
  const stateHash = sha256(state);
  return getDb().$transaction(async (tx) => {
    const consumed = await tx.oAuthTransaction.updateMany({
      where: {
        stateHash,
        browserBindingHash: sha256(browserBinding),
        consumedAt: null,
        expiresAt: { gt: new Date() },
      },
      data: { consumedAt: new Date() },
    });
    if (consumed.count !== 1) return null;
    const row = await tx.oAuthTransaction.findUniqueOrThrow({ where: { stateHash } });
    return {
      codeVerifier: decrypt(row.encryptedCodeVerifier),
      interactionUid: row.interactionUid,
      returnTo: row.returnTo,
      handoff: row.handoff,
    };
  });
}

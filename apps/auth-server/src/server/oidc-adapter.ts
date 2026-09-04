import type { Adapter, AdapterPayload } from "oidc-provider";

import type { Prisma } from "../../generated/prisma/client";
import { decrypt } from "./crypto";
import { getDb } from "./db";

function jsonPayload(payload: AdapterPayload): Prisma.InputJsonValue {
  return JSON.parse(JSON.stringify(payload)) as Prisma.InputJsonValue;
}

export class PrismaOidcAdapter implements Adapter {
  constructor(private readonly model: string) {}

  async upsert(id: string, payload: AdapterPayload, expiresIn?: number): Promise<void> {
    if (this.model === "Client") return;
    const expiresAt = expiresIn ? new Date(Date.now() + expiresIn * 1000) : null;
    await getDb().oidcArtifact.upsert({
      where: { model_id: { model: this.model, id } },
      create: {
        model: this.model,
        id,
        payload: jsonPayload(payload),
        grantId: payload.grantId,
        userCode: payload.userCode,
        uid: payload.uid,
        expiresAt,
      },
      update: {
        payload: jsonPayload(payload),
        grantId: payload.grantId,
        userCode: payload.userCode,
        uid: payload.uid,
        expiresAt,
      },
    });
  }

  async find(id: string): Promise<AdapterPayload | undefined> {
    if (this.model === "Client") {
      const client = await getDb().oidcClient.findUnique({ where: { clientId: id } });
      if (!client?.active) return undefined;
      return {
        ...(client.metadata as AdapterPayload),
        ...(client.encryptedClientSecret ? { client_secret: decrypt(client.encryptedClientSecret) } : {}),
      };
    }
    const row = await getDb().oidcArtifact.findUnique({ where: { model_id: { model: this.model, id } } });
    if (!row || (row.expiresAt && row.expiresAt <= new Date())) return undefined;
    return row.payload as AdapterPayload;
  }

  async findByUserCode(userCode: string): Promise<AdapterPayload | undefined> {
    return this.findByField("userCode", userCode);
  }

  async findByUid(uid: string): Promise<AdapterPayload | undefined> {
    return this.findByField("uid", uid);
  }

  private async findByField(field: "userCode" | "uid", value: string): Promise<AdapterPayload | undefined> {
    const row = await getDb().oidcArtifact.findFirst({
      where: { model: this.model, [field]: value, OR: [{ expiresAt: null }, { expiresAt: { gt: new Date() } }] },
    });
    return row?.payload as AdapterPayload | undefined;
  }

  async consume(id: string): Promise<void> {
    const row = await getDb().oidcArtifact.findUnique({ where: { model_id: { model: this.model, id } } });
    if (!row) return;
    const payload = { ...(row.payload as Record<string, unknown>), consumed: Math.floor(Date.now() / 1000) };
    await getDb().oidcArtifact.update({
      where: { model_id: { model: this.model, id } },
      data: { payload: payload as Prisma.InputJsonValue },
    });
  }

  async destroy(id: string): Promise<void> {
    if (this.model === "Client") return;
    await getDb().oidcArtifact.deleteMany({ where: { model: this.model, id } });
  }

  async revokeByGrantId(grantId: string): Promise<void> {
    await getDb().oidcArtifact.deleteMany({ where: { grantId } });
  }
}

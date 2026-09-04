import type { NextApiRequest, NextApiResponse } from "next";

import { getOidcProvider } from "./oidc";

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export async function finishInteraction(
  req: NextApiRequest,
  res: NextApiResponse,
  accountId: string,
): Promise<void> {
  const provider = getOidcProvider();
  const details = await provider.interactionDetails(req, res);

  if (details.prompt.name === "login") {
    await provider.interactionFinished(req, res, {
      login: { accountId, remember: true, amr: ["lark"] },
    });
    return;
  }

  if (details.prompt.name === "consent") {
    let grant = details.grantId ? await provider.Grant.find(details.grantId) : undefined;
    if (!grant) grant = new provider.Grant({ accountId, clientId: String(details.params.client_id) });
    const missingOIDCScope = stringList(details.prompt.details.missingOIDCScope);
    if (missingOIDCScope.length) grant.addOIDCScope(missingOIDCScope.join(" "));
    const grantId = await grant.save();
    await provider.interactionFinished(req, res, { consent: { grantId } });
    return;
  }

  throw new Error(`Unsupported interaction prompt: ${details.prompt.name}`);
}

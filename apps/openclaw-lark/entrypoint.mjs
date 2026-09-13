import { spawnSync } from "node:child_process";

const required = ["OPENCLAW_LARK_APP_ID", "OPENCLAW_LARK_APP_SECRET", "OPENAI_API_KEY", "OPENCLAW_GATEWAY_TOKEN"];
for (const name of required) {
  if (!process.env[name]?.trim()) {
    console.error(`[openclaw] missing required environment variable: ${name}`);
    process.exit(1);
  }
}

const run = (args, options = {}) => {
  const result = spawnSync("openclaw", args, {
    encoding: "utf8",
    stdio: options.quiet ? ["ignore", "ignore", "pipe"] : "inherit",
    env: process.env,
  });
  if (result.status !== 0) {
    if (options.quiet && result.stderr) process.stderr.write(result.stderr);
    throw new Error(`openclaw ${args.join(" ")} failed with exit code ${result.status}`);
  }
};

const set = (path, value, ...extra) => run(["config", "set", path, value, ...extra], { quiet: true });
const ref = (path, envName) => run(["config", "set", path, "--ref-provider", "default", "--ref-source", "env", "--ref-id", envName], { quiet: true });

const ensureFeishuPlugin = () => {
  const listed = spawnSync("openclaw", ["plugins", "list", "--json"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: process.env,
  });
  if (listed.status === 0) {
    try {
      const plugins = JSON.parse(listed.stdout);
      const current = Array.isArray(plugins.plugins) ? plugins.plugins.find((plugin) => plugin.id === "feishu") : undefined;
      if (
        current?.version === "2026.9.4" &&
        current.trust?.installSource === "npm" &&
        current.trust?.reason === "trusted-official"
      ) return;
    } catch {
      // Install below will produce the actionable error if the list is malformed.
    }
  }
  run([
    "plugins", "install", "@openclaw/feishu@2026.9.4",
    "--accept-capabilities", "--acknowledge-install-policy-warning", "--force", "--pin",
  ]);
};

try {
  ensureFeishuPlugin();
  // Keep all runtime configuration reproducible when the state volume is new.
  set("gateway.mode", "local");
  set("channels.feishu.enabled", "true");
  set("channels.feishu.domain", "lark");
  set("channels.feishu.connectionMode", "websocket");
  set("channels.feishu.appId", process.env.OPENCLAW_LARK_APP_ID.trim());
  ref("channels.feishu.appSecret", "OPENCLAW_LARK_APP_SECRET");
  set("channels.feishu.streaming", JSON.stringify({
    mode: "partial",
    chunkMode: "length",
    block: { enabled: true },
  }));
  set("agents.defaults.blockStreamingDefault", "on");
  set("agents.defaults.blockStreamingBreak", "text_end");
  set("agents.defaults.blockStreamingChunk", JSON.stringify({
    minChars: 8,
    maxChars: 800,
    breakPreference: "sentence",
  }));
  set("channels.feishu.dmPolicy", "pairing");
  set("channels.feishu.groupPolicy", "allowlist");
  if (process.env.OPENCLAW_LARK_GROUP_ID?.trim()) {
    set("channels.feishu.groupAllowFrom", JSON.stringify([process.env.OPENCLAW_LARK_GROUP_ID.trim()]));
  }
  set("models.providers.openai.baseUrl", (process.env.OPENAI_BASE_URL || "https://api.openai.com/v1").trim());
  ref("models.providers.openai.apiKey", "OPENAI_API_KEY");
  const model = process.env.OPENAI_MODEL?.trim() || "gpt-5.6-luna";
  set("models.providers.openai.models", JSON.stringify([{
    id: model,
    name: model,
    api: "openai-responses",
    reasoning: false,
    input: ["text", "image"],
    contextWindow: 128000,
    maxTokens: 8192,
  }]));
  set("agents.defaults.model.primary", `openai/${model}`);
  // Keep the long-lived group session responsive without discarding its durable transcript.
  set("agents.defaults.contextPruning.mode", "cache-ttl");
  set("agents.defaults.contextPruning.ttl", "5m");
  set("agents.defaults.compaction.enabled", "true");
  set("agents.defaults.compaction.keepRecentTokens", "12000");
  // Keep the full authorized catalog searchable, but defer large schemas until needed.
  // Keep a cache-stable capability directory in the prompt and hydrate full
  // schemas only for the selected tool. This preserves MCP access while
  // avoiding a full structured catalog rebuild on every turn.
  set("tools.toolSearch", JSON.stringify({ mode: "directory" }));
  set("messages.groupChat.historyLimit", "20");
  set("channels.feishu.typingIndicator", "true");
  set("channels.feishu.resolveSenderNames", "false");
  // The Codex host harness is not available inside this container and can
  // leave Feishu sessions stuck in running state. Feishu tools remain enabled.
  run(["plugins", "disable", "codex"]);
  run(["plugins", "enable", "feishu"]);
} catch (error) {
  console.error(`[openclaw] configuration failed: ${error.message}`);
  process.exit(1);
}

console.log("[openclaw] Feishu channel configured; starting gateway in container WebSocket mode");
const gateway = spawnSync("openclaw", [
  "gateway", "run", "--force", "--bind", "lan", "--port", "18789", "--auth", "token", "--token", process.env.OPENCLAW_GATEWAY_TOKEN,
], { stdio: "inherit", env: process.env });
process.exit(gateway.status ?? 1);

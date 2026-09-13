import http from "node:http";
import { randomUUID } from "node:crypto";
import { Client as McpClient } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import OpenAI from "openai";
import * as lark from "@larksuiteoapi/node-sdk";
import { createClient } from "redis";

const config = {
  appId: process.env.APP_ID?.trim(),
  appSecret: process.env.APP_SECRET?.trim(),
  domain: process.env.LARK_DOMAIN?.trim() || "https://open.larksuite.com",
  port: Number(process.env.PORT || 3010),
  model: process.env.OPENAI_MODEL?.trim() || "gpt-5.6-luna",
  tools: process.env.LARK_MCP_TOOLS?.trim() || "preset.default",
  redisUrl: process.env.REDIS_URL?.trim() || "redis://redis:6379",
  contextTtl: Number(process.env.LARK_BOT_CONTEXT_TTL_SECONDS || 86400),
  confirmTtl: Number(process.env.LARK_BOT_CONFIRM_TTL_SECONDS || 300),
};
if (!config.appId || !config.appSecret) throw new Error("APP_ID and APP_SECRET are required");

const larkClient = new lark.Client({ appId: config.appId, appSecret: config.appSecret, domain: lark.Domain.Lark });
const openai = process.env.OPENAI_API_KEY?.trim()
  ? new OpenAI({ apiKey: process.env.OPENAI_API_KEY.trim(), baseURL: process.env.OPENAI_BASE_URL?.trim() || undefined })
  : null;
const redis = createClient({ url: config.redisUrl });
redis.on("error", (error) => console.error(`redis error: ${error.message}`));
let mcpClient;
let mcpTransport;
const conversationLocks = new Map();
const key = (kind, id) => `letron:lark-bot:${kind}:${id}`;

function serial(id, fn) {
  const previous = conversationLocks.get(id) || Promise.resolve();
  const current = previous.catch(() => undefined).then(fn);
  conversationLocks.set(id, current.finally(() => {
    if (conversationLocks.get(id) === current) conversationLocks.delete(id);
  }));
  return current;
}
async function startMcp() {
  const command = process.platform === "win32" ? "npx.cmd" : "npx";
  mcpTransport = new StdioClientTransport({
    command,
    args: ["-y", "@larksuiteoapi/lark-mcp", "mcp", "--domain", config.domain, "--tools", config.tools],
    env: { ...process.env, APP_ID: config.appId, APP_SECRET: config.appSecret, LARK_DOMAIN: config.domain, LARK_TOKEN_MODE: "tenant_access_token" },
  });
  mcpClient = new McpClient({ name: "letron-lark-bot", version: "1.0.0" }, { capabilities: {} });
  await mcpClient.connect(mcpTransport);
  const listed = await mcpClient.listTools();
  console.log(`MCP ready: ${listed.tools.length} tools`);
}
async function sendText(chatId, text) {
  await larkClient.im.v1.message.create({
    params: { receive_id_type: "chat_id" },
    data: { receive_id: chatId, msg_type: "text", content: JSON.stringify({ text: String(text).slice(0, 4000) }) },
  });
}
function eventText(data) {
  try {
    const content = JSON.parse(data?.message?.content || data?.event?.message?.content || "{}");
    return typeof content.text === "string" ? content.text.trim() : "";
  } catch { return ""; }
}
function eventId(data) {
  return data?.event_id || data?.header?.event_id || data?.message?.message_id || data?.event?.message?.message_id || randomUUID();
}
function isWriteTool(name) {
  return /(?:create|update|patch|delete|remove|add|modify|move|import|grant|revoke|send|upload|rename|transfer|batch)/i.test(name);
}
function isForbiddenTool(name) {
  return /(?:user|contact).*(?:delete|remove)|(?:delete|remove).*(?:user|contact)/i.test(name);
}
function toolDefinitions(listed) {
  return listed.tools.map((tool) => ({
    type: "function",
    function: { name: tool.name, description: tool.description || "", parameters: tool.inputSchema || { type: "object", properties: {} } },
  }));
}
async function loadContext(chatId) {
  const raw = await redis.get(key("context", chatId));
  return raw ? JSON.parse(raw) : [];
}
async function saveContext(chatId, history) {
  await redis.set(key("context", chatId), JSON.stringify(history.slice(-30)), { EX: config.contextTtl });
}
async function pending(chatId) {
  const raw = await redis.get(key("pending", chatId));
  return raw ? JSON.parse(raw) : null;
}
async function requestWriteConfirmation(chatId, history, call) {
  const args = JSON.parse(call.function.arguments || "{}");
  const id = randomUUID().slice(0, 8);
  await redis.set(key("pending", chatId), JSON.stringify({ id, senderId: call.senderId, history, call: { id: call.id, name: call.function.name, args } }), { EX: config.confirmTtl });
  await sendText(chatId, `Thao tác ghi ${call.function.name} đang chờ xác nhận. Nếu đúng, trả lời: CONFIRM ${id}. Hết hạn sau ${Math.ceil(config.confirmTtl / 60)} phút.`);
}
async function continueWithTool(chatId, history, call, result) {
  history.push({ role: "tool", tool_call_id: call.id, content: JSON.stringify(result) });
  const followup = await openai.chat.completions.create({ model: config.model, messages: [{ role: "system", content: "Trả lời ngắn gọn bằng tiếng Việt, nêu rõ kết quả và lỗi nếu có." }, ...history] });
  const output = followup.choices[0]?.message?.content || "Đã xử lý xong.";
  history.push({ role: "assistant", content: output });
  await saveContext(chatId, history);
  await sendText(chatId, output);
}
async function confirm(chatId, senderId, token) {
  const item = await pending(chatId);
  if (!item || item.id !== token) { await sendText(chatId, "Không tìm thấy yêu cầu ghi đang chờ hoặc yêu cầu đã hết hạn."); return; }
  if (item.senderId !== senderId) { await sendText(chatId, "Chỉ người đã tạo yêu cầu mới được xác nhận thao tác này."); return; }
  await redis.del(key("pending", chatId));
  if (isForbiddenTool(item.call.name)) { await sendText(chatId, "Từ chối: bot không được phép xóa hoặc gỡ user."); return; }
  const result = await mcpClient.callTool({ name: item.call.name, arguments: item.call.args });
  await continueWithTool(chatId, item.history, item.call, result);
}
async function answer(chatId, senderId, text) {
  if (/^\/clear$/i.test(text)) { await redis.del(key("context", chatId), key("pending", chatId)); await sendText(chatId, "Đã xóa context và yêu cầu chờ."); return; }
  const confirmation = /^confirm\s+([a-z0-9-]+)$/i.exec(text);
  if (confirmation) { await confirm(chatId, senderId, confirmation[1]); return; }
  if (!openai) { await sendText(chatId, "Bot đã nhận tin nhắn nhưng OPENAI_API_KEY chưa sẵn sàng."); return; }
  const history = await loadContext(chatId);
  history.push({ role: "user", content: text });
  const listed = await mcpClient.listTools();
  const system = "Bạn là trợ lý LeTRON. Đọc dữ liệu tự do. Với mọi thao tác ghi, hãy gọi tool để bot xin xác nhận; tuyệt đối không xóa user/contact hoặc dữ liệu khi chưa có xác nhận rõ ràng.";
  let response = await openai.chat.completions.create({ model: config.model, reasoning_effort: "none", messages: [{ role: "system", content: system }, ...history], tools: toolDefinitions(listed), tool_choice: "auto" });
  for (let round = 0; round < 4; round += 1) {
    const message = response.choices[0]?.message;
    if (!message) throw new Error("OPENAI_EMPTY_RESPONSE");
    history.push(message);
    const calls = message.tool_calls || [];
    if (!calls.length) { await saveContext(chatId, history); await sendText(chatId, message.content || "Mình chưa có câu trả lời."); return; }
    for (const call of calls) {
      if (isForbiddenTool(call.function.name)) { await sendText(chatId, "Từ chối: bot không được phép xóa hoặc gỡ user."); return; }
      if (isWriteTool(call.function.name)) { await saveContext(chatId, history); await requestWriteConfirmation(chatId, history, { ...call, senderId }); return; }
      const result = await mcpClient.callTool({ name: call.function.name, arguments: JSON.parse(call.function.arguments || "{}") });
      history.push({ role: "tool", tool_call_id: call.id, content: JSON.stringify(result) });
    }
    response = await openai.chat.completions.create({ model: config.model, reasoning_effort: "none", messages: [{ role: "system", content: system }, ...history], tools: toolDefinitions(listed), tool_choice: "auto" });
  }
  throw new Error("MCP_TOOL_LOOP_LIMIT");
}
const server = http.createServer((request, response) => {
  if (request.url === "/healthz") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ ok: true, mcp: Boolean(mcpClient), redis: redis.isReady, openai: Boolean(openai), model: config.model }));
    return;
  }
  response.writeHead(404); response.end();
});
await redis.connect();
await startMcp();
server.listen(config.port, "0.0.0.0", () => console.log(`Lark bot health listening on :${config.port}`));
const dispatcher = new lark.EventDispatcher({}).register({
  "im.message.receive_v1": async (data) => {
    // EventDispatcher flattens v2 event payloads before invoking the handler.
    // Keep the nested fallback for webhook/test payloads.
    const message = data?.message || data?.event?.message;
    const text = eventText(data);
    const sender = data?.sender || data?.event?.sender;
    console.log(`Lark message event: type=${message?.message_type || "unknown"} text=${Boolean(text)} sender=${sender?.sender_type || "unknown"}`);
    if (!message?.chat_id || !text || message.message_type !== "text" || sender?.sender_type === "app") return;
    const id = eventId(data);
    if (!(await redis.set(key("event", id), "1", { NX: true, EX: 86400 }))) return;
    const senderId = sender?.sender_id?.union_id || sender?.sender_id?.open_id || message.chat_id;
    await serial(message.chat_id, async () => {
      try { await answer(message.chat_id, senderId, text); }
      catch (error) { console.error(`message handling failed: ${error instanceof Error ? error.message : String(error)}`); await sendText(message.chat_id, "Bot gặp lỗi khi xử lý yêu cầu. Vui lòng thử lại."); }
    });
  },
});
const wsClient = new lark.WSClient({ appId: config.appId, appSecret: config.appSecret, domain: lark.Domain.Lark });
await wsClient.start({ eventDispatcher: dispatcher });
console.log("Lark bot WebSocket connected");
async function shutdown() {
  server.close();
  await mcpTransport?.close().catch(() => undefined);
  await redis.quit().catch(() => undefined);
  process.exit(0);
}
process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);

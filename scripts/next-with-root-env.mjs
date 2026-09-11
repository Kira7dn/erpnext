import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const command = process.argv[2];
const args = process.argv.slice(2);

function parseEnv(content) {
  const values = new Map();
  for (const line of content.split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*)\s*$/);
    if (match) values.set(match[1], match[2].replace(/^['"]|['"]$/g, ""));
  }
  return values;
}

async function loadEnv(file, override) {
  const content = await readFile(resolve(root, file), "utf8");
  for (const [key, value] of parseEnv(content)) {
    if (value && (override || !process.env[key])) process.env[key] = value;
  }
}

if (!command) throw new Error("Next command is required");
await loadEnv(".env", false);
if (command === "build" || command === "start") await loadEnv(".env.production", true);

const executable = process.platform === "win32"
  ? resolve(process.cwd(), "node_modules/.bin/next.cmd")
  : resolve(process.cwd(), "node_modules/.bin/next");
const child = spawn(executable, args, {
  cwd: process.cwd(),
  env: process.env,
  stdio: "inherit",
  windowsHide: false,
  shell: process.platform === "win32",
});
child.on("exit", (code, signal) => process.exit(signal ? 1 : code ?? 1));

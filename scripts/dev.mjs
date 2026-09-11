import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = process.cwd();

function parseEnv(content) {
  const values = new Map();
  for (const line of content.split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*)\s*$/);
    if (!match || match[1].startsWith("#")) continue;
    values.set(match[1], match[2].replace(/^['"]|['"]$/g, ""));
  }
  return values;
}

try {
  const values = parseEnv(await readFile(resolve(root, ".env"), "utf8"));
  for (const [key, value] of values) if (!process.env[key] && value) process.env[key] = value;
} catch (error) {
  console.error(`Root dev launcher could not load .env: ${error.message}`);
  process.exit(1);
}

const commands = [
  "npm --prefix apps/auth-server run dev",
  "npm --prefix apps/erp run dev",
];
const children = commands.map((commandLine) => {
  const command = process.platform === "win32" ? process.env.ComSpec ?? "cmd.exe" : "npm";
  const args = process.platform === "win32" ? ["/d", "/s", "/c", commandLine] : commandLine.split(" ");
  const child = spawn(command, args, {
    cwd: root,
    env: process.env,
    stdio: "inherit",
    windowsHide: false,
  });
  child.on("error", (error) => {
    console.error(`Root dev child failed: ${error.message}`);
  });
  return child;
});

let stopping = false;
let exited = 0;
let exitCode = 0;
const stopChildren = (signal) => {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill(signal);
};
process.on("SIGINT", () => stopChildren("SIGINT"));
process.on("SIGTERM", () => stopChildren("SIGTERM"));
for (const child of children) {
  child.on("exit", (code) => {
    exited += 1;
    if (code && !stopping) {
      exitCode = code;
      stopChildren("SIGTERM");
    }
    if (exited === children.length) process.exit(exitCode);
  });
}

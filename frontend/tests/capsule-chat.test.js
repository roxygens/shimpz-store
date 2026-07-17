// @ts-nocheck -- executed by Node's built-in test runner; the browser bundle has no Node typings.
import assert from "node:assert/strict";
import test from "node:test";

import {
  createAssistantChatTurn,
  parseCapsuleStorage,
  parseCapsuleUpload,
  parseChatTerminalEvent,
  parseInstalledAssistants,
  selectRunnableAssistant,
} from "../src/lib/capsuleChat.js";

const file = {
  id: "a".repeat(32),
  name: "brief.txt",
  media_type: "text/plain",
  size: 5,
  sha256: "b".repeat(64),
};
const usage = { used_bytes: 5, limit_bytes: 100 * 1024 * 1024, remaining_bytes: 100 * 1024 * 1024 - 5 };

test("creates only an Assistant-scoped chat turn", () => {
  assert.deepEqual(createAssistantChatTurn("hello-pulse", "  hello  ", [file.id]), {
    assistant: "hello-pulse",
    message: "hello",
    files: [file.id],
  });
  for (const [assistant, message] of [
    ["", "hello"],
    ["../escape", "hello"],
    ["hello-pulse", ""],
    ["hello-pulse", { provider: "openai" }],
  ]) {
    assert.throws(() => createAssistantChatTurn(assistant, message));
  }
  for (const files of [
    ["../escape"],
    [file.id, file.id],
    Array.from({ length: 9 }, (_, index) => index.toString(16).padStart(32, "0")),
  ]) {
    assert.throws(() => createAssistantChatTurn("hello-pulse", "hello", files));
  }
});

test("accepts only exact bounded terminal chat events", () => {
  const terminalEvents = [
    { type: "done", reply: "complete", assistant: "hello-pulse", power: "reports.read" },
    { type: "done", reply: "complete", assistant: "hello-pulse", power: null },
    { type: "error", status: 504, detail: "provider timed out" },
    { type: "stopped" },
  ];
  for (const event of terminalEvents) {
    assert.deepEqual(parseChatTerminalEvent(event), event);
  }

  for (const event of [
    { type: "text", text: "partial" },
    { type: "tool", label: "shell" },
    { type: "ask", text: "approve?" },
    { type: "answered", answered: true },
    { type: "done", reply: "complete", assistant: "hello-pulse", power: null, extra: true },
    { type: "done", reply: "complete", assistant: "../escape", power: null },
    { type: "done", reply: "complete", assistant: "hello-pulse", power: "../escape" },
    { type: "done", reply: "x".repeat(60_001), assistant: "hello-pulse", power: null },
    { type: "error", status: true, detail: "failed" },
    { type: "error", status: 200, detail: "not an error" },
    { type: "error", status: 502, detail: "x".repeat(801) },
    { type: "stopped", requested: true },
  ]) {
    assert.throws(() => parseChatTerminalEvent(event));
  }
});

test("selects only a running installed Assistant and projects its declared Powers", () => {
  const assistants = parseInstalledAssistants({
    apps: [
      { app: "hello-pulse", status: "running", powers: ["hello"], container: "private" },
      { app: "salesnator", status: "exited", powers: ["campaigns.read"] },
      { app: "legacy-app", status: "running", powers: [] },
    ],
    capsule: "private",
  });
  assert.deepEqual(assistants, [
    { id: "hello-pulse", status: "running", powers: ["hello"] },
    { id: "salesnator", status: "exited", powers: ["campaigns.read"] },
  ]);
  assert.equal(selectRunnableAssistant(assistants, "hello-pulse"), "hello-pulse");
  assert.equal(selectRunnableAssistant(assistants, "salesnator"), "hello-pulse");
});

test("keeps Capsule files opaque and drops every path-like upstream field", () => {
  const inventory = parseCapsuleStorage({
    files: [{ ...file, created_at: 1_700_000_000, path: "/private/blob" }],
    ...usage,
    mount: "/private",
  });
  const uploaded = parseCapsuleUpload({ file: { ...file, ...usage, path: "/private/blob" }, ...usage });

  assert.deepEqual(inventory, { files: [{ ...file, created_at: 1_700_000_000 }], ...usage });
  assert.deepEqual(uploaded, { file, ...usage });
  assert.equal("path" in inventory.files[0], false);
  assert.equal("path" in uploaded.file, false);
});

test("rejects forged, duplicate and inconsistent Capsule inventories", () => {
  for (const value of [
    null,
    { files: "many", ...usage },
    { files: [{ ...file, id: "../escape", created_at: 1 }], ...usage },
    { files: [{ ...file, name: "../brief.txt", created_at: 1 }], ...usage },
    { files: [{ ...file, created_at: 1 }, { ...file, created_at: 2 }], ...usage },
    { files: [{ ...file, created_at: 1 }], ...usage, remaining_bytes: 0 },
  ]) {
    assert.throws(() => parseCapsuleStorage(value));
  }
});

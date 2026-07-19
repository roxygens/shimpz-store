// @ts-nocheck -- executed by Node's built-in test runner; the browser bundle has no Node typings.
import assert from "node:assert/strict";
import test from "node:test";

import {
  CHAT_WS_SUBPROTOCOL,
  createTeamChatTurn,
  parseTeamChatAssistantScope,
  parseTeamStorage,
  parseTeamUpload,
  parseChatTerminalEvent,
  teamChatReconnectDelay,
  teamChatWebSocketPath,
} from "../src/lib/teamChat.js";

const file = {
  id: "a".repeat(32),
  name: "brief.txt",
  media_type: "text/plain",
  size: 5,
  sha256: "b".repeat(64),
};
const usage = { used_bytes: 5, limit_bytes: 100 * 1024 * 1024, remaining_bytes: 100 * 1024 * 1024 - 5 };

test("creates a strict Team-scoped chat turn with an explicit Assistant scope", () => {
  assert.deepEqual(createTeamChatTurn("  hello  ", [file.id], ["shimpz-assistant"]), {
    message: "hello",
    files: [file.id],
    assistant_ids: ["shimpz-assistant"],
  });
  assert.deepEqual(createTeamChatTurn("brain only"), {
    message: "brain only",
    files: [],
    assistant_ids: [],
  });
  for (const message of ["", { provider: "openai" }]) {
    assert.throws(() => createTeamChatTurn(message));
  }
  for (const files of [
    ["../escape"],
    [file.id, file.id],
    Array.from({ length: 9 }, (_, index) => index.toString(16).padStart(32, "0")),
  ]) {
    assert.throws(() => createTeamChatTurn("hello", files));
  }
  for (const assistants of [
    ["../escape"],
    ["shimpz-assistant", "shimpz-assistant"],
    Array.from({ length: 17 }, (_, index) => `assistant-${index}`),
  ]) {
    assert.throws(() => createTeamChatTurn("hello", [], assistants));
  }
});

test("accepts only an exact bounded default Assistant scope", () => {
  assert.deepEqual(
    parseTeamChatAssistantScope({ assistant_ids: ["shimpz-assistant"] }),
    ["shimpz-assistant"],
  );
  assert.deepEqual(parseTeamChatAssistantScope({ assistant_ids: [] }), []);
  for (const inventory of [
    null,
    { installed: ["shimpz-assistant"] },
    { assistant_ids: ["shimpz-assistant"], private: true },
    { assistant_ids: ["bad_id"] },
    { assistant_ids: ["shimpz-assistant", "shimpz-assistant"] },
  ]) {
    assert.throws(() => parseTeamChatAssistantScope(inventory));
  }
});

test("accepts only exact bounded terminal events from the authoritative Team", () => {
  const terminalEvents = [
    { type: "done", reply: "complete", team_name: "Marketing" },
    { type: "error", status: 504, detail: "provider timed out" },
    { type: "stopped" },
  ];
  for (const event of terminalEvents) {
    assert.deepEqual(parseChatTerminalEvent(event, "Marketing"), event);
  }

  for (const event of [
    { type: "text", text: "partial" },
    { type: "tool", label: "shell" },
    { type: "ask", text: "approve?" },
    { type: "answered", answered: true },
    { type: "done", reply: "complete", team_name: "Marketing", trace: [] },
    { type: "done", reply: "complete", team_name: "Sales" },
    { type: "done", reply: "complete", team_name: " Marketing " },
    { type: "done", reply: "x".repeat(60_001), team_name: "Marketing" },
    { type: "error", status: true, detail: "failed" },
    { type: "error", status: 200, detail: "not an error" },
    { type: "error", status: 502, detail: "x".repeat(801) },
    { type: "stopped", requested: true },
  ]) {
    assert.throws(() => parseChatTerminalEvent(event, "Marketing"));
  }
});

test("uses the single versioned Team chat WebSocket contract", () => {
  assert.equal(CHAT_WS_SUBPROTOCOL, "shimpz.chat.v2");
  assert.equal(teamChatWebSocketPath("team_one"), "/api/teams/team_one/chat/ws");
  for (const teamId of ["", "../escape", "team-one", "A"]) {
    assert.throws(() => teamChatWebSocketPath(teamId));
  }
});

test("caps Team chat reconnect backoff without encoding automatic replay", () => {
  assert.deepEqual(
    [0, 1, 2, 3, 4, 20].map(teamChatReconnectDelay),
    [400, 800, 1600, 3200, 5000, 5000],
  );
  for (const invalid of [-1, 0.5, "1", null]) {
    assert.throws(() => teamChatReconnectDelay(invalid));
  }
});

test("keeps Team files opaque and drops every path-like upstream field", () => {
  const inventory = parseTeamStorage({
    files: [{ ...file, created_at: 1_700_000_000, path: "/private/blob" }],
    ...usage,
    mount: "/private",
  });
  const uploaded = parseTeamUpload({ file: { ...file, ...usage, path: "/private/blob" }, ...usage });

  assert.deepEqual(inventory, { files: [{ ...file, created_at: 1_700_000_000 }], ...usage });
  assert.deepEqual(uploaded, { file, ...usage });
  assert.equal("path" in inventory.files[0], false);
  assert.equal("path" in uploaded.file, false);
});

test("rejects forged, duplicate and inconsistent Team inventories", () => {
  for (const value of [
    null,
    { files: "many", ...usage },
    { files: [{ ...file, id: "../escape", created_at: 1 }], ...usage },
    { files: [{ ...file, name: "../brief.txt", created_at: 1 }], ...usage },
    { files: [{ ...file, created_at: 1 }, { ...file, created_at: 2 }], ...usage },
    { files: [{ ...file, created_at: 1 }], ...usage, remaining_bytes: 0 },
  ]) {
    assert.throws(() => parseTeamStorage(value));
  }
});

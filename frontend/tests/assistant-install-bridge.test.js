// @ts-nocheck -- executed by Node's built-in test runner; the browser bundle has no Node typings.
import assert from "node:assert/strict";
import test from "node:test";

import {
  ASSISTANT_INSTALL_ACK_TIMEOUT_MS,
  ASSISTANT_INSTALL_ACK_TYPE,
  ASSISTANT_STORE_CONTEXT_TYPE,
  ASSISTANT_STORE_FRAME_MAX_HEIGHT,
  ASSISTANT_STORE_FRAME_MIN_HEIGHT,
  ASSISTANT_STORE_FRAME_TYPE,
  ASSISTANT_STORE_STATE_MAX_IDS,
  ASSISTANT_STORE_STATE_TYPE,
  ASSISTANT_UNINSTALL_ACK_TYPE,
  acceptAssistantStoreState,
  acceptAssistantStoreContext,
  assistantStoreActionForState,
  createAssistantStoreFrameMessage,
  createAssistantInstallRequest,
  createAssistantUninstallRequest,
  classifyAssistantInstallAck,
  classifyAssistantUninstallAck,
  resolveInstallParentOrigin,
  shouldReconcileAssistantStoreAction,
} from "../src/lib/assistantInstallBridge.js";

test("resolves only exact HTTP loopback Admin origins from the iframe referrer", () => {
  assert.equal(resolveInstallParentOrigin("http://127.0.0.1:7777/assistants/"), "http://127.0.0.1:7777");
  assert.equal(resolveInstallParentOrigin("http://localhost:7777/assistants/"), "http://localhost:7777");
  assert.equal(resolveInstallParentOrigin("http://[::1]:7777/assistants/"), "http://[::1]:7777");

  for (const referrer of [
    "",
    "https://127.0.0.1:7777/assistants/",
    "http://127.0.0.2:7777/assistants/",
    "http://localtest.me:7777/assistants/",
    "http://captain@localhost:7777/assistants/",
    "not a URL",
  ]) {
    assert.throws(() => resolveInstallParentOrigin(referrer));
  }
});

test("keeps the validated referrer fallback compatible with an Admin that has no context handshake", () => {
  const parentWindow = {};
  const parentOrigin = resolveInstallParentOrigin("http://localhost:7777/assistants/");
  const data = {
    type: ASSISTANT_INSTALL_ACK_TYPE,
    version: 1,
    assistant: "hello-pulse",
    accepted: true,
  };

  assert.equal(parentOrigin, "http://localhost:7777");
  assert.equal(
    classifyAssistantInstallAck(
      { source: parentWindow, origin: parentOrigin, data },
      { parentWindow, parentOrigin, assistant: "hello-pulse" },
    ),
    "accepted",
  );
});

test("creates the exact inert Assistant install request", () => {
  assert.deepEqual(createAssistantInstallRequest("hello-pulse"), {
    type: "shimpz:assistant-install",
    version: 1,
    assistant: "hello-pulse",
  });
  for (const assistant of ["", "Hello-Pulse", "../hello", "hello_pulse", "a".repeat(81)]) {
    assert.throws(() => createAssistantInstallRequest(assistant));
  }
});

test("creates the exact inert Assistant uninstall request", () => {
  assert.deepEqual(createAssistantUninstallRequest("hello-pulse"), {
    type: "shimpz:assistant-uninstall",
    version: 1,
    assistant: "hello-pulse",
  });
  for (const assistant of ["", "Hello-Pulse", "../hello", "hello_pulse", "a".repeat(81)]) {
    assert.throws(() => createAssistantUninstallRequest(assistant));
  }
});

test("creates one exact bounded integer frame measurement", () => {
  assert.deepEqual(createAssistantStoreFrameMessage(719.2), {
    type: ASSISTANT_STORE_FRAME_TYPE,
    version: 1,
    height: 720,
  });
  assert.equal(createAssistantStoreFrameMessage(1).height, ASSISTANT_STORE_FRAME_MIN_HEIGHT);
  assert.equal(createAssistantStoreFrameMessage(9000).height, ASSISTANT_STORE_FRAME_MAX_HEIGHT);
  for (const height of [Number.NaN, Number.POSITIVE_INFINITY, "720", null]) {
    assert.throws(() => createAssistantStoreFrameMessage(height));
  }
});

test("accepts Store context only from the exact parent at an HTTP loopback origin", () => {
  const parentWindow = {};
  const data = { type: ASSISTANT_STORE_CONTEXT_TYPE, version: 1 };
  for (const origin of [
    "http://127.0.0.1:7777",
    "http://localhost:7777",
    "http://[::1]:7777",
  ]) {
    assert.equal(acceptAssistantStoreContext({ source: parentWindow, origin, data }, parentWindow), origin);
  }

  const rejected = [
    { source: {}, origin: "http://localhost:7777", data },
    { source: parentWindow, origin: "https://localhost:7777", data },
    { source: parentWindow, origin: "http://127.0.0.2:7777", data },
    { source: parentWindow, origin: "http://captain@localhost:7777", data },
    { source: parentWindow, origin: "http://localhost:7777/path", data },
    { source: parentWindow, origin: "http://localhost:7777", data: { ...data, extra: true } },
    { source: parentWindow, origin: "http://localhost:7777", data: { ...data, version: 2 } },
    { source: parentWindow, origin: "http://localhost:7777", data: { type: ASSISTANT_STORE_FRAME_TYPE, version: 1 } },
  ];
  for (const event of rejected) assert.equal(acceptAssistantStoreContext(event, parentWindow), null);
  assert.equal(acceptAssistantStoreContext(null, parentWindow), null);
  assert.equal(acceptAssistantStoreContext({ source: parentWindow, origin: "http://localhost", data }, null), null);
});

test("accepts only exact bounded installed-Assistant state from the loopback parent", () => {
  const parentWindow = {};
  const parentOrigin = "http://localhost:7777";
  const ready = {
    type: ASSISTANT_STORE_STATE_TYPE,
    version: 1,
    status: "ready",
    installed: ["hello-pulse", "salesnator"],
  };

  assert.deepEqual(
    acceptAssistantStoreState(
      { source: parentWindow, origin: parentOrigin, data: ready },
      parentWindow,
      parentOrigin,
    ),
    { status: "ready", installed: ["hello-pulse", "salesnator"] },
  );
  for (const status of ["loading", "error"]) {
    assert.deepEqual(
      acceptAssistantStoreState(
        { source: parentWindow, origin: parentOrigin, data: { ...ready, status, installed: [] } },
        parentWindow,
        parentOrigin,
      ),
      { status, installed: [] },
    );
  }

  const maximum = Array.from({ length: ASSISTANT_STORE_STATE_MAX_IDS }, (_, index) => `assistant-${index}`);
  assert.equal(
    acceptAssistantStoreState(
      { source: parentWindow, origin: parentOrigin, data: { ...ready, installed: maximum } },
      parentWindow,
      parentOrigin,
    )?.installed.length,
    ASSISTANT_STORE_STATE_MAX_IDS,
  );
});

test("rejects untrusted, malformed, oversized, and state-bearing non-ready inventory", () => {
  const parentWindow = {};
  const parentOrigin = "http://127.0.0.1:7777";
  const exact = {
    source: parentWindow,
    origin: parentOrigin,
    data: {
      type: ASSISTANT_STORE_STATE_TYPE,
      version: 1,
      status: "ready",
      installed: ["hello-pulse"],
    },
  };
  const tooMany = Array.from(
    { length: ASSISTANT_STORE_STATE_MAX_IDS + 1 },
    (_, index) => `assistant-${index}`,
  );
  const cases = [
    { ...exact, source: {} },
    { ...exact, origin: "http://localhost:7777" },
    { ...exact, data: { ...exact.data, type: "shimpz:assistant-store-inventory" } },
    { ...exact, data: { ...exact.data, version: "1" } },
    { ...exact, data: { ...exact.data, version: 2 } },
    { ...exact, data: { ...exact.data, status: "idle" } },
    { ...exact, data: { ...exact.data, installed: null } },
    { ...exact, data: { ...exact.data, installed: "hello-pulse" } },
    { ...exact, data: { ...exact.data, installed: ["hello-pulse", "hello-pulse"] } },
    { ...exact, data: { ...exact.data, installed: ["Hello-Pulse"] } },
    { ...exact, data: { ...exact.data, installed: ["a".repeat(81)] } },
    { ...exact, data: { ...exact.data, installed: tooMany } },
    { ...exact, data: { ...exact.data, status: "loading" } },
    { ...exact, data: { ...exact.data, status: "error" } },
    { ...exact, data: { ...exact.data, capsule: "private_capsule" } },
    { ...exact, data: { ...exact.data, token: "secret" } },
    { ...exact, data: null },
    { ...exact, data: [ASSISTANT_STORE_STATE_TYPE, 1, "ready", ["hello-pulse"]] },
  ];

  for (const candidate of cases) {
    assert.equal(acceptAssistantStoreState(candidate, parentWindow, parentOrigin), null);
  }
  assert.equal(acceptAssistantStoreState(exact, null, parentOrigin), null);
  assert.equal(acceptAssistantStoreState(exact, parentWindow, "https://127.0.0.1:7777"), null);
  assert.equal(
    acceptAssistantStoreState(
      { ...exact, origin: "https://127.0.0.1:7777" },
      parentWindow,
      "https://127.0.0.1:7777",
    ),
    null,
  );
});

test("keeps an old Admin install-compatible and requires authoritative ready state for uninstall", () => {
  assert.equal(assistantStoreActionForState("legacy", [], "hello-pulse"), "install");
  assert.equal(assistantStoreActionForState("ready", [], "hello-pulse"), "install");
  assert.equal(assistantStoreActionForState("ready", ["hello-pulse"], "hello-pulse"), "uninstall");
  assert.equal(assistantStoreActionForState("loading", ["hello-pulse"], "hello-pulse"), "blocked");
  assert.equal(assistantStoreActionForState("error", ["hello-pulse"], "hello-pulse"), "blocked");
  assert.equal(assistantStoreActionForState("unknown", ["hello-pulse"], "hello-pulse"), "blocked");
  assert.equal(assistantStoreActionForState("ready", ["hello-pulse"], "Hello-Pulse"), "blocked");
  assert.equal(assistantStoreActionForState("ready", "hello-pulse", "hello-pulse"), "blocked");
});

test("reconciles ACK and cancellation only against authoritative ready inventory", () => {
  assert.equal(
    shouldReconcileAssistantStoreAction("install", "pending", "ready", ["hello-pulse"], "hello-pulse"),
    true,
  );
  assert.equal(
    shouldReconcileAssistantStoreAction("uninstall", "pending", "ready", [], "hello-pulse"),
    true,
  );
  assert.equal(
    shouldReconcileAssistantStoreAction("install", "pending", "ready", [], "hello-pulse"),
    false,
  );
  assert.equal(
    shouldReconcileAssistantStoreAction("uninstall", "pending", "ready", ["hello-pulse"], "hello-pulse"),
    false,
  );
  assert.equal(
    shouldReconcileAssistantStoreAction("uninstall", "sent", "ready", ["hello-pulse"], "hello-pulse"),
    true,
  );
  assert.equal(
    shouldReconcileAssistantStoreAction("install", "error", "ready", [], "hello-pulse"),
    true,
  );
  for (const status of ["legacy", "loading", "error"]) {
    assert.equal(
      shouldReconcileAssistantStoreAction("uninstall", "sent", status, [], "hello-pulse"),
      false,
    );
  }
});

test("accepts only the exact generic ACK from the exact parent source and origin", () => {
  const parentWindow = {};
  const parentOrigin = "http://127.0.0.1:7777";
  const data = {
    type: ASSISTANT_INSTALL_ACK_TYPE,
    version: 1,
    assistant: "hello-pulse",
    accepted: true,
  };
  const context = { parentWindow, parentOrigin, assistant: "hello-pulse" };

  assert.equal(classifyAssistantInstallAck({ source: parentWindow, origin: parentOrigin, data }, context), "accepted");
  assert.equal(
    classifyAssistantInstallAck({ source: {}, origin: parentOrigin, data }, context),
    "ignore",
  );
  assert.equal(
    classifyAssistantInstallAck({ source: parentWindow, origin: "http://localhost:7777", data }, context),
    "ignore",
  );
  assert.equal(
    classifyAssistantInstallAck({ source: parentWindow, origin: parentOrigin, data: { type: "other" } }, context),
    "ignore",
  );
});

test("rejects every malformed trusted ACK and defines a bounded wait", () => {
  const parentWindow = {};
  const parentOrigin = "http://127.0.0.1:7777";
  const context = { parentWindow, parentOrigin, assistant: "hello-pulse" };
  const exact = {
    type: ASSISTANT_INSTALL_ACK_TYPE,
    version: 1,
    assistant: "hello-pulse",
    accepted: true,
  };
  const cases = [
    { ...exact, version: "1" },
    { ...exact, version: 2 },
    { ...exact, assistant: "salesnator" },
    { ...exact, accepted: false },
    { ...exact, capsule: "private_capsule" },
    { ...exact, token: "secret" },
  ];
  for (const data of cases) {
    assert.equal(classifyAssistantInstallAck({ source: parentWindow, origin: parentOrigin, data }, context), "invalid");
  }
  assert.equal(ASSISTANT_INSTALL_ACK_TIMEOUT_MS, 3000);
});

test("accepts only the exact uninstall ACK and never confuses it with install", () => {
  const parentWindow = {};
  const parentOrigin = "http://[::1]:7777";
  const context = { parentWindow, parentOrigin, assistant: "hello-pulse" };
  const exact = {
    type: ASSISTANT_UNINSTALL_ACK_TYPE,
    version: 1,
    assistant: "hello-pulse",
    accepted: true,
  };

  assert.equal(
    classifyAssistantUninstallAck({ source: parentWindow, origin: parentOrigin, data: exact }, context),
    "accepted",
  );
  assert.equal(
    classifyAssistantUninstallAck(
      { source: parentWindow, origin: parentOrigin, data: { ...exact, type: ASSISTANT_INSTALL_ACK_TYPE } },
      context,
    ),
    "ignore",
  );
  for (const data of [
    { ...exact, version: 2 },
    { ...exact, assistant: "salesnator" },
    { ...exact, accepted: false },
    { ...exact, installed: false },
    { ...exact, capsule: "private_capsule" },
  ]) {
    assert.equal(
      classifyAssistantUninstallAck({ source: parentWindow, origin: parentOrigin, data }, context),
      "invalid",
    );
  }
  assert.equal(
    classifyAssistantUninstallAck({ source: {}, origin: parentOrigin, data: exact }, context),
    "ignore",
  );
});

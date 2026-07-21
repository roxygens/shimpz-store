const ASSISTANT_ID_RE = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const REQUEST_KEYS = Object.freeze(["assistant", "type", "version"]);
const ACK_KEYS = Object.freeze(["accepted", "assistant", "type", "version"]);
const FRAME_KEYS = Object.freeze(["height", "type", "version"]);
const CONTEXT_KEYS = Object.freeze(["type", "version"]);
const STORE_STATE_KEYS = Object.freeze(["installed", "status", "type", "version"]);
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "[::1]"]);
const CANARY_ADMIN_ORIGIN = "https://local.shimpz.com";
const STORE_STATE_STATUSES = new Set(["error", "loading", "ready"]);

export const ASSISTANT_INSTALL_TYPE = "shimpz:assistant-install";
export const ASSISTANT_INSTALL_ACK_TYPE = "shimpz:assistant-install-ack";
export const ASSISTANT_UNINSTALL_TYPE = "shimpz:assistant-uninstall";
export const ASSISTANT_UNINSTALL_ACK_TYPE = "shimpz:assistant-uninstall-ack";
export const ASSISTANT_INSTALL_VERSION = 1;
export const ASSISTANT_INSTALL_ACK_TIMEOUT_MS = 3000;
export const ASSISTANT_STORE_FRAME_TYPE = "shimpz:assistant-store-frame";
export const ASSISTANT_STORE_CONTEXT_TYPE = "shimpz:assistant-store-context";
export const ASSISTANT_STORE_STATE_TYPE = "shimpz:assistant-store-state";
export const ASSISTANT_STORE_FRAME_VERSION = 1;
export const ASSISTANT_STORE_STATE_VERSION = 1;
export const ASSISTANT_STORE_FRAME_MIN_HEIGHT = 320;
export const ASSISTANT_STORE_FRAME_MAX_HEIGHT = 5000;
export const ASSISTANT_STORE_STATE_MAX_IDS = 128;

/**
 * @param {unknown} value
 * @param {readonly string[]} expected
 */
function hasExactKeys(value, expected) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")) return false;
  keys.sort();
  return keys.length === expected.length && keys.every((key, index) => key === expected[index]);
}

/** @param {unknown} value */
function isTrustedAdminOrigin(value) {
  if (typeof value !== "string") return false;
  try {
    const origin = new URL(value);
    if (origin.origin !== value || origin.username || origin.password) return false;
    return (
      (origin.protocol === "http:" && LOOPBACK_HOSTS.has(origin.hostname)) ||
      origin.origin === CANARY_ADMIN_ORIGIN
    );
  } catch {
    return false;
  }
}

/** @param {string} referrer */
export function resolveInstallParentOrigin(referrer) {
  if (typeof referrer !== "string" || !referrer) throw new Error("missing local Admin referrer");
  const parent = new URL(referrer);
  if (parent.username || parent.password || !isTrustedAdminOrigin(parent.origin)) {
    throw new Error("unexpected local Admin origin");
  }
  return parent.origin;
}

/**
 * Create the exact inert frame measurement sent to a local Admin parent.
 * @param {number} height
 */
export function createAssistantStoreFrameMessage(height) {
  if (typeof height !== "number" || !Number.isFinite(height)) {
    throw new Error("invalid Assistant Store frame height");
  }
  const boundedHeight = Math.min(
    ASSISTANT_STORE_FRAME_MAX_HEIGHT,
    Math.max(ASSISTANT_STORE_FRAME_MIN_HEIGHT, Math.ceil(height)),
  );
  const message = {
    type: ASSISTANT_STORE_FRAME_TYPE,
    version: ASSISTANT_STORE_FRAME_VERSION,
    height: boundedHeight,
  };
  if (!hasExactKeys(message, FRAME_KEYS)) throw new Error("invalid Assistant Store frame message");
  return message;
}

/**
 * Accept the exact context reply only from the current parent window at a named Admin origin.
 * The returned origin is safe to use as the exact targetOrigin for the existing install request.
 * @param {{ source?: unknown, origin?: unknown, data?: unknown } | null | undefined} event
 * @param {unknown} parentWindow
 */
export function acceptAssistantStoreContext(event, parentWindow) {
  if (!event || !parentWindow || event.source !== parentWindow) return null;
  const data = event.data;
  if (data === null || typeof data !== "object" || Array.isArray(data)) return null;
  if (!hasExactKeys(data, CONTEXT_KEYS)) return null;
  const value = /** @type {Record<string, unknown>} */ (data);
  if (
    value.type !== ASSISTANT_STORE_CONTEXT_TYPE ||
    value.version !== ASSISTANT_STORE_FRAME_VERSION ||
    typeof event.origin !== "string"
  ) {
    return null;
  }
  return isTrustedAdminOrigin(event.origin) ? event.origin : null;
}

/**
 * Accept only bounded Assistant IDs from the exact loopback parent. This intentionally reveals no
 * Team identity, runtime details, tokens, or credentials to the public Store document.
 * @param {{ source?: unknown, origin?: unknown, data?: unknown } | null | undefined} event
 * @param {unknown} parentWindow
 * @param {string} parentOrigin
 * @returns {{ status: "error" | "loading" | "ready", installed: string[] } | null}
 */
export function acceptAssistantStoreState(event, parentWindow, parentOrigin) {
  if (
    !event ||
    !parentWindow ||
    event.source !== parentWindow ||
    event.origin !== parentOrigin ||
    typeof parentOrigin !== "string"
  ) {
    return null;
  }
  try {
    if (resolveInstallParentOrigin(`${parentOrigin}/`) !== parentOrigin) return null;
  } catch {
    return null;
  }

  const data = event.data;
  if (!hasExactKeys(data, STORE_STATE_KEYS)) return null;
  const value = /** @type {Record<string, unknown>} */ (data);
  if (
    value.type !== ASSISTANT_STORE_STATE_TYPE ||
    value.version !== ASSISTANT_STORE_STATE_VERSION ||
    typeof value.status !== "string" ||
    !STORE_STATE_STATUSES.has(value.status) ||
    !Array.isArray(value.installed) ||
    value.installed.length > ASSISTANT_STORE_STATE_MAX_IDS
  ) {
    return null;
  }
  if (value.status !== "ready" && value.installed.length !== 0) return null;

  const seen = new Set();
  for (const assistant of value.installed) {
    if (
      typeof assistant !== "string" ||
      !ASSISTANT_ID_RE.test(assistant) ||
      assistant.length > 80 ||
      seen.has(assistant)
    ) {
      return null;
    }
    seen.add(assistant);
  }
  return {
    status: /** @type {"error" | "loading" | "ready"} */ (value.status),
    installed: [...value.installed],
  };
}

/**
 * Resolve the only safe Store action from locally held inventory state. A legacy Admin remains
 * install-compatible, while an unavailable authoritative inventory can never become uninstall.
 * @param {unknown} status
 * @param {unknown} installed
 * @param {unknown} assistant
 * @returns {"blocked" | "install" | "uninstall"}
 */
export function assistantStoreActionForState(status, installed, assistant) {
  if (
    typeof assistant !== "string" ||
    !ASSISTANT_ID_RE.test(assistant) ||
    assistant.length > 80 ||
    !Array.isArray(installed)
  ) {
    return "blocked";
  }
  if (status === "legacy") return "install";
  if (status !== "ready") return "blocked";
  return installed.includes(assistant) ? "uninstall" : "install";
}

/**
 * Reconcile pending work only after its target is visible, but clear acknowledged/error feedback on
 * any later authoritative snapshot (including a locally cancelled confirmation) without inventing
 * success. The rendered action continues to come solely from that snapshot.
 * @param {unknown} action
 * @param {unknown} actionState
 * @param {unknown} inventoryStatus
 * @param {unknown} installed
 * @param {unknown} assistant
 */
export function shouldReconcileAssistantStoreAction(
  action,
  actionState,
  inventoryStatus,
  installed,
  assistant,
) {
  if (
    inventoryStatus !== "ready" ||
    (action !== "install" && action !== "uninstall") ||
    (actionState !== "pending" && actionState !== "sent" && actionState !== "error")
  ) {
    return false;
  }
  if (actionState !== "pending") return true;
  const nextAction = assistantStoreActionForState(inventoryStatus, installed, assistant);
  return (action === "install" && nextAction === "uninstall") ||
    (action === "uninstall" && nextAction === "install");
}

/** @param {string} assistant */
export function createAssistantInstallRequest(assistant) {
  if (typeof assistant !== "string" || !ASSISTANT_ID_RE.test(assistant) || assistant.length > 80) {
    throw new Error("invalid Assistant id");
  }
  const request = { type: ASSISTANT_INSTALL_TYPE, version: ASSISTANT_INSTALL_VERSION, assistant };
  if (!hasExactKeys(request, REQUEST_KEYS)) throw new Error("invalid install request");
  return request;
}

/** @param {string} assistant */
export function createAssistantUninstallRequest(assistant) {
  if (typeof assistant !== "string" || !ASSISTANT_ID_RE.test(assistant) || assistant.length > 80) {
    throw new Error("invalid Assistant id");
  }
  const request = { type: ASSISTANT_UNINSTALL_TYPE, version: ASSISTANT_INSTALL_VERSION, assistant };
  if (!hasExactKeys(request, REQUEST_KEYS)) throw new Error("invalid uninstall request");
  return request;
}

/**
 * Classify only replies from the exact loopback parent window. Untrusted messages are ignored;
 * a malformed ACK from the trusted parent fails the pending request instead of becoming success.
 */
/**
 * @param {{ source?: unknown, origin?: unknown, data?: unknown } | null | undefined} event
 * @param {{ parentWindow: unknown, parentOrigin: string, assistant: string }} expected
 */
export function classifyAssistantInstallAck(event, expected) {
  const { parentWindow, parentOrigin, assistant } = expected;
  if (!event || event.source !== parentWindow || event.origin !== parentOrigin) return "ignore";
  const data = event.data;
  if (data === null || typeof data !== "object" || Array.isArray(data)) return "ignore";
  const value = /** @type {Record<string, unknown>} */ (data);
  if (value.type !== ASSISTANT_INSTALL_ACK_TYPE) return "ignore";
  if (!hasExactKeys(value, ACK_KEYS)) return "invalid";
  return value.version === ASSISTANT_INSTALL_VERSION && value.assistant === assistant && value.accepted === true
    ? "accepted"
    : "invalid";
}

/**
 * Classify only the exact uninstall ACK from the trusted loopback parent. Install acknowledgements
 * cannot satisfy an uninstall request, and no local state is accepted as part of the ACK.
 * @param {{ source?: unknown, origin?: unknown, data?: unknown } | null | undefined} event
 * @param {{ parentWindow: unknown, parentOrigin: string, assistant: string }} expected
 */
export function classifyAssistantUninstallAck(event, expected) {
  const { parentWindow, parentOrigin, assistant } = expected;
  if (!event || event.source !== parentWindow || event.origin !== parentOrigin) return "ignore";
  const data = event.data;
  if (data === null || typeof data !== "object" || Array.isArray(data)) return "ignore";
  const value = /** @type {Record<string, unknown>} */ (data);
  if (value.type !== ASSISTANT_UNINSTALL_ACK_TYPE) return "ignore";
  if (!hasExactKeys(value, ACK_KEYS)) return "invalid";
  return value.version === ASSISTANT_INSTALL_VERSION && value.assistant === assistant && value.accepted === true
    ? "accepted"
    : "invalid";
}

const ASSISTANT_ID_RE = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const REQUEST_KEYS = Object.freeze(["assistant", "type", "version"]);
const ACK_KEYS = Object.freeze(["accepted", "assistant", "type", "version"]);
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "[::1]"]);

export const ASSISTANT_INSTALL_TYPE = "shimpz:assistant-install";
export const ASSISTANT_INSTALL_ACK_TYPE = "shimpz:assistant-install-ack";
export const ASSISTANT_INSTALL_VERSION = 1;
export const ASSISTANT_INSTALL_ACK_TIMEOUT_MS = 3000;

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

/** @param {string} referrer */
export function resolveInstallParentOrigin(referrer) {
  if (typeof referrer !== "string" || !referrer) throw new Error("missing local Admin referrer");
  const parent = new URL(referrer);
  if (
    parent.protocol !== "http:" ||
    !LOOPBACK_HOSTS.has(parent.hostname) ||
    parent.username ||
    parent.password
  ) {
    throw new Error("unexpected local Admin origin");
  }
  return parent.origin;
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

const CAPSULE_ID_RE = /^[a-z0-9_]{1,40}$/;
const ASSISTANT_ID_RE = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const LOCALES = new Set(["en", "pt"]);
const RELEASED_ASSISTANTS = new Set(["hello-pulse"]);

/** @typedef {{ id: string, name: string }} CloudCapsule */

export const CLOUD_CAPSULE_LIMIT = 128;
export const CLOUD_ASSISTANT_LIMIT = 128;

/** @param {unknown} value @returns {value is Record<string, unknown>} */
function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** @param {unknown} embedded @returns {"self-hosted" | "cloud"} */
export function assistantStoreMode(embedded) {
  if (typeof embedded !== "boolean") throw new Error("invalid Assistant Store mode");
  return embedded ? "self-hosted" : "cloud";
}

/** @param {unknown} mode @param {unknown} topLevel */
export function cloudStoreCanStart(mode, topLevel) {
  if ((mode !== "cloud" && mode !== "self-hosted") || typeof topLevel !== "boolean") {
    throw new Error("invalid Assistant Store execution context");
  }
  return mode === "cloud" && topLevel;
}

/** @param {unknown} payload @returns {{ authenticated: boolean }} */
export function parseCloudAccount(payload) {
  if (!isPlainObject(payload) || typeof payload.authenticated !== "boolean") {
    throw new Error("invalid account response");
  }
  return { authenticated: payload.authenticated };
}

/** @param {unknown} payload @returns {CloudCapsule[]} */
export function parseCloudCapsules(payload) {
  if (!isPlainObject(payload) || !Array.isArray(payload.capsules)) {
    throw new Error("invalid Capsule inventory");
  }
  if (payload.capsules.length > CLOUD_CAPSULE_LIMIT) {
    throw new Error("Capsule inventory is too large");
  }

  const seen = new Set();
  const capsules = /** @type {unknown[]} */ (payload.capsules);
  return capsules.map((value) => {
    if (!isPlainObject(value) || typeof value.id !== "string" || !CAPSULE_ID_RE.test(value.id)) {
      throw new Error("invalid Capsule");
    }
    if (seen.has(value.id)) throw new Error("duplicate Capsule");
    seen.add(value.id);
    const name = value.name == null ? value.id : value.name;
    if (
      typeof name !== "string" ||
      name.length < 1 ||
      name.length > 80 ||
      name.trim() !== name ||
      [...name].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)
    ) {
      throw new Error("invalid Capsule name");
    }
    return { id: value.id, name };
  });
}

/** @param {unknown} capsules @param {unknown} candidate */
export function selectCloudCapsule(capsules, candidate) {
  if (!Array.isArray(capsules) || typeof candidate !== "string") return "";
  return capsules.some((capsule) => isPlainObject(capsule) && capsule.id === candidate) ? candidate : "";
}

/** @param {unknown} payload @returns {string[]} */
export function parseCloudAssistantInventory(payload) {
  if (!isPlainObject(payload) || Reflect.ownKeys(payload).length !== 1 || !Array.isArray(payload.installed)) {
    throw new Error("invalid Assistant inventory");
  }
  if (payload.installed.length > CLOUD_ASSISTANT_LIMIT) {
    throw new Error("Assistant inventory is too large");
  }
  const seen = new Set();
  for (const assistant of payload.installed) {
    if (
      typeof assistant !== "string" ||
      assistant.length > 80 ||
      !ASSISTANT_ID_RE.test(assistant) ||
      seen.has(assistant)
    ) {
      throw new Error("invalid Assistant inventory");
    }
    seen.add(assistant);
  }
  return [...payload.installed];
}

/**
 * @param {unknown} inventoryReady
 * @param {unknown} installed
 * @param {unknown} assistant
 * @returns {"blocked" | "install" | "uninstall"}
 */
export function cloudAssistantAction(inventoryReady, installed, assistant) {
  if (
    inventoryReady !== true ||
    !Array.isArray(installed) ||
    typeof assistant !== "string" ||
    !RELEASED_ASSISTANTS.has(assistant)
  ) {
    return "blocked";
  }
  return installed.includes(assistant) ? "uninstall" : "install";
}

/** @param {unknown} requestGeneration @param {unknown} currentGeneration @param {unknown} requestCapsule @param {unknown} currentCapsule */
export function cloudRequestIsCurrent(requestGeneration, currentGeneration, requestCapsule, currentCapsule) {
  return Number.isSafeInteger(requestGeneration) &&
    requestGeneration === currentGeneration &&
    typeof requestCapsule === "string" &&
    requestCapsule === currentCapsule;
}

/** @param {unknown} locale @param {unknown} assistant */
export function closedAssistantStoreHref(locale, assistant) {
  if (typeof locale !== "string" || typeof assistant !== "string" || !LOCALES.has(locale) || !RELEASED_ASSISTANTS.has(assistant)) {
    throw new Error("invalid Assistant Store destination");
  }
  return `/${locale}/assistants?assistant=${encodeURIComponent(assistant)}`;
}

/** @param {unknown} locale @param {unknown} assistant */
export function closedAssistantLoginHref(locale, assistant) {
  if (typeof locale !== "string" || typeof assistant !== "string" || !LOCALES.has(locale) || !RELEASED_ASSISTANTS.has(assistant)) {
    throw new Error("invalid Assistant login destination");
  }
  return `/${locale}/login?return=assistants&assistant=${encodeURIComponent(assistant)}`;
}

/** @param {unknown} locale @param {unknown} assistant */
export function closedAssistantCapsuleHref(locale, assistant) {
  if (typeof locale !== "string" || typeof assistant !== "string" || !LOCALES.has(locale) || !RELEASED_ASSISTANTS.has(assistant)) {
    throw new Error("invalid Assistant Capsule destination");
  }
  return `/${locale}/capsule?return=assistants&assistant=${encodeURIComponent(assistant)}`;
}

/** @param {unknown} locale @param {unknown} search @returns {string | null} */
export function resolveClosedAssistantReturn(locale, search) {
  if (typeof locale !== "string" || !LOCALES.has(locale) || typeof search !== "string") return null;
  const params = new URLSearchParams(search);
  const keys = [...params.keys()];
  if (
    keys.length !== 2 ||
    new Set(keys).size !== 2 ||
    params.get("return") !== "assistants"
  ) {
    return null;
  }
  const assistant = params.get("assistant");
  return assistant !== null && RELEASED_ASSISTANTS.has(assistant)
    ? closedAssistantStoreHref(locale, assistant)
    : null;
}

/** @param {unknown} search @returns {string} */
export function requestedAssistantFromSearch(search) {
  if (typeof search !== "string") return "";
  const params = new URLSearchParams(search);
  const keys = [...params.keys()];
  if (keys.length !== 1 || keys[0] !== "assistant") return "";
  const assistant = params.get("assistant");
  return assistant !== null && RELEASED_ASSISTANTS.has(assistant) ? assistant : "";
}

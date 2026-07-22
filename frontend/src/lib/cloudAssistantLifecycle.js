const TEAM_ID_RE = /^[a-z0-9_]{1,40}$/;
const ASSISTANT_ID_RE = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const LOCALES = new Set(["en", "pt"]);
const STORE_ASSISTANTS = new Set(["shimpz-cloudflare"]);
const RELEASED_ASSISTANTS = new Set(["shimpz-cloudflare"]);

/** @typedef {{ team_id: string, team_name: string }} CloudTeam */

export const CLOUD_TEAM_LIMIT = 128;
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

/** @param {unknown} payload @returns {CloudTeam[]} */
export function parseCloudTeams(payload) {
  if (!isPlainObject(payload) || !Array.isArray(payload.teams)) {
    throw new Error("invalid Team inventory");
  }
  if (payload.teams.length > CLOUD_TEAM_LIMIT) {
    throw new Error("Team inventory is too large");
  }

  const seen = new Set();
  const teams = /** @type {unknown[]} */ (payload.teams);
  return teams.map((value) => {
    if (!isPlainObject(value) || typeof value.team_id !== "string" || !TEAM_ID_RE.test(value.team_id)) {
      throw new Error("invalid Team");
    }
    if (seen.has(value.team_id)) throw new Error("duplicate Team");
    seen.add(value.team_id);
    const teamName = value.team_name;
    if (
      typeof teamName !== "string" ||
      teamName.length < 1 ||
      teamName.length > 80 ||
      teamName.trim() !== teamName ||
      [...teamName].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)
    ) {
      throw new Error("invalid Team name");
    }
    return { team_id: value.team_id, team_name: teamName };
  });
}

/** @param {unknown} teams @param {unknown} candidate */
export function selectCloudTeam(teams, candidate) {
  if (!Array.isArray(teams) || typeof candidate !== "string") return "";
  return teams.some((team) => isPlainObject(team) && team.team_id === candidate) ? candidate : "";
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

/** @param {unknown} requestGeneration @param {unknown} currentGeneration @param {unknown} requestTeamId @param {unknown} currentTeamId */
export function cloudRequestIsCurrent(requestGeneration, currentGeneration, requestTeamId, currentTeamId) {
  return Number.isSafeInteger(requestGeneration) &&
    requestGeneration === currentGeneration &&
    typeof requestTeamId === "string" &&
    requestTeamId === currentTeamId;
}

/** @param {unknown} locale @param {unknown} assistant */
export function closedAssistantStoreHref(locale, assistant) {
  if (typeof locale !== "string" || typeof assistant !== "string" || !LOCALES.has(locale) || !STORE_ASSISTANTS.has(assistant)) {
    throw new Error("invalid Assistant Store destination");
  }
  return `/${locale}/assistants?assistant=${encodeURIComponent(assistant)}`;
}

/** @param {unknown} locale @param {unknown} assistant */
export function closedAssistantLoginHref(locale, assistant) {
  if (typeof locale !== "string" || typeof assistant !== "string" || !LOCALES.has(locale) || !STORE_ASSISTANTS.has(assistant)) {
    throw new Error("invalid Assistant login destination");
  }
  return `/${locale}/login?return=assistants&assistant=${encodeURIComponent(assistant)}`;
}

/** @param {unknown} locale @param {unknown} assistant */
export function closedAssistantTeamHref(locale, assistant) {
  if (typeof locale !== "string" || typeof assistant !== "string" || !LOCALES.has(locale) || !STORE_ASSISTANTS.has(assistant)) {
    throw new Error("invalid Assistant Team destination");
  }
  return `/${locale}/team?return=assistants&assistant=${encodeURIComponent(assistant)}`;
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
  return assistant !== null && STORE_ASSISTANTS.has(assistant)
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
  return assistant !== null && STORE_ASSISTANTS.has(assistant) ? assistant : "";
}

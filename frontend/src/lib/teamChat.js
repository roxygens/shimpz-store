const FILE_ID = /^[a-f0-9]{32}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const TEAM_ID_RE = /^[a-z0-9_]{1,40}$/;
const ASSISTANT_ID_RE = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const MAX_FILES = 256;
const MAX_FILES_PER_TURN = 8;
const MAX_FILE_UPLOAD_BYTES = 25 * 1024 * 1024;
const MAX_ASSISTANTS_PER_TURN = 16;
const MAX_MESSAGE_CHARS = 16_000;
const MAX_REPLY_CHARS = 60_000;
const MAX_ERROR_DETAIL_CHARS = 800;
export const CHAT_WS_SUBPROTOCOL = "shimpz.chat.v2";

/** Capped reconnect delay. Reconnection never implies replaying a chat frame. @param {any} attempt */
export function teamChatReconnectDelay(attempt) {
  if (!Number.isSafeInteger(attempt) || attempt < 0) throw new TypeError("invalid reconnect attempt");
  return Math.min(400 * (2 ** Math.min(attempt, 4)), 5_000);
}

/** @param {any} teamId @returns {string} */
export function teamChatWebSocketPath(teamId) {
  return `/api/teams/${canonicalTeamId(teamId)}/chat/ws`;
}

/** @typedef {{ used_bytes: number, limit_bytes: number, remaining_bytes: number }} StorageUsage */
/** @typedef {{ id: string, name: string, media_type: string, size: number, sha256: string, created_at?: number }} StoredFile */

/** @param {any} value @returns {Record<string, any> | null} */
function record(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value : null;
}

/** @param {Record<string, any>} value @param {string[]} keys @returns {boolean} */
function hasExactKeys(value, keys) {
  const actual = Object.keys(value);
  return actual.length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}

/** @param {any} value @returns {string} */
function canonicalTeamId(value) {
  if (typeof value !== "string" || !TEAM_ID_RE.test(value)) {
    throw new TypeError("invalid Team id");
  }
  return value;
}

/** @param {any} value @returns {string} */
function canonicalTeamName(value) {
  if (
    typeof value !== "string" ||
    !value ||
    value.length > 80 ||
    value.trim() !== value ||
    /[\u0000-\u001f\u007f]/.test(value)
  ) {
    throw new TypeError("invalid Team name");
  }
  return value;
}

/** @param {any} value @returns {string} */
function chatReply(value) {
  if (
    typeof value !== "string" ||
    !value.trim() ||
    value.length > MAX_REPLY_CHARS ||
    /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value)
  ) {
    throw new TypeError("invalid chat reply");
  }
  return value;
}

/** @param {any} value @returns {StorageUsage} */
function usage(value) {
  const source = record(value);
  if (!source) throw new TypeError("invalid Team storage usage");
  /** @type {Record<string, number>} */
  const result = {};
  for (const key of ["used_bytes", "limit_bytes", "remaining_bytes"]) {
    const amount = source[key];
    if (!Number.isSafeInteger(amount) || amount < 0) throw new TypeError("invalid Team storage usage");
    result[key] = amount;
  }
  const withinQuota = result.used_bytes <= result.limit_bytes &&
    result.used_bytes + result.remaining_bytes === result.limit_bytes;
  const overQuota = result.used_bytes >= result.limit_bytes && result.remaining_bytes === 0;
  if (!withinQuota && !overQuota) {
    throw new TypeError("inconsistent Team storage usage");
  }
  return /** @type {StorageUsage} */ (result);
}

/** @param {any} value @param {boolean} createdAtRequired @returns {StoredFile} */
function fileMetadata(value, createdAtRequired) {
  const source = record(value);
  if (!source) throw new TypeError("invalid Team file metadata");
  const { id, name, media_type: mediaType, size, sha256, created_at: createdAt } = source;
  if (
    typeof id !== "string" ||
    !FILE_ID.test(id) ||
    typeof name !== "string" ||
    !name ||
    name.trim() !== name ||
    name.length > 255 ||
    name === "." ||
    name === ".." ||
    /[\\/\u0000-\u001f\u007f]/.test(name) ||
    typeof mediaType !== "string" ||
    !mediaType ||
    mediaType.length > 127 ||
    !Number.isSafeInteger(size) ||
    size < 1 ||
    size > MAX_FILE_UPLOAD_BYTES ||
    typeof sha256 !== "string" ||
    !SHA256.test(sha256)
  ) {
    throw new TypeError("invalid Team file metadata");
  }
  /** @type {StoredFile} */
  const metadata = { id, name, media_type: mediaType, size, sha256 };
  if (createdAtRequired || createdAt !== undefined) {
    if (!Number.isSafeInteger(createdAt) || createdAt < 0) {
      throw new TypeError("invalid Team file timestamp");
    }
    metadata.created_at = createdAt;
  }
  return metadata;
}

/** @param {any} value @returns {string[]} */
function assistantIds(value) {
  if (!Array.isArray(value) || value.length > MAX_ASSISTANTS_PER_TURN) {
    throw new TypeError("invalid chat Assistant scope");
  }
  const ids = value.map((assistantId) => {
    if (
      typeof assistantId !== "string" ||
      assistantId.length > 80 ||
      !ASSISTANT_ID_RE.test(assistantId)
    ) {
      throw new TypeError("invalid chat Assistant id");
    }
    return assistantId;
  });
  if (ids.length !== new Set(ids).size) throw new TypeError("duplicate chat Assistant id");
  return ids;
}

/** @param {any} value @returns {string[]} */
export function parseTeamChatAssistantScope(value) {
  const source = record(value);
  if (!source || !hasExactKeys(source, ["assistant_ids"])) {
    throw new TypeError("invalid chat Assistant inventory");
  }
  return assistantIds(source.assistant_ids);
}

/** @param {any} message @param {any} [files] @param {any} [assistants] @returns {{ message: string, files: string[], assistant_ids: string[] }} */
export function createTeamChatTurn(message, files = [], assistants = []) {
  if (typeof message !== "string") throw new TypeError("message must be a string");
  const text = message.trim();
  if (!text || text.length > MAX_MESSAGE_CHARS) throw new TypeError("invalid chat message");
  if (!Array.isArray(files) || files.length > MAX_FILES_PER_TURN) {
    throw new TypeError("invalid chat files");
  }
  const opaqueIds = files.map((fileId) => {
    if (typeof fileId !== "string" || !FILE_ID.test(fileId)) throw new TypeError("invalid chat file id");
    return fileId;
  });
  if (opaqueIds.length !== new Set(opaqueIds).size) throw new TypeError("duplicate chat file id");
  return { message: text, files: opaqueIds, assistant_ids: assistantIds(assistants) };
}

/**
 * @param {any} value
 * @param {any} expectedTeamId
 * @param {any} expectedTeamName
 * @returns {{ type: "done", team_id: string, team_name: string, reply: string } | { type: "error", status: number, detail: string } | { type: "stopped" }}
 */
export function parseChatTerminalEvent(value, expectedTeamId, expectedTeamName) {
  const source = record(value);
  if (!source) throw new TypeError("invalid chat terminal event");
  if (source.type === "done") {
    if (!hasExactKeys(source, ["type", "team_id", "team_name", "reply"])) {
      throw new TypeError("invalid chat completion event");
    }
    const teamId = canonicalTeamId(source.team_id);
    const teamName = canonicalTeamName(source.team_name);
    if (
      teamId !== canonicalTeamId(expectedTeamId) ||
      teamName !== canonicalTeamName(expectedTeamName)
    ) {
      throw new TypeError("Team identity mismatch");
    }
    return {
      type: "done",
      team_id: teamId,
      team_name: teamName,
      reply: chatReply(source.reply),
    };
  }
  if (source.type === "error") {
    if (
      !hasExactKeys(source, ["type", "status", "detail"]) ||
      !Number.isInteger(source.status) ||
      source.status < 400 ||
      source.status > 599 ||
      typeof source.detail !== "string" ||
      !source.detail ||
      source.detail !== source.detail.trim() ||
      source.detail.length > MAX_ERROR_DETAIL_CHARS ||
      /[\u0000-\u001f\u007f]/.test(source.detail)
    ) {
      throw new TypeError("invalid chat error event");
    }
    return { type: "error", status: source.status, detail: source.detail };
  }
  if (source.type === "stopped" && hasExactKeys(source, ["type"])) {
    return { type: "stopped" };
  }
  throw new TypeError("invalid chat terminal event");
}

/** @param {any} value @returns {{ files: StoredFile[] } & StorageUsage} */
export function parseTeamStorage(value) {
  const source = record(value);
  if (!source || !Array.isArray(source.files) || source.files.length > MAX_FILES) {
    throw new TypeError("invalid Team storage inventory");
  }
  const files = source.files.map((/** @type {any} */ file) => fileMetadata(file, true));
  if (
    files.map(({ id }) => id).length !==
    new Set(files.map(({ id }) => id)).size
  ) {
    throw new TypeError("duplicate Team file");
  }
  return { files, ...usage(source) };
}

/** @param {any} value @returns {{ file: StoredFile } & StorageUsage} */
export function parseTeamUpload(value) {
  const source = record(value);
  if (!source) throw new TypeError("invalid Team upload response");
  return { file: fileMetadata(source.file, true), ...usage(source) };
}

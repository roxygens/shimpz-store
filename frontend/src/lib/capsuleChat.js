const FILE_ID = /^[a-f0-9]{32}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const CAPSULE_ID = /^[a-z0-9_]{1,40}$/;
const MAX_FILES = 256;
const MAX_FILES_PER_TURN = 8;
const MAX_MESSAGE_CHARS = 16_000;
const MAX_REPLY_CHARS = 60_000;
const MAX_ERROR_DETAIL_CHARS = 800;

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
  if (!source) throw new TypeError("invalid Capsule storage usage");
  /** @type {Record<string, number>} */
  const result = {};
  for (const key of ["used_bytes", "limit_bytes", "remaining_bytes"]) {
    const amount = source[key];
    if (!Number.isSafeInteger(amount) || amount < 0) throw new TypeError("invalid Capsule storage usage");
    result[key] = amount;
  }
  if (result.used_bytes + result.remaining_bytes !== result.limit_bytes) {
    throw new TypeError("inconsistent Capsule storage usage");
  }
  return /** @type {StorageUsage} */ (result);
}

/** @param {any} value @param {boolean} createdAtRequired @returns {StoredFile} */
function fileMetadata(value, createdAtRequired) {
  const source = record(value);
  if (!source) throw new TypeError("invalid Capsule file metadata");
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
    size < 0 ||
    typeof sha256 !== "string" ||
    !SHA256.test(sha256)
  ) {
    throw new TypeError("invalid Capsule file metadata");
  }
  /** @type {StoredFile} */
  const metadata = { id, name, media_type: mediaType, size, sha256 };
  if (createdAtRequired || createdAt !== undefined) {
    if (!Number.isSafeInteger(createdAt) || createdAt < 0) {
      throw new TypeError("invalid Capsule file timestamp");
    }
    metadata.created_at = createdAt;
  }
  return metadata;
}

/** @param {any} message @param {any} [files] @returns {{ message: string, files?: string[] }} */
export function createTeamChatTurn(message, files = []) {
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
  return opaqueIds.length
    ? { message: text, files: opaqueIds }
    : { message: text };
}

/**
 * @param {any} value
 * @param {any} expectedTeam
 * @returns {{ type: "done", reply: string, team: string } | { type: "error", status: number, detail: string } | { type: "stopped" }}
 */
export function parseChatTerminalEvent(value, expectedTeam) {
  const source = record(value);
  if (!source) throw new TypeError("invalid chat terminal event");
  if (source.type === "done") {
    if (!hasExactKeys(source, ["type", "reply", "team"])) {
      throw new TypeError("invalid chat completion event");
    }
    const team = canonicalTeamName(source.team);
    if (team !== canonicalTeamName(expectedTeam)) throw new TypeError("Team identity mismatch");
    return { type: "done", reply: chatReply(source.reply), team };
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

/** @param {any} value @param {any} expectedCapsule @param {any} expectedTeam */
export function parseTeamChatResponse(value, expectedCapsule, expectedTeam) {
  const source = record(value);
  if (!source || !hasExactKeys(source, ["capsule", "team", "reply"])) {
    throw new TypeError("invalid Team chat response");
  }
  if (
    typeof expectedCapsule !== "string" ||
    !CAPSULE_ID.test(expectedCapsule) ||
    source.capsule !== expectedCapsule
  ) {
    throw new TypeError("Capsule identity mismatch");
  }
  const team = canonicalTeamName(source.team);
  if (team !== canonicalTeamName(expectedTeam)) throw new TypeError("Team identity mismatch");
  return { capsule: source.capsule, team, reply: chatReply(source.reply) };
}

/** @param {any} value @returns {{ files: StoredFile[] } & StorageUsage} */
export function parseCapsuleStorage(value) {
  const source = record(value);
  if (!source || !Array.isArray(source.files) || source.files.length > MAX_FILES) {
    throw new TypeError("invalid Capsule storage inventory");
  }
  const files = source.files.map((/** @type {any} */ file) => fileMetadata(file, true));
  if (
    files.map(({ id }) => id).length !==
    new Set(files.map(({ id }) => id)).size
  ) {
    throw new TypeError("duplicate Capsule file");
  }
  return { files, ...usage(source) };
}

/** @param {any} value @returns {{ file: StoredFile } & StorageUsage} */
export function parseCapsuleUpload(value) {
  const source = record(value);
  if (!source) throw new TypeError("invalid Capsule upload response");
  return { file: fileMetadata(source.file, false), ...usage(source) };
}

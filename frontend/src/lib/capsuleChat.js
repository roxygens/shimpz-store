const ASSISTANT_ID = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const POWER_ID = /^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$/;
const FILE_ID = /^[a-f0-9]{32}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const MAX_ASSISTANTS = 64;
const MAX_POWERS = 64;
const MAX_FILES = 256;
const MAX_FILES_PER_TURN = 8;
const MAX_MESSAGE_CHARS = 16_000;

/** @typedef {{ used_bytes: number, limit_bytes: number, remaining_bytes: number }} StorageUsage */
/** @typedef {{ id: string, name: string, media_type: string, size: number, sha256: string, created_at?: number }} StoredFile */
/** @typedef {{ id: string, status: string, powers: string[] }} InstalledAssistant */

/** @param {any} value @returns {Record<string, any> | null} */
function record(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value : null;
}

/** @param {any} value @returns {string} */
function canonicalAssistant(value) {
  if (typeof value !== "string" || value.length > 80 || !ASSISTANT_ID.test(value)) {
    throw new TypeError("invalid Assistant id");
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

/** @param {any} value @returns {InstalledAssistant[]} */
export function parseInstalledAssistants(value) {
  const source = record(value);
  if (!source || !Array.isArray(source.apps) || source.apps.length > MAX_ASSISTANTS) {
    throw new TypeError("invalid installed Assistant inventory");
  }
  const assistants = source.apps.map((/** @type {any} */ entry) => {
    const item = record(entry);
    if (!item) throw new TypeError("invalid installed Assistant");
    const id = canonicalAssistant(item.app);
    if (typeof item.status !== "string" || !item.status || item.status.length > 32) {
      throw new TypeError("invalid installed Assistant status");
    }
    if (!Array.isArray(item.powers) || item.powers.length > MAX_POWERS) {
      throw new TypeError("invalid installed Assistant Powers");
    }
    const powers = item.powers.map((/** @type {any} */ power) => {
      if (typeof power !== "string" || power.length > 80 || !POWER_ID.test(power)) {
        throw new TypeError("invalid installed Assistant Power");
      }
      return power;
    });
    if (powers.length !== new Set(powers).size) throw new TypeError("duplicate installed Assistant Power");
    return { id, status: item.status, powers };
  });
  if (
    assistants.map(({ id }) => id).length !==
    new Set(assistants.map(({ id }) => id)).size
  ) {
    throw new TypeError("duplicate installed Assistant");
  }
  return assistants.filter((assistant) => assistant.powers.length > 0);
}

/** @param {InstalledAssistant[]} assistants @param {any} requested @returns {string} */
export function selectRunnableAssistant(assistants, requested) {
  if (!Array.isArray(assistants)) throw new TypeError("invalid installed Assistant inventory");
  const running = assistants.filter((assistant) => assistant?.status === "running");
  return running.some((assistant) => assistant.id === requested) ? requested : running[0]?.id ?? "";
}

/** @param {any} assistant @param {any} message @param {any} [files] @returns {{ assistant: string, message: string, files?: string[] }} */
export function createAssistantChatTurn(assistant, message, files = []) {
  const selected = canonicalAssistant(assistant);
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
    ? { assistant: selected, message: text, files: opaqueIds }
    : { assistant: selected, message: text };
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

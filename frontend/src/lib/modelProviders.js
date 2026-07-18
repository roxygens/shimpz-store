/**
 * @typedef {{id: string, title: string, inputUsdPerMillion: number, outputUsdPerMillion: number}} ModelDefinition
 */

/** @param {string} id @param {string} title @param {number} inputUsdPerMillion @param {number} outputUsdPerMillion */
const freezeModel = (id, title, inputUsdPerMillion, outputUsdPerMillion) =>
  Object.freeze({ id, title, inputUsdPerMillion, outputUsdPerMillion });

// Base rates verified 2026-07-17: https://developers.openai.com/api/docs/models and https://platform.claude.com/docs/en/about-claude/pricing
const OPENAI_MODELS = Object.freeze([
  freezeModel("gpt-5.6-sol", "GPT-5.6 Sol", 5, 30),
  freezeModel("gpt-5.6-terra", "GPT-5.6 Terra", 2.5, 15),
  freezeModel("gpt-5.6-luna", "GPT-5.6 Luna", 1, 6),
  freezeModel("gpt-5.5", "GPT-5.5", 5, 30),
]);

const ANTHROPIC_MODELS = Object.freeze([
  freezeModel("claude-fable-5", "Claude Fable 5", 10, 50),
  freezeModel("claude-opus-4-8", "Claude Opus 4.8", 5, 25),
  freezeModel("claude-sonnet-5", "Claude Sonnet 5", 3, 15),
  freezeModel("claude-haiku-4-5-20251001", "Claude Haiku 4.5", 1, 5),
]);

/** @type {readonly ModelDefinition[]} */
const NO_MODELS = Object.freeze([]);

export const MODEL_PROVIDERS = Object.freeze([
  Object.freeze({ id: "openai", title: "OpenAI", defaultModel: "gpt-5.6-terra", models: OPENAI_MODELS }),
  Object.freeze({ id: "anthropic", title: "Anthropic", defaultModel: "claude-sonnet-5", models: ANTHROPIC_MODELS }),
]);

/** @param {unknown} value */
export function modelProvider(value) {
  if (typeof value !== "string") return null;
  const id = value.trim().toLowerCase();
  return MODEL_PROVIDERS.find((provider) => provider.id === id) ?? null;
}

/** @param {unknown} value */
export function defaultModelFor(value) {
  return modelProvider(value)?.defaultModel ?? "";
}

/** @param {unknown} value */
export function modelsForProvider(value) {
  return modelProvider(value)?.models ?? NO_MODELS;
}

/** @param {unknown} provider @param {unknown} model */
export function modelForProvider(provider, model) {
  if (typeof model !== "string") return null;
  const id = model.trim();
  return modelsForProvider(provider).find((candidate) => candidate.id === id) ?? null;
}

/** @param {ModelDefinition} model @param {unknown} locale */
export function modelOptionLabel(model, locale = "en") {
  const input = locale === "pt" ? "entrada" : "input";
  const output = locale === "pt" ? "saída" : "output";
  /** @param {number} value */
  const usd = (value) =>
    Number(value).toLocaleString("en-US", {
      minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
      maximumFractionDigits: 2,
    });
  return `${model.title} — ${input} $${usd(model.inputUsdPerMillion)} · ${output} $${usd(model.outputUsdPerMillion)} / 1M`;
}

/** @param {unknown} provider @param {unknown} model */
export function normalizeInferenceSelection(provider, model) {
  const definition = modelProvider(provider);
  if (!definition) throw new TypeError("Unsupported model provider");
  const selectedModel = String(model || definition.defaultModel).trim();
  if (!modelForProvider(definition.id, selectedModel)) throw new TypeError("Unsupported model for provider");
  return { provider: definition.id, model: selectedModel };
}

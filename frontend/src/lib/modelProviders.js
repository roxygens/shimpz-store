/**
 * @typedef {{id: string, title: string, inputUsdPerMillion: number, outputUsdPerMillion: number}} ModelDefinition
 */
import MODEL_CATALOG from "./modelCatalog.json" with { type: "json" };

/** @param {Record<string, number|string>} model */
const freezeModel = (model) => Object.freeze({
  id: String(model.id),
  title: String(model.title),
  inputUsdPerMillion: Number(model.input_usd_per_million_cents) / 100,
  outputUsdPerMillion: Number(model.output_usd_per_million_cents) / 100,
});

/** @type {readonly ModelDefinition[]} */
const NO_MODELS = Object.freeze([]);

export const MODEL_PROVIDERS = Object.freeze(MODEL_CATALOG.providers.map((provider) => Object.freeze({
  id: provider.id,
  title: provider.title,
  defaultModel: provider.default_model,
  models: Object.freeze(provider.models.map(freezeModel)),
})));

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

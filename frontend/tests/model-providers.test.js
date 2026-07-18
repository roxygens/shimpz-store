// @ts-nocheck -- executed by Node's built-in test runner; the browser bundle has no Node typings.
import assert from "node:assert/strict";
import test from "node:test";

import {
  MODEL_PROVIDERS,
  defaultModelFor,
  modelForProvider,
  modelOptionLabel,
  modelProvider,
  modelsForProvider,
  normalizeInferenceSelection,
} from "../src/lib/modelProviders.js";

test("model provider catalog exposes fixed models, prices and balanced defaults", () => {
  assert.deepEqual(
    MODEL_PROVIDERS.map(({ id, defaultModel }) => ({ id, defaultModel })),
    [
      { id: "openai", defaultModel: "gpt-5.6-terra" },
      { id: "anthropic", defaultModel: "claude-sonnet-5" },
    ],
  );
  assert.equal(defaultModelFor("ANTHROPIC"), "claude-sonnet-5");
  assert.equal(modelProvider("codex"), null);
  assert.deepEqual(
    modelsForProvider("openai").map(({ id, inputUsdPerMillion, outputUsdPerMillion }) => ({
      id,
      inputUsdPerMillion,
      outputUsdPerMillion,
    })),
    [
      { id: "gpt-5.6-sol", inputUsdPerMillion: 5, outputUsdPerMillion: 30 },
      { id: "gpt-5.6-terra", inputUsdPerMillion: 2.5, outputUsdPerMillion: 15 },
      { id: "gpt-5.6-luna", inputUsdPerMillion: 1, outputUsdPerMillion: 6 },
      { id: "gpt-5.5", inputUsdPerMillion: 5, outputUsdPerMillion: 30 },
    ],
  );
  assert.deepEqual(
    modelsForProvider("anthropic").map(({ id, inputUsdPerMillion, outputUsdPerMillion }) => ({
      id,
      inputUsdPerMillion,
      outputUsdPerMillion,
    })),
    [
      { id: "claude-fable-5", inputUsdPerMillion: 10, outputUsdPerMillion: 50 },
      { id: "claude-opus-4-8", inputUsdPerMillion: 5, outputUsdPerMillion: 25 },
      { id: "claude-sonnet-5", inputUsdPerMillion: 3, outputUsdPerMillion: 15 },
      { id: "claude-haiku-4-5-20251001", inputUsdPerMillion: 1, outputUsdPerMillion: 5 },
    ],
  );
  assert.equal(
    modelOptionLabel(modelForProvider("openai", "gpt-5.6-terra"), "en"),
    "GPT-5.6 Terra — input $2.50 · output $15 / 1M",
  );
  assert.equal(
    modelOptionLabel(modelForProvider("openai", "gpt-5.6-terra"), "pt"),
    "GPT-5.6 Terra — entrada $2.50 · saída $15 / 1M",
  );
  assert.ok(Object.isFrozen(MODEL_PROVIDERS));
  assert.ok(Object.isFrozen(modelsForProvider("openai")));
});

test("inference selection accepts only a model from its provider catalog", () => {
  assert.deepEqual(normalizeInferenceSelection("openai", ""), {
    provider: "openai",
    model: "gpt-5.6-terra",
  });
  assert.deepEqual(normalizeInferenceSelection("anthropic", "claude-haiku-4-5-20251001"), {
    provider: "anthropic",
    model: "claude-haiku-4-5-20251001",
  });
  assert.throws(() => normalizeInferenceSelection("claude-code", "claude-sonnet-5"));
  assert.throws(() => normalizeInferenceSelection("anthropic", "gpt-5.5"));
  assert.throws(() => normalizeInferenceSelection("openai", "vendor/model-v2"));
  assert.throws(() => normalizeInferenceSelection("openai", "bad model"));
});

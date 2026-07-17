import assert from "node:assert/strict";
import test from "node:test";

import {
  MODEL_PROVIDERS,
  defaultModelFor,
  modelProvider,
  normalizeInferenceSelection,
} from "../src/lib/modelProviders.js";

test("model provider catalog exposes the controller defaults", () => {
  assert.deepEqual(
    MODEL_PROVIDERS.map(({ id, defaultModel }) => ({ id, defaultModel })),
    [
      { id: "openai", defaultModel: "gpt-5.5" },
      { id: "anthropic", defaultModel: "claude-sonnet-5" },
    ],
  );
  assert.equal(defaultModelFor("ANTHROPIC"), "claude-sonnet-5");
  assert.equal(modelProvider("codex"), null);
});

test("inference selection accepts safe provider model IDs and rejects legacy or unsafe values", () => {
  assert.deepEqual(normalizeInferenceSelection("openai", ""), {
    provider: "openai",
    model: "gpt-5.5",
  });
  assert.deepEqual(normalizeInferenceSelection("anthropic", "vendor/model-v2"), {
    provider: "anthropic",
    model: "vendor/model-v2",
  });
  assert.throws(() => normalizeInferenceSelection("claude-code", "claude-sonnet-5"));
  assert.throws(() => normalizeInferenceSelection("openai", "bad model"));
});

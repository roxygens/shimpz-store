// @ts-nocheck -- executed by Node's built-in test runner; the browser bundle has no Node typings.
import assert from "node:assert/strict";
import test from "node:test";

import { ASSISTANT_BY_ID, SERVICE_BY_ID } from "../src/lib/catalog.ts";

test("Shimpz Assistant exposes its canonical release version", () => {
  assert.equal(ASSISTANT_BY_ID.get("shimpz-assistant")?.version, "0.2.0");
});

test("OpenAI media Service publishes only its implemented operations", () => {
  const service = SERVICE_BY_ID.get("openai");

  assert.ok(service);
  assert.deepEqual(service.summary, {
    en: "Audited image, transcription, and speech operations.",
    pt: "Operações auditadas de imagem, transcrição e voz.",
  });
  assert.deepEqual(service.blurb, {
    en: "The audited OpenAI media sidecar implements allow-listed image generation, speech-to-text transcription, and text-to-speech. These operations are not yet exposed through an Assistant Power.",
    pt: "O sidecar auditado de mídia OpenAI implementa geração de imagens, transcrição de voz em texto e conversão de texto em voz permitidas. Essas operações ainda não são expostas por um Power de Assistant.",
  });
  assert.deepEqual(service.features, [
    { en: "Image generation (gpt-image)", pt: "Geração de imagens (gpt-image)" },
    { en: "Speech-to-text transcription", pt: "Transcrição de fala para texto" },
    { en: "Text-to-speech voice", pt: "Voz de texto para fala" },
  ]);
  assert.deepEqual(service.boundaries, [
    {
      en: "Every request is audited; the media API key remains inside the sidecar",
      pt: "Toda requisição é auditada; a chave de API de mídia permanece dentro do sidecar",
    },
    {
      en: "No Assistant Power or Assistant route exposes these operations yet",
      pt: "Nenhum Power nem rota de Assistant expõe essas operações ainda",
    },
    {
      en: "Only allow-listed image, transcription and speech operations are accepted",
      pt: "Somente operações permitidas de imagem, transcrição e fala são aceitas",
    },
  ]);
});

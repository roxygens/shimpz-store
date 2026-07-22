// @ts-nocheck -- executed by Node's built-in test runner; the browser bundle has no Node typings.
import assert from "node:assert/strict";
import test from "node:test";

import { ASSISTANT_BY_ID, SERVICES } from "../src/lib/catalog.ts";

test("Shimpz Assistant exposes its canonical Account and Secret contract", () => {
  const assistant = ASSISTANT_BY_ID.get("shimpz-assistant");

  assert.ok(assistant);
  assert.equal(assistant.version, "0.6.0");
  assert.deepEqual(
    assistant.powers.map((power) => power.id),
    [
      "public-user-lookup",
      "identity-me",
      "create-post",
      "delete-post",
      "list-direct-uploads",
      "create-test-direct-upload",
      "cancel-direct-upload",
      "verify-mux-webhook",
    ],
  );
  assert.match(assistant.summary.en, /X Accounts/);
  assert.match(assistant.summary.en, /Mux BYOK Secrets/);
  assert.match(assistant.description.en, /api\.x\.com/);
  assert.match(assistant.description.en, /api\.mux\.com/);
  assert.match(assistant.description.en, /without network access/);
  assert.deepEqual(assistant.permissions, [
    {
      en: "Allowed hosts: api.x.com and api.mux.com only",
      pt: "Hosts permitidos: somente api.x.com e api.mux.com",
    },
    {
      en: "Account: controller-owned X OAuth 2.0 with S256 PKCE; its token reaches only the declared X Power invocation",
      pt: "Account: OAuth 2.0 do X com S256 PKCE sob custódia do controller; seu token chega somente à execução do Power do X declarado",
    },
    {
      en: "Secrets: Mux Token ID, Token Secret and Webhook Signing Secret are requested just in time and injected only into the declaring Power",
      pt: "Secrets: Token ID, Token Secret e Webhook Signing Secret do Mux são solicitados sob demanda e injetados somente no Power que os declara",
    },
    {
      en: "Approval: required for every Post create/delete and Mux upload create/cancel invocation",
      pt: "Aprovação: obrigatória para cada criação/exclusão de Post e criação/cancelamento de upload do Mux",
    },
  ]);
});

test("Cloudflare Assistant exposes only its least-privilege read contract", () => {
  const assistant = ASSISTANT_BY_ID.get("shimpz-cloudflare");

  assert.ok(assistant);
  assert.equal(assistant.version, "0.1.1");
  assert.deepEqual(assistant.powers.map((power) => power.id), ["list-zones", "list-dns-records"]);
  assert.match(assistant.description.en, /api\.cloudflare\.com/);
  assert.match(assistant.permissions[1].en, /zone\.read, dns\.read and offline_access/);
  assert.match(assistant.permissions[2].en, /read-only/);
});

test("PostgreSQL is the only published Service", () => {
  assert.deepEqual(SERVICES.map((service) => service.id), ["postgres"]);
});

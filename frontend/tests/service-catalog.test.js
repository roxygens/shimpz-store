// @ts-nocheck -- executed by Node's built-in test runner; the browser bundle has no Node typings.
import assert from "node:assert/strict";
import test from "node:test";

import { ASSISTANT_BY_ID, SERVICES } from "../src/lib/catalog.ts";

test("Cloudflare is the sole Assistant and exposes only its least-privilege read contract", () => {
  assert.deepEqual([...ASSISTANT_BY_ID.keys()], ["shimpz-cloudflare"]);
  const assistant = ASSISTANT_BY_ID.get("shimpz-cloudflare");

  assert.ok(assistant);
  assert.equal(assistant.version, "0.1.5");
  assert.deepEqual(assistant.powers.map((power) => power.id), ["list-zones", "list-dns-records"]);
  assert.match(assistant.description.en, /api\.cloudflare\.com/);
  assert.match(assistant.permissions[1].en, /zone\.read, dns\.read and offline_access/);
  assert.match(assistant.permissions[2].en, /read-only/);
});

test("PostgreSQL is the only published Service", () => {
  assert.deepEqual(SERVICES.map((service) => service.id), ["postgres"]);
});

// @ts-nocheck -- executed by Node's built-in test runner; the browser bundle has no Node typings.
import assert from "node:assert/strict";
import test from "node:test";

import {
  CLOUD_ASSISTANT_LIMIT,
  CLOUD_TEAM_LIMIT,
  assistantStoreMode,
  closedAssistantTeamHref,
  closedAssistantLoginHref,
  closedAssistantStoreHref,
  cloudAssistantAction,
  cloudRequestIsCurrent,
  cloudStoreCanStart,
  parseCloudAccount,
  parseCloudAssistantInventory,
  parseCloudTeams,
  requestedAssistantFromSearch,
  resolveClosedAssistantReturn,
  selectCloudTeam,
} from "../src/lib/cloudAssistantLifecycle.js";

test("selects the Store runtime mode only from the dedicated route context", () => {
  assert.equal(assistantStoreMode(true), "self-hosted");
  assert.equal(assistantStoreMode(false), "cloud");
  assert.equal(cloudStoreCanStart("cloud", true), true);
  assert.equal(cloudStoreCanStart("cloud", false), false);
  assert.equal(cloudStoreCanStart("self-hosted", true), false);
  for (const value of [undefined, null, "false", 0]) assert.throws(() => assistantStoreMode(value));
  assert.throws(() => cloudStoreCanStart("cloud", "yes"));
});

test("projects a bounded canonical cloud Team selector", () => {
  const teams = parseCloudTeams({
    teams: [
      { team_id: "abc123_workspace", team_name: "Workspace", status: "running", private: "ignored" },
      { team_id: "def456_sales", team_name: "Sales", provider: "openai" },
    ],
    upstreamMetadata: "ignored",
  });
  assert.deepEqual(teams, [
    { team_id: "abc123_workspace", team_name: "Workspace" },
    { team_id: "def456_sales", team_name: "Sales" },
  ]);
  assert.equal(selectCloudTeam(teams, "def456_sales"), "def456_sales");
  assert.equal(selectCloudTeam(teams, "unknown"), "");

  for (const value of [
    null,
    {},
    { teams: "many" },
    { teams: [{ team_id: "../../escape", team_name: "Bad" }] },
    { teams: [{ team_id: "valid", team_name: "One" }, { team_id: "valid", team_name: "Two" }] },
    { teams: [{ team_id: "valid", team_name: " padded " }] },
    { teams: [{ team_id: "valid" }] },
    { teams: Array.from({ length: CLOUD_TEAM_LIMIT + 1 }, (_, index) => ({ team_id: `team_${index}`, team_name: `Team ${index}` })) },
  ]) {
    assert.throws(() => parseCloudTeams(value));
  }
});

test("accepts only an explicit account state and exact bounded Assistant inventory", () => {
  assert.deepEqual(parseCloudAccount({ authenticated: true, username: "captain" }), { authenticated: true });
  assert.deepEqual(parseCloudAssistantInventory({ installed: ["shimpz-assistant"] }), ["shimpz-assistant"]);
  for (const value of [null, {}, { authenticated: "yes" }]) assert.throws(() => parseCloudAccount(value));
  for (const value of [
    null,
    {},
    { installed: "shimpz-assistant" },
    { installed: ["shimpz-assistant", "shimpz-assistant"] },
    { installed: ["../hello"] },
    { installed: [], team_id: "private" },
    { installed: Array.from({ length: CLOUD_ASSISTANT_LIMIT + 1 }, (_, index) => `assistant-${index}`) },
  ]) {
    assert.throws(() => parseCloudAssistantInventory(value));
  }
});

test("derives one contextual action only from authoritative selected-Team state", () => {
  assert.equal(cloudAssistantAction(true, [], "shimpz-assistant"), "install");
  assert.equal(cloudAssistantAction(true, ["shimpz-assistant"], "shimpz-assistant"), "uninstall");
  assert.equal(cloudAssistantAction(false, ["shimpz-assistant"], "shimpz-assistant"), "blocked");
  assert.equal(cloudAssistantAction(true, [], "unknown"), "blocked");
});

test("rejects stale inventory and mutation completions after a Team switch", () => {
  assert.equal(cloudRequestIsCurrent(4, 4, "team_one", "team_one"), true);
  assert.equal(cloudRequestIsCurrent(3, 4, "team_one", "team_one"), false);
  assert.equal(cloudRequestIsCurrent(4, 4, "team_one", "team_two"), false);
  assert.equal(cloudRequestIsCurrent(Number.NaN, Number.NaN, "team_one", "team_one"), false);
});

test("uses a closed Store/login return enum and never accepts an arbitrary redirect", () => {
  assert.equal(closedAssistantStoreHref("en", "shimpz-assistant"), "/en/assistants?assistant=shimpz-assistant");
  assert.equal(
    closedAssistantLoginHref("pt", "shimpz-assistant"),
    "/pt/login?return=assistants&assistant=shimpz-assistant",
  );
  assert.equal(
    closedAssistantTeamHref("en", "shimpz-assistant"),
    "/en/team?return=assistants&assistant=shimpz-assistant",
  );
  assert.equal(
    resolveClosedAssistantReturn("en", "?return=assistants&assistant=shimpz-assistant"),
    "/en/assistants?assistant=shimpz-assistant",
  );
  for (const search of [
    "?return=https://evil.example&assistant=shimpz-assistant",
    "?return=assistants&assistant=unknown",
    "?return=assistants&assistant=shimpz-assistant&next=https://evil.example",
    "?return=assistants&return=assistants&assistant=shimpz-assistant",
  ]) {
    assert.equal(resolveClosedAssistantReturn("en", search), null);
  }
  assert.equal(requestedAssistantFromSearch("?assistant=shimpz-assistant"), "shimpz-assistant");
  assert.equal(requestedAssistantFromSearch("?assistant=shimpz-assistant&install=true"), "");
  assert.equal(requestedAssistantFromSearch("?assistant=unknown"), "");
  assert.throws(() => closedAssistantStoreHref("en", "unknown"));
  assert.throws(() => closedAssistantLoginHref("xx", "shimpz-assistant"));
  assert.throws(() => closedAssistantTeamHref("en", "unknown"));
});

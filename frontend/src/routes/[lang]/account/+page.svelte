<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import Seo from "$lib/components/Seo.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);

  let me = $state<any>(null);
  let ready = $state(false);
  let busy = $state(false);
  const providers = [
    { id: "claude-code", title: "Claude Code" },
    { id: "codex", title: "Codex" },
  ];
  let brains = $state<any[]>([]);
  let brainSecrets = $state<Record<string, string>>({ "claude-code": "", codex: "" });
  let brainAuth = $state<Record<string, string>>({ "claude-code": "api_key", codex: "api_key" });
  let brainBusy = $state("");
  let brainMessage = $state<Record<string, string>>({});

  async function loadBrains() {
    const r = await fetch("/api/brains").catch(() => null);
    if (!r?.ok) return false;
    const result = await r.json().catch(() => null);
    if (!result) return false;
    brains = result.brains ?? [];
    return true;
  }

  onMount(async () => {
    const d = await fetch("/api/me").then((r) => r.json()).catch(() => ({}));
    if (!d.authenticated) {
      goto(u.login(lang)); // account is behind auth
      return;
    }
    me = d;
    await loadBrains();
    ready = true;
  });

  function configured(provider: string) {
    return brains.some((entry) => entry.provider === provider && entry.status === "configured");
  }

  function revoking(provider: string) {
    return brains.some((entry) => entry.provider === provider && entry.status === "revoking");
  }

  function removable(provider: string) {
    return configured(provider) || revoking(provider);
  }

  function removalPendingLabel() {
    return lang === "pt" ? "Remoção pendente" : "Removal pending";
  }

  function retryRemovalLabel() {
    return lang === "pt" ? "Tentar remoção novamente" : "Retry removal";
  }

  async function applyBrainToCapsules(provider: string): Promise<boolean> {
    const r = await fetch("/api/capsules").catch(() => null);
    if (!r?.ok) return false;
    const caps = (await r.json()).capsules ?? [];
    const results = await Promise.all(
      caps
        .filter((capsule: any) => (capsule.brain ?? "claude-code") === provider)
        .map((capsule: any) =>
          fetch(`/api/capsules/${capsule.id}/brain/configure`, { method: "POST" }).catch(() => null),
        ),
    );
    return results.every((result) => result?.ok);
  }

  async function saveBrain(provider: string) {
    const secret = brainSecrets[provider]?.trim();
    if (!secret || brainBusy) return;
    brainBusy = provider;
    brainMessage[provider] = "";
    try {
      const r = await fetch(`/api/brains/${provider}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ auth_type: brainAuth[provider], secret }),
      });
      const result = await r.json().catch(() => ({}));
      if (!r.ok) {
        brainMessage[provider] = result.detail ?? result.error ?? "save failed";
        return;
      }
      brainSecrets[provider] = "";
      await loadBrains();
      const applied = await applyBrainToCapsules(provider);
      brainMessage[provider] = tr(applied ? "brain_saved" : "brain_saved_apply_failed", lang);
    } finally {
      brainBusy = "";
    }
  }

  async function removeBrain(provider: string) {
    if (brainBusy) return;
    brainBusy = provider;
    brainMessage[provider] = "";
    try {
      const r = await fetch(`/api/brains/${provider}`, { method: "DELETE" }).catch(() => null);
      const result = await r?.json().catch(() => ({}));
      if (!r?.ok) {
        await loadBrains();
        brainMessage[provider] = result?.detail ?? result?.error ?? "remove failed";
        return;
      }
      await loadBrains();
      brainMessage[provider] = tr("brain_removed", lang);
    } finally {
      brainBusy = "";
    }
  }

  async function logout() {
    busy = true;
    await fetch("/api/logout", { method: "POST" }).catch(() => null);
    localStorage.removeItem("shimpz_current_capsule");
    localStorage.removeItem("shimpz_current_capsule_name");
    goto(u.home(lang));
  }
</script>

<Seo title={`${tr("account_title", lang)} · Shimpz`} description={tr("account_lead", lang)} {lang} />

<section class="wrap max-w-2xl pt-10 pb-8">
  <h1 class="text-4xl font-extrabold tracking-tight sm:text-5xl">{tr("account_title", lang)}</h1>
  <p class="mt-3 dim">{tr("account_lead", lang)}</p>

  {#if !ready}
    <p class="mt-8 dim">…</p>
  {:else}
    <div class="mt-8 flex items-center gap-4">
      <div class="app-icon grid size-16 shrink-0 place-items-center" style="--g1:var(--color-cyan);--g2:var(--color-magenta);font-size:26px">{(me.username?.[0] ?? "?").toUpperCase()}</div>
      <div class="min-w-0">
        <div class="text-xl font-semibold">{me.username}</div>
        <div class="mono truncate text-xs dim">{tr("logged_in_as", lang)} @{me.username}</div>
      </div>
    </div>

    <div class="panel mt-8">
      <span class="kicker">{tr("account_profile", lang)}</span>
      <dl class="mt-4 space-y-3 text-sm">
        <div class="flex items-center justify-between gap-4 border-b hair pb-3">
          <dt class="dim">{tr("username", lang)}</dt>
          <dd class="mono">{me.username}</dd>
        </div>
        <div class="flex items-center justify-between gap-4">
          <dt class="dim">{tr("account_id_label", lang)}</dt>
          <dd class="mono min-w-0 truncate">{me.account_id}</dd>
        </div>
      </dl>
    </div>

    <div class="panel mt-6">
      <span class="kicker">{tr("account_brains", lang)}</span>
      <p class="mt-3 text-sm leading-relaxed dim">{tr("account_brains_lead", lang)}</p>
      <div class="mt-5 space-y-5">
        {#each providers as provider (provider.id)}
          <div class="rounded-xl border hair p-4">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div class="font-semibold">{provider.title}</div>
              <span
                class="badge"
                style:color={configured(provider.id) ? "var(--color-primary)" : "var(--color-magenta)"}
              >
                {#if revoking(provider.id)}
                  {removalPendingLabel()}
                {:else if configured(provider.id)}
                  {tr("brain_configured", lang)}
                {:else}
                  {tr("brain_not_configured", lang)}
                {/if}
              </span>
            </div>
            <label class="mt-4 block">
              <span class="kicker !text-[10px]">{tr("brain_auth_type", lang)}</span>
              <select class="field field-sm mt-2" bind:value={brainAuth[provider.id]}>
                <option value="api_key">{tr("brain_api_key", lang)}</option>
                <option value="oauth">{tr("brain_oauth", lang)}</option>
              </select>
            </label>
            <label class="mt-3 block">
              <span class="kicker !text-[10px]">{tr("brain_secret", lang)}</span>
              <textarea
                class="field mt-2 min-h-24 resize-y"
                autocomplete="off"
                spellcheck="false"
                bind:value={brainSecrets[provider.id]}
              ></textarea>
              <span class="mt-2 block text-xs dim">
                {tr(brainAuth[provider.id] === "oauth" ? "brain_secret_oauth_help" : "brain_secret_api_help", lang)}
              </span>
            </label>
            <div class="mt-4 flex flex-wrap items-center gap-3">
              <button
                class="btn-primary !py-2 text-sm"
                disabled={brainBusy !== "" || !brainSecrets[provider.id]?.trim()}
                onclick={() => saveBrain(provider.id)}>{tr("brain_save", lang)}</button>
              {#if removable(provider.id)}
                <button
                  class="btn-ghost !py-2 text-sm"
                  disabled={brainBusy !== ""}
                  onclick={() => removeBrain(provider.id)}
                >{revoking(provider.id) ? retryRemovalLabel() : tr("brain_remove", lang)}</button>
              {/if}
              {#if brainMessage[provider.id]}
                <span class="text-xs dim" aria-live="polite">{brainMessage[provider.id]}</span>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    </div>

    <div class="panel mt-6">
      <span class="kicker">{tr("account_session", lang)}</span>
      <div class="mt-4 flex flex-wrap gap-3">
        <a href={u.capsule(lang)} class="btn-ghost !py-2 text-sm">{tr("my_capsules", lang)} →</a>
        <button
          class="btn-ghost !py-2 text-sm"
          style="color:var(--color-magenta);box-shadow:inset 0 0 0 1px color-mix(in oklab, var(--color-magenta) 45%, transparent)"
          disabled={busy}
          onclick={logout}>{tr("log_out", lang)}</button>
      </div>
    </div>
  {/if}
</section>

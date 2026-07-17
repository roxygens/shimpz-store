<script lang="ts">
  import { onMount } from "svelte";
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { MODEL_PROVIDERS } from "$lib/modelProviders.js";
  import { u } from "$lib/url";
  import HudIcon from "$lib/components/HudIcon.svelte";

  type ProviderId = "anthropic" | "openai";
  type LoadState = "loading" | "ready" | "error";
  type BrainRecord = {
    provider: ProviderId;
    auth_type: "api_key";
    status: "configured" | "revoking";
  };

  let { lang }: { lang: Locale } = $props();

  let loadState = $state<LoadState>("loading");
  let brains = $state<BrainRecord[]>([]);
  let provider = $state<ProviderId>("openai");
  let step = $state<1 | 2 | 3>(1);
  let secret = $state("");
  let reveal = $state(false);
  let busy = $state(false);
  let message = $state("");
  let messageTone = $state<"" | "error" | "success">("");
  let confirmRemove = $state<ProviderId | "">("");
  let fieldError = $state("");

  function recordFor(id: ProviderId) {
    return brains.find((entry) => entry.provider === id);
  }

  function providerTitle(id: ProviderId) {
    return MODEL_PROVIDERS.find((entry) => entry.id === id)?.title ?? id;
  }

  function statusLabel(id: ProviderId) {
    const record = recordFor(id);
    if (record?.status === "revoking") return lang === "pt" ? "Remoção pendente" : "Removal pending";
    return tr(record?.status === "configured" ? "brain_configured" : "brain_not_configured", lang);
  }

  async function load({ preserveMessage = false }: { preserveMessage?: boolean } = {}) {
    loadState = "loading";
    if (!preserveMessage) message = "";
    try {
      const response = await fetch("/api/brains");
      const result = await response.json().catch(() => null);
      if (!response.ok || !Array.isArray(result?.brains)) throw new Error("providers unavailable");
      brains = result.brains.filter(
        (entry: BrainRecord) => entry?.provider === "openai" || entry?.provider === "anthropic",
      );
      loadState = "ready";
    } catch {
      loadState = "error";
    }
  }

  function chooseProvider(id: string) {
    if (id !== "openai" && id !== "anthropic") return;
    provider = id;
    secret = "";
    reveal = false;
    fieldError = "";
    message = "";
    messageTone = "";
    step = 2;
  }

  async function save() {
    if (busy) return;
    const value = secret.trim();
    if (!value) {
      fieldError = tr("brain_secret_required", lang);
      return;
    }
    busy = true;
    message = "";
    messageTone = "";
    try {
      const response = await fetch(`/api/brains/${provider}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ auth_type: "api_key", secret: value }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        message = result.detail ?? result.error ?? (lang === "pt" ? "Não foi possível salvar a chave." : "Could not save the key.");
        messageTone = "error";
        return;
      }
      secret = "";
      reveal = false;
      await load({ preserveMessage: true });
      message = tr("brain_saved", lang);
      messageTone = "success";
      step = 3;
    } finally {
      busy = false;
    }
  }

  async function remove(id: ProviderId) {
    if (busy) return;
    const existing = recordFor(id);
    if (existing?.status !== "revoking" && confirmRemove !== id) {
      confirmRemove = id;
      return;
    }
    busy = true;
    message = "";
    messageTone = "";
    try {
      const response = await fetch(`/api/brains/${id}`, { method: "DELETE" }).catch(() => null);
      const result = await response?.json().catch(() => ({}));
      if (!response?.ok) {
        message = result?.detail ?? result?.error ?? (lang === "pt" ? "Não foi possível remover a chave." : "Could not remove the key.");
        messageTone = "error";
      } else {
        message = tr("brain_removed", lang);
        messageTone = "success";
      }
      confirmRemove = "";
      await load({ preserveMessage: true });
      step = 1;
    } finally {
      busy = false;
    }
  }

  onMount(load);
</script>

<section class="brain-console panel" aria-labelledby="brain-wizard-title">
  <header class="console-head">
    <div class="console-mark"><HudIcon name="brain" size={25} /></div>
    <div>
      <p class="kicker">{tr("account_brains", lang)}</p>
      <h2 id="brain-wizard-title">{tr("brain_wizard_title", lang)}</h2>
      <p>{tr("brain_wizard_lead", lang)}</p>
    </div>
  </header>

  {#if loadState === "loading"}
    <p class="loading" role="status">{tr("loading", lang)}</p>
  {:else if loadState === "error"}
    <div class="notice notice-error state-notice" role="alert">
      <span>{tr("brain_load_failed", lang)}</span>
      <button class="btn-ghost compact" type="button" onclick={() => load()}>
        <HudIcon name="retry" size={15} /> {tr("brain_retry_load", lang)}
      </button>
    </div>
  {:else}
    <ol class="stepper" aria-label={tr("brain_wizard_title", lang)}>
      {#each [tr("brain_step_provider", lang), tr("brain_step_credential", lang)] as label, index (label)}
        <li class:active={step === index + 1} class:complete={step > index + 1} aria-current={step === index + 1 ? "step" : undefined}>
          <span>{String(index + 1).padStart(2, "0")}</span>{label}
        </li>
      {/each}
    </ol>

    <div class="stage">
      {#if step === 1}
        <div class="stage-copy">
          <h3>{tr("brain_choose_provider", lang)}</h3>
          <p>{tr("brain_choose_provider_help", lang)}</p>
        </div>
        <div class="option-grid">
          {#each MODEL_PROVIDERS as option (option.id)}
            <button class="option" type="button" onclick={() => chooseProvider(option.id)}>
              <span class="option-icon"><HudIcon name="brain" size={22} /></span>
              <span class="option-copy"><strong>{option.title}</strong><small>{option.defaultModel}</small></span>
              <span class="badge" class:ready={recordFor(option.id as ProviderId)?.status === "configured"}>{statusLabel(option.id as ProviderId)}</span>
            </button>
          {/each}
        </div>
      {:else if step === 2}
        <div class="stage-copy">
          <p class="selection">{providerTitle(provider)} // {tr("brain_api_key", lang)}</p>
          <h3>{tr("brain_credential_title", lang)}</h3>
          <p>{tr("brain_credential_review", lang)}</p>
        </div>
        <label class="credential-field">
          <span class="kicker">{tr("brain_secret", lang)}</span>
          <span class="secret-input">
            <input
              class="field"
              type={reveal ? "text" : "password"}
              autocomplete="off"
              spellcheck="false"
              bind:value={secret}
              oninput={() => (fieldError = "")} />
            <button type="button" onclick={() => (reveal = !reveal)}>{tr(reveal ? "password_hide" : "password_show", lang)}</button>
          </span>
          <small>{tr("brain_secret_api_help", lang)}</small>
        </label>
        {#if fieldError}<p class="field-error" role="alert">{fieldError}</p>{/if}
        {#if message}<p class="notice state-notice notice-error" role="alert">{message}</p>{/if}
        <div class="stage-actions">
          <button class="btn-ghost compact" type="button" disabled={busy} onclick={() => (step = 1)}>{tr("brain_back", lang)}</button>
          <button class="btn-primary compact" type="button" disabled={busy || !secret.trim()} onclick={save}>
            {#if busy}{tr("brain_saving", lang)}{:else}<HudIcon name="shield" size={16} /> {tr("brain_save", lang)}{/if}
          </button>
        </div>
      {:else}
        <div class="done-mark"><HudIcon name="check" size={30} /></div>
        <div class="stage-copy done-copy">
          <h3>{tr("brain_done_title", lang)}</h3>
          <p>{tr("brain_done_body", lang)}</p>
        </div>
        {#if message}<p class="notice state-notice notice-success" role="status">{message}</p>{/if}
        <div class="stage-actions done-actions">
          <button class="btn-ghost compact" type="button" onclick={() => { message = ""; step = 1; }}>{tr("brain_reconfigure", lang)}</button>
          <a class="btn-primary compact" href={u.capsule(lang)}>{tr("my_capsules", lang)} →</a>
        </div>
      {/if}
    </div>

    <div class="configured-list">
      <h3>{tr("brain_configured_list", lang)}</h3>
      {#if brains.length === 0}
        <p>{tr("brain_none_configured", lang)}</p>
      {:else}
        {#each brains as entry (entry.provider)}
          <div class="configured-row">
            <span class="configured-icon"><HudIcon name="brain" size={18} /></span>
            <span class="configured-name"><strong>{providerTitle(entry.provider)}</strong><small>{tr("brain_api_key", lang)}</small></span>
            <span class="badge" class:ready={entry.status === "configured"}>{statusLabel(entry.provider)}</span>
            <button class="btn-ghost row-action" type="button" disabled={busy || entry.status === "revoking"} onclick={() => chooseProvider(entry.provider)}>{tr("brain_reconfigure", lang)}</button>
            <button class="btn-danger row-action" type="button" disabled={busy} onclick={() => remove(entry.provider)}>
              {entry.status === "revoking" ? (lang === "pt" ? "Tentar remoção" : "Retry removal") : tr("brain_remove", lang)}
            </button>
            {#if confirmRemove === entry.provider && entry.status !== "revoking"}
              <div class="remove-confirm">
                <span>{tr("brain_remove_confirm", lang)}</span>
                <button class="btn-danger row-action" type="button" onclick={() => remove(entry.provider)}>{tr("brain_remove", lang)}</button>
                <button class="btn-ghost row-action" type="button" onclick={() => (confirmRemove = "")}>{tr("brain_cancel", lang)}</button>
              </div>
            {/if}
          </div>
        {/each}
      {/if}
      {#if message && step === 1}
        <p class="notice state-notice" class:notice-error={messageTone === "error"} class:notice-success={messageTone === "success"} role={messageTone === "error" ? "alert" : "status"}>{message}</p>
      {/if}
    </div>
  {/if}
</section>

<style>
  .brain-console { padding: clamp(1.1rem, 3vw, 1.6rem); }
  .console-head { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 1rem; align-items: start; }
  .console-mark,
  .option-icon,
  .configured-icon,
  .done-mark { display: grid; place-items: center; color: var(--color-cyan); background: #000; box-shadow: inset 0 0 0 1px var(--color-border-strong); clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px); }
  .console-mark { width: 3.1rem; height: 3.1rem; }
  .console-head h2 { margin: 0.15rem 0 0; font-size: clamp(1.35rem, 3vw, 1.8rem); }
  .console-head p:last-child { max-width: 42rem; margin: 0.4rem 0 0; color: var(--color-muted); font-size: 0.85rem; line-height: 1.6; }
  .loading { margin: 2rem 0 0; color: var(--color-muted); }
  .stepper { display: grid; grid-template-columns: repeat(2, 1fr); margin: 1.5rem 0 0; padding: 0; list-style: none; }
  .stepper li { display: flex; min-width: 0; align-items: center; gap: 0.5rem; border-bottom: 1px solid var(--color-border); padding: 0.65rem 0.35rem; color: var(--color-muted-2); font-family: var(--font-mono); font-size: 0.62rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
  .stepper li.active { border-color: var(--color-cyan); color: var(--color-fg); }
  .stepper li.active span,
  .stepper li.complete span { color: var(--color-cyan); }
  .stage { min-height: 17rem; padding: clamp(1.2rem, 3vw, 1.8rem) 0 1.25rem; }
  .stage-copy h3 { margin: 0; font-size: clamp(1.15rem, 2.5vw, 1.45rem); }
  .stage-copy > p:not(.selection) { max-width: 42rem; margin: 0.45rem 0 0; color: var(--color-muted); font-size: 0.85rem; }
  .selection { margin: 0 0 0.45rem; color: var(--color-cyan); font-family: var(--font-mono); font-size: 0.68rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
  .option-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; margin-top: 1.15rem; }
  .option { display: grid; min-width: 0; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 0.8rem; border: 0; padding: 0.9rem; background: #000; box-shadow: inset 0 0 0 1px var(--color-border); color: var(--color-fg); cursor: pointer; text-align: left; clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px); }
  .option:hover { box-shadow: inset 0 0 0 1px var(--color-cyan); }
  .option-icon { width: 2.5rem; height: 2.5rem; }
  .option-copy strong,
  .option-copy small { display: block; }
  .option-copy strong { font-family: var(--font-mono); font-size: 0.88rem; }
  .option-copy small { margin-top: 0.2rem; color: var(--color-muted); font-size: 0.68rem; }
  .badge.ready { color: var(--color-green); }
  .stage-actions { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 0.65rem; margin-top: 1.15rem; }
  .compact { min-height: 2.5rem; padding: 0.55rem 0.85rem; font-size: 0.7rem; }
  .credential-field { display: block; margin-top: 1.1rem; }
  .credential-field small { display: block; margin-top: 0.45rem; color: var(--color-muted); font-size: 0.7rem; }
  .secret-input { position: relative; display: block; margin-top: 0.45rem; }
  .secret-input input { padding-right: 5.5rem; }
  .secret-input button { position: absolute; top: 50%; right: 0.65rem; border: 0; padding: 0.4rem; background: transparent; color: var(--color-cyan); cursor: pointer; font-family: var(--font-mono); font-size: 0.65rem; text-transform: uppercase; transform: translateY(-50%); }
  .field-error { margin: 0.65rem 0 0; color: var(--color-danger); font-size: 0.75rem; }
  .state-notice { margin-top: 0.9rem; padding: 0.75rem 0.9rem; font-size: 0.75rem; }
  .state-notice:not(p) { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.75rem; }
  .done-mark { width: 3.5rem; height: 3.5rem; margin: 0 auto; color: var(--color-green); }
  .done-copy { margin-top: 0.9rem; text-align: center; }
  .done-copy p { margin-inline: auto !important; }
  .done-actions { justify-content: center; }
  .configured-list { border-top: 1px solid var(--color-border); padding-top: 1rem; }
  .configured-list > h3 { margin: 0 0 0.7rem; color: var(--color-muted); font-size: 0.75rem; letter-spacing: 0.08em; text-transform: uppercase; }
  .configured-list > p:not(.notice) { margin: 0; color: var(--color-muted); font-size: 0.8rem; }
  .configured-row { position: relative; display: grid; grid-template-columns: auto minmax(7rem, 1fr) auto auto auto; align-items: center; gap: 0.55rem; border-top: 1px solid var(--color-border); padding: 0.65rem 0; }
  .configured-row:first-of-type { border-top: 0; }
  .configured-icon { width: 2rem; height: 2rem; }
  .configured-name strong,
  .configured-name small { display: block; }
  .configured-name strong { font-family: var(--font-mono); font-size: 0.8rem; }
  .configured-name small { color: var(--color-muted); font-size: 0.65rem; }
  .row-action { min-height: 2rem; padding: 0.35rem 0.55rem; font-size: 0.58rem; }
  .remove-confirm { grid-column: 1 / -1; display: flex; flex-wrap: wrap; align-items: center; gap: 0.55rem; padding: 0.7rem; background: color-mix(in oklab, var(--color-danger) 7%, #000); box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--color-danger) 40%, var(--color-border)); color: var(--color-danger); font-size: 0.72rem; }
  .remove-confirm span { flex: 1 1 18rem; }

  @media (max-width: 720px) {
    .option-grid { grid-template-columns: 1fr; }
    .configured-row { grid-template-columns: auto minmax(0, 1fr) auto; }
    .configured-row > .row-action { grid-row: 2; }
  }
  @media (max-width: 480px) {
    .console-head { grid-template-columns: 1fr; }
    .stepper li { align-items: flex-start; flex-direction: column; gap: 0.1rem; }
    .option { grid-template-columns: auto minmax(0, 1fr); }
    .option .badge { grid-column: 2; justify-self: start; }
  }
</style>

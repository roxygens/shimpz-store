<script lang="ts">
  import { onMount, tick } from "svelte";
  import { goto } from "$app/navigation";
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import Seo from "$lib/components/Seo.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);

  let phase = $state("checking"); // checking | ready (unauthed → redirected to /login)
  let capName = $state("");
  let brain = $state("claude-code");
  let model = $state("claude-sonnet-5");
  let capsules = $state<any[]>([]);
  let selected = $state("");
  let error = $state("");
  let busy = $state(false);
  let modelSelectionAvailable = $state(false);

  let createOpen = $state(false); // the "Create Capsule" modal (creation is no longer inline on the page)
  let destroyTarget = $state<any>(null);
  let appsByCap = $state<Record<string, any[]>>({}); // installed apps per Capsule
  let openApps = $state(""); // which Capsule's Apps menu is expanded

  let createTrigger = $state<HTMLButtonElement>();
  let destroyDialog = $state<HTMLDialogElement>();
  let destroyCancelButton = $state<HTMLButtonElement>();
  let destroyReturnFocus: HTMLButtonElement | null = null;

  const SEL_KEY = "shimpz_current_capsule";

  function defaultModel(provider: string) {
    return provider === "claude-code" ? "claude-sonnet-5" : "";
  }

  function chooseBrain(event: Event) {
    brain = (event.currentTarget as HTMLSelectElement).value;
    model = defaultModel(brain);
  }

  async function loadApps(id: string) {
    const r = await fetch(`/api/capsules/${id}/apps`);
    appsByCap[id] = r.ok ? ((await r.json()).apps ?? []) : [];
  }

  async function refresh() {
    const r = await fetch("/api/capsules");
    if (r.ok) {
      capsules = (await r.json()).capsules ?? [];
      if (!selected && capsules[0]) select(capsules[0].id); // persist too — the app page reads it
      await Promise.all(capsules.map((c) => loadApps(c.id))); // so each row can show its Apps count
    }
  }

  function toggleApps(id: string) {
    openApps = openApps === id ? "" : id;
  }

  async function uninstallApp(capId: string, appId: string) {
    if (busy) return;
    busy = true;
    try {
      await fetch(`/api/capsules/${capId}/apps/${appId}`, { method: "DELETE" });
      await loadApps(capId);
    } finally {
      busy = false;
    }
  }

  async function boot() {
    try {
      const me = await (await fetch("/api/me")).json();
      if (me.authenticated) {
        const brainsResponse = await fetch("/api/brains").catch(() => null);
        const brainsResult = await brainsResponse?.json().catch(() => null);
        modelSelectionAvailable = Boolean(brainsResponse?.ok && Array.isArray(brainsResult?.brains));
        selected = localStorage.getItem(SEL_KEY) ?? "";
        await refresh();
        phase = "ready";
      } else {
        goto(u.login(lang)); // auth is centralized on /login
      }
    } catch {
      goto(u.login(lang));
    }
  }

  async function createCapsule() {
    if (!capName.trim() || busy) return;
    busy = true;
    error = "";
    try {
      const payload: Record<string, string> = { name: capName.trim(), brain };
      if (modelSelectionAvailable) payload.model = model.trim();
      const r = await fetch("/api/capsules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (r.ok) {
        capName = "";
        createOpen = false;
        await refresh();
      } else {
        const result = await r.json().catch(() => ({}));
        error = result.detail ?? result.error ?? `create failed (${r.status})`;
      }
    } catch (e) {
      error = String(e);
    } finally {
      busy = false;
    }
  }

  async function destroyCapsule(id: string) {
    busy = true;
    error = "";
    try {
      await fetch(`/api/capsules/${id}`, { method: "DELETE" });
      if (selected === id) select("");
      await refresh();
    } finally {
      busy = false;
    }
  }

  async function openDestroyDialog(capsule: any, trigger: HTMLButtonElement) {
    if (busy) return;
    destroyTarget = capsule;
    destroyReturnFocus = trigger;
    await tick();
    if (destroyDialog && !destroyDialog.open) destroyDialog.showModal();
    destroyCancelButton?.focus();
  }

  function closeDestroyDialog() {
    if (busy) return;
    if (destroyDialog?.open) destroyDialog.close();
    const returnFocus = destroyReturnFocus;
    destroyTarget = null;
    destroyReturnFocus = null;
    void tick().then(() => {
      if (returnFocus?.isConnected) returnFocus.focus();
      else createTrigger?.focus();
    });
  }

  async function confirmDestroyCapsule() {
    if (!destroyTarget || busy) return;
    const id = destroyTarget.id;
    try {
      await destroyCapsule(id);
    } finally {
      closeDestroyDialog();
    }
  }

  function select(id: string) {
    selected = id;
    if (id) {
      localStorage.setItem(SEL_KEY, id);
      const name = capsules.find((c) => c.id === id)?.name ?? id;
      localStorage.setItem(SEL_KEY + "_name", name); // the app page shows WHERE Install will land
    } else {
      localStorage.removeItem(SEL_KEY);
      localStorage.removeItem(SEL_KEY + "_name");
    }
  }

  // lock the page scroll while either focused modal is open
  $effect(() => {
    if (typeof document === "undefined") return;
    document.body.style.overflow = createOpen || destroyTarget ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  });

  onMount(boot);
</script>

<svelte:window onkeydown={(e) => { if (e.key === "Escape" && createOpen) createOpen = false; }} />

<Seo title={tr("capsule_title", lang)} description={tr("capsule_lead", lang)} {lang} />

<section class="wrap pt-10 pb-8">
  {#if phase === "checking"}
    <h1 class="text-4xl font-extrabold tracking-tight sm:text-5xl">{tr("my_capsules", lang)}</h1>
    <p class="mt-6 dim">…</p>
  {:else}
    <!-- My Capsules — the page is the LIST; creation lives behind the button (a focused modal) -->
    <div class="flex flex-wrap items-center justify-between gap-4">
      <h1 class="text-4xl font-extrabold tracking-tight sm:text-5xl">{tr("my_capsules", lang)}</h1>
      <button bind:this={createTrigger} class="btn-primary" onclick={() => { error = ""; createOpen = true; }}>+ {tr("capsule_submit", lang)}</button>
    </div>
    <div class="mt-3 text-sm dim">{capsules.length} {tr("my_capsules", lang)}</div>
    {#if error && !createOpen}<p class="mt-3 text-sm" style="color:var(--color-magenta)">{error}</p>{/if}

    <div class="mt-6 space-y-3">
      {#each capsules as c (c.id)}
        <div class="card" class:ring={selected === c.id}>
          <div class="flex flex-wrap items-center gap-3">
            <button class="flex min-w-0 flex-1 items-center gap-4 text-left" onclick={() => select(c.id)}>
              <span class="app-icon grid shrink-0 place-items-center" style="--g1:var(--color-cyan);--g2:var(--color-magenta);width:34px;height:34px;font-size:16px">⬡</span>
              <span class="min-w-0 flex-1">
                <span class="block font-semibold">{c.name || c.id}</span>
                <span class="mono block truncate text-xs dim">
                  {c.id} · {c.status} · {tr("brain_label", lang)}: {c.brain ?? "claude-code"}{#if modelSelectionAvailable} · {tr("model_label", lang)}: {c.model || tr("model_default", lang)}{/if}
                </span>
              </span>
              {#if selected === c.id}<span class="badge">{tr("current", lang)}</span>{/if}
            </button>
            <button class="btn-ghost !px-3 !py-1 text-xs" aria-expanded={openApps === c.id} onclick={() => toggleApps(c.id)}>
              {tr("apps_menu", lang)} <span class="opacity-70">{appsByCap[c.id]?.length ?? 0}</span> {openApps === c.id ? "▴" : "▾"}
            </button>
            <a class="btn-ghost !px-3 !py-1 text-xs" href={u.chat(lang)} onclick={() => select(c.id)}>{tr("nav_chat", lang)}</a>
            <button
              class="btn-danger !px-3 !py-1 text-xs"
              disabled={busy}
              onclick={(event) => openDestroyDialog(c, event.currentTarget)}>{tr("destroy", lang)}</button>
          </div>

          {#if openApps === c.id}
            <div class="mt-4 border-t hair pt-4">
              <span class="kicker">{tr("installed_apps", lang)}</span>
              <div class="mt-3 space-y-2">
                {#each (appsByCap[c.id] ?? []) as a (a.app)}
                  <div class="flex items-center gap-3 text-sm">
                    <span class="mono min-w-0 flex-1 truncate">{a.app}</span>
                    <span class="badge">{a.status}</span>
                    <button class="btn-ghost !px-3 !py-1 text-xs" disabled={busy} onclick={() => uninstallApp(c.id, a.app)}>{tr("uninstall", lang)}</button>
                  </div>
                {/each}
                {#if (appsByCap[c.id] ?? []).length === 0}
                  <p class="text-sm dim">{tr("no_apps", lang)}</p>
                {/if}
              </div>
            </div>
          {/if}
        </div>
      {/each}
      {#if capsules.length === 0}<p class="dim">{tr("no_capsules", lang)}</p>{/if}
    </div>
  {/if}
</section>

<!-- Create Capsule — a focused overlay, so the page itself stays a clean list -->
{#if createOpen}
  <div class="create-backdrop fixed inset-0 z-[70] flex items-center justify-center p-5" style="background:color-mix(in oklab, var(--color-bg) 88%, transparent)" role="dialog" aria-modal="true" aria-label={tr("capsule_submit", lang)} tabindex="-1">
    <div class="panel create-panel w-full max-w-md space-y-4">
      <div class="flex items-center justify-between gap-4">
        <h2 class="mono text-lg font-extrabold uppercase tracking-wide">{tr("capsule_submit", lang)}</h2>
        <button class="btn-ghost !px-3 !py-1 text-xs" onclick={() => (createOpen = false)} aria-label={tr("close", lang)}>✕</button>
      </div>
      <p class="text-sm leading-relaxed dim">{tr("capsule_lead", lang)}</p>
      <div>
        <span class="kicker">{tr("capsule_name_label", lang)}</span>
        <input class="field mt-2" placeholder={tr("capsule_name_ph", lang)} bind:value={capName} onkeydown={(e) => e.key === "Enter" && createCapsule()} />
      </div>
      <label class="flex items-center gap-3 text-sm dim">
        <span class="kicker !text-[10px]">{tr("brain_label", lang)}</span>
        <select class="field field-sm w-auto" value={brain} onchange={chooseBrain}>
          <option value="claude-code">Claude Code</option>
          <option value="codex">Codex</option>
        </select>
      </label>
      {#if modelSelectionAvailable}
        <label class="block text-sm dim">
          <span class="kicker !text-[10px]">{tr("model_label", lang)}</span>
          <input class="field mt-2" bind:value={model} placeholder={tr("model_default", lang)} maxlength="128" autocomplete="off" />
          <span class="mt-1 block text-xs dim">{tr("model_hint", lang)}</span>
        </label>
      {/if}
      {#if error}<p class="text-sm" style="color:var(--color-magenta)">{error}</p>{/if}
      <button class="btn-primary w-full justify-center" disabled={busy || !capName.trim()} onclick={createCapsule}>{tr("capsule_submit", lang)}</button>
    </div>
  </div>
{/if}

{#if destroyTarget}
  <dialog
    bind:this={destroyDialog}
    class="destroy-dialog"
    aria-labelledby="destroy-dialog-title"
    aria-describedby="destroy-dialog-description"
    oncancel={(event) => {
      event.preventDefault();
      closeDestroyDialog();
    }}
  >
    <div class="panel destroy-panel">
      <p class="kicker">{tr("my_capsules", lang)} // {tr("destroy", lang)}</p>
      <h2 id="destroy-dialog-title">{tr("destroy", lang)} {destroyTarget.name || destroyTarget.id}?</h2>
      <p id="destroy-dialog-description">{tr("destroy_confirm", lang)}</p>
      <div class="destroy-actions">
        <button bind:this={destroyCancelButton} class="btn-ghost" type="button" disabled={busy} onclick={closeDestroyDialog}>
          {lang === "pt" ? "Cancelar" : "Cancel"}
        </button>
        <button class="btn-danger" type="button" disabled={busy} onclick={confirmDestroyCapsule}>
          {busy ? tr("capsule_submitting", lang) : tr("destroy", lang)}
        </button>
      </div>
    </div>
  </dialog>
{/if}

<style>
  .ring {
    box-shadow: 0 0 0 1px var(--color-primary);
  }

  .create-backdrop {
    overflow-y: auto;
    overscroll-behavior: contain;
  }

  .create-panel {
    max-height: calc(100dvh - 2.5rem);
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-gutter: stable;
  }

  .destroy-dialog {
    width: min(calc(100% - 2rem), 32rem);
    max-height: calc(100dvh - 2rem);
    margin: auto;
    padding: 0;
    border: 0;
    overflow: visible;
    background: transparent;
    color: var(--color-fg);
  }

  .destroy-dialog::backdrop {
    background: color-mix(in oklab, var(--color-bg) 88%, transparent);
    backdrop-filter: blur(8px);
  }

  .destroy-panel {
    max-height: calc(100dvh - 2rem);
    overflow-y: auto;
    padding: clamp(1.25rem, 4vw, 2rem);
    overscroll-behavior: contain;
  }

  .destroy-panel .kicker { margin: 0 0 0.8rem; }

  .destroy-panel h2 {
    margin: 0;
    font-size: clamp(1.35rem, 5vw, 1.8rem);
    line-height: 1.2;
  }

  .destroy-panel > p:last-of-type {
    margin: 1rem 0 0;
    color: var(--color-muted);
    line-height: 1.65;
  }

  .destroy-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.7rem;
    margin-top: 1.6rem;
  }

  @media (max-height: 560px) {
    .create-backdrop {
      align-items: flex-start;
      padding-block: 0.75rem;
    }

    .create-panel { max-height: calc(100dvh - 1.5rem); }
  }

  @media (max-width: 420px) {
    .destroy-actions { align-items: stretch; flex-direction: column-reverse; }
    .destroy-actions button { width: 100%; }
  }
</style>

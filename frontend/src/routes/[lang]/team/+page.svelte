<script lang="ts">
  import { onMount, tick } from "svelte";
  import { goto } from "$app/navigation";
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import {
    MODEL_PROVIDERS,
    defaultModelFor,
    modelOptionLabel,
    modelsForProvider,
    normalizeInferenceSelection,
  } from "$lib/modelProviders.js";
  import { u } from "$lib/url";
  import { resolveClosedAssistantReturn } from "$lib/cloudAssistantLifecycle.js";
  import HudIcon from "$lib/components/HudIcon.svelte";
  import PageIntro from "$lib/components/PageIntro.svelte";
  import Seo from "$lib/components/Seo.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);

  let phase = $state("checking"); // checking | ready (unauthed → redirected to /login)
  let teamNameInput = $state("");
  let provider = $state("openai");
  let model = $state(defaultModelFor("openai"));
  let teams = $state<any[]>([]);
  let selected = $state("");
  let error = $state("");
  let busy = $state(false);

  let createOpen = $state(false); // the "Create Team" modal (creation is no longer inline on the page)
  let destroyTarget = $state<any>(null);
  let appsByTeam = $state<Record<string, any[]>>({}); // installed apps per Team
  let appsLoaded = $state<Record<string, boolean>>({});
  let appsLoading = $state<Record<string, boolean>>({});
  let appsError = $state<Record<string, string>>({});
  let openApps = $state(""); // which Team's Apps menu is expanded

  let createTrigger = $state<HTMLButtonElement>();
  let destroyDialog = $state<HTMLDialogElement>();
  let destroyCancelButton = $state<HTMLButtonElement>();
  let destroyReturnFocus: HTMLButtonElement | null = null;

  const SEL_KEY = "shimpz_current_team";

  function chooseProvider(event: Event) {
    provider = (event.currentTarget as HTMLSelectElement).value;
    model = defaultModelFor(provider);
  }

  async function loadApps(teamId: string) {
    appsLoading[teamId] = true;
    appsError[teamId] = "";
    try {
      const r = await fetch(`/api/teams/${teamId}/apps`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      appsByTeam[teamId] = (await r.json()).apps ?? [];
      appsLoaded[teamId] = true;
    } catch {
      appsError[teamId] = tr("team_apps_load_failed", lang);
    } finally {
      appsLoading[teamId] = false;
    }
  }

  async function refresh() {
    const r = await fetch("/api/teams");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    teams = (await r.json()).teams ?? [];
    if (!teams.some((team) => team.team_id === selected)) {
      select(teams[0]?.team_id ?? "");
    }
  }

  async function toggleApps(id: string) {
    if (openApps === id) {
      openApps = "";
      return;
    }
    openApps = id;
    if (!appsLoaded[id] && !appsLoading[id]) await loadApps(id);
  }

  async function uninstallApp(teamId: string, appId: string) {
    if (busy) return;
    busy = true;
    try {
      await fetch(`/api/teams/${teamId}/apps/${appId}`, { method: "DELETE" });
      await loadApps(teamId);
    } finally {
      busy = false;
    }
  }

  async function boot() {
    try {
      const meResponse = await fetch("/api/me");
      const me = await meResponse.json().catch(() => ({}));
      if (!meResponse.ok || !me.authenticated) {
        goto(u.login(lang)); // auth is centralized on /login
        return;
      }
      selected = localStorage.getItem(SEL_KEY) ?? "";
      try {
        await refresh();
      } catch {
        error = tr("team_list_load_failed", lang);
      }
      phase = "ready";
    } catch {
      goto(u.login(lang));
    }
  }

  async function createTeam() {
    if (!teamNameInput.trim() || busy) return;
    busy = true;
    error = "";
    try {
      const inference = normalizeInferenceSelection(provider, model);
      const payload = { team_name: teamNameInput.trim(), ...inference };
      const r = await fetch("/api/teams", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (r.ok) {
        teamNameInput = "";
        createOpen = false;
        await refresh();
        const destination = resolveClosedAssistantReturn(lang, window.location.search);
        if (destination) await goto(destination);
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

  async function destroyTeam(teamId: string) {
    busy = true;
    error = "";
    try {
      await fetch(`/api/teams/${teamId}`, { method: "DELETE" });
      if (selected === teamId) select("");
      await refresh();
    } finally {
      busy = false;
    }
  }

  async function openDestroyDialog(team: any, trigger: HTMLButtonElement) {
    if (busy) return;
    destroyTarget = team;
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

  async function confirmDestroyTeam() {
    if (!destroyTarget || busy) return;
    const teamId = destroyTarget.team_id;
    try {
      await destroyTeam(teamId);
    } finally {
      closeDestroyDialog();
    }
  }

  function select(teamId: string) {
    selected = teamId;
    if (teamId) {
      localStorage.setItem(SEL_KEY, teamId);
      const teamName = teams.find((team) => team.team_id === teamId)?.team_name ?? teamId;
      localStorage.setItem(SEL_KEY + "_name", teamName); // the app page shows WHERE Install will land
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

<Seo title={tr("team_list_title", lang)} description={tr("team_list_lead", lang)} {lang} />

<section class="wrap pt-10 pb-8">
  {#snippet teamMedia()}
    <div class="team-hero-icon"><HudIcon name="team" size={44} /></div>
  {/snippet}

  {#snippet teamMeta()}
    {#if phase === "ready"}
      <span class="badge">{teams.length} {tr("team_count_label", lang)}</span>
      <button bind:this={createTrigger} class="btn-primary" onclick={() => { error = ""; createOpen = true; }}>
        <HudIcon name="add" size={17} />
        {tr("team_submit", lang)}
      </button>
    {/if}
  {/snippet}

  <PageIntro
    headingId="team-list-title"
    kicker={tr("team_list_kicker", lang)}
    title={tr("my_teams", lang)}
    description={tr("team_list_lead", lang)}
    media={teamMedia}
    meta={teamMeta}
  />

  {#if phase === "checking"}
    <p class="mt-6 dim">…</p>
  {:else}
    {#if error && !createOpen}<p class="mt-5 notice notice-error">{error}</p>{/if}

    <div class="team-list">
      {#each teams as team (team.team_id)}
        <article class="card team-card" class:ring={selected === team.team_id}>
          <button class="team-identity" type="button" onclick={() => select(team.team_id)}>
            <span class="team-mark" aria-hidden="true"><HudIcon name="team" size={27} /></span>
            <span class="team-copy">
              <span class="team-name">{team.team_name}</span>
              <span class="team-id mono">{team.team_id}</span>
              <span class="team-facts mono">
                <span><span class="status-signal" aria-hidden="true"></span>{team.status}</span>
                <span>{tr("brain_label", lang)}: {team.provider ?? "openai"}</span>
                <span>{tr("model_label", lang)}: {team.model || defaultModelFor(team.provider ?? "openai")}</span>
              </span>
            </span>
            {#if selected === team.team_id}<span class="badge">{tr("current", lang)}</span>{/if}
          </button>

          <div class="team-actions" role="group" aria-label={`${tr("team_actions", lang)}: ${team.team_name}`}>
            <button class="team-action" type="button" aria-expanded={openApps === team.team_id} onclick={() => toggleApps(team.team_id)}>
              <HudIcon name="assistants" size={18} />
              <span>{tr("apps_menu", lang)}</span>
              {#if appsLoaded[team.team_id]}<span class="action-count">{appsByTeam[team.team_id]?.length ?? 0}</span>{/if}
              <span class:expanded={openApps === team.team_id} class="chevron"><HudIcon name="chevron" size={16} /></span>
            </button>
            <a class="team-action" href={u.chat(lang, team.team_id)} onclick={() => select(team.team_id)}>
              <HudIcon name="chat" size={18} />
              <span>{tr("nav_chat", lang)}</span>
            </a>
            <button
              class="team-action team-action-danger"
              type="button"
              disabled={busy}
              onclick={(event) => openDestroyDialog(team, event.currentTarget)}>
              <HudIcon name="destroy" size={18} />
              <span>{tr("destroy", lang)}</span>
            </button>
          </div>

          {#if openApps === team.team_id}
            <div class="assistant-drawer">
              <div class="drawer-heading">
                <span class="kicker">{tr("installed_apps", lang)}</span>
                <span class="mono drawer-team">{team.team_name}</span>
              </div>
              {#if appsLoading[team.team_id]}
                <p class="drawer-state dim">{tr("loading", lang)}</p>
              {:else if appsError[team.team_id]}
                <div class="drawer-state drawer-error">
                  <span>{appsError[team.team_id]}</span>
                  <button class="btn-ghost" type="button" onclick={() => loadApps(team.team_id)}>
                    <HudIcon name="retry" size={16} /> {tr("retry", lang)}
                  </button>
                </div>
              {:else}
                <div class="assistant-list">
                  {#each (appsByTeam[team.team_id] ?? []) as a (a.app)}
                    <div class="assistant-row">
                      <span class="assistant-row-icon" aria-hidden="true"><HudIcon name="assistants" size={17} /></span>
                      <span class="mono assistant-name">{a.app}</span>
                      <span class="badge">{a.status}</span>
                      <button class="btn-ghost assistant-uninstall" type="button" disabled={busy} onclick={() => uninstallApp(team.team_id, a.app)}>
                        <HudIcon name="uninstall" size={16} /> {tr("uninstall", lang)}
                      </button>
                    </div>
                  {/each}
                  {#if (appsByTeam[team.team_id] ?? []).length === 0}
                    <p class="drawer-state dim">{tr("no_apps", lang)}</p>
                  {/if}
                </div>
              {/if}
            </div>
          {/if}
        </article>
      {/each}
      {#if teams.length === 0}<div class="panel empty-state"><HudIcon name="team" size={32} /><p>{tr("no_teams", lang)}</p></div>{/if}
    </div>
  {/if}
</section>

<!-- Create Team — a focused overlay, so the page itself stays a clean list -->
{#if createOpen}
  <div class="create-backdrop fixed inset-0 z-[70] flex items-center justify-center p-5" style="background:color-mix(in oklab, var(--color-bg) 88%, transparent)" role="dialog" aria-modal="true" aria-label={tr("team_submit", lang)} tabindex="-1">
    <div class="panel create-panel w-full max-w-md space-y-4">
      <div class="flex items-center justify-between gap-4">
        <h2 class="mono text-lg font-extrabold uppercase tracking-wide">{tr("team_submit", lang)}</h2>
        <button class="btn-ghost !px-3 !py-1 text-xs" onclick={() => (createOpen = false)} aria-label={tr("close", lang)}>✕</button>
      </div>
      <p class="text-sm leading-relaxed dim">{tr("team_lead", lang)}</p>
      <div>
        <span class="kicker">{tr("team_name_label", lang)}</span>
        <input class="field mt-2" placeholder={tr("team_name_ph", lang)} bind:value={teamNameInput} onkeydown={(e) => e.key === "Enter" && createTeam()} />
      </div>
      <label class="block text-sm dim">
        <span class="kicker !text-[10px]">{tr("brain_label", lang)}</span>
        <select class="field mt-2" value={provider} onchange={chooseProvider}>
          {#each MODEL_PROVIDERS as option (option.id)}
            <option value={option.id}>{option.title}</option>
          {/each}
        </select>
      </label>
      <label class="block text-sm dim">
        <span class="kicker !text-[10px]">{tr("model_label", lang)}</span>
        <select class="field mt-2" bind:value={model}>
          {#each modelsForProvider(provider) as option (option.id)}
            <option value={option.id}>{modelOptionLabel(option, lang)}</option>
          {/each}
        </select>
      </label>
      {#if error}<p class="text-sm" style="color:var(--color-magenta)">{error}</p>{/if}
      <button class="btn-primary w-full justify-center" disabled={busy || !teamNameInput.trim()} onclick={createTeam}>{tr("team_submit", lang)}</button>
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
      <p class="kicker">{tr("my_teams", lang)} // {tr("destroy", lang)}</p>
      <h2 id="destroy-dialog-title">{tr("destroy", lang)} {destroyTarget.team_name}?</h2>
      <p id="destroy-dialog-description">{tr("destroy_confirm", lang)}</p>
      <div class="destroy-actions">
        <button bind:this={destroyCancelButton} class="btn-ghost" type="button" disabled={busy} onclick={closeDestroyDialog}>
          {lang === "pt" ? "Cancelar" : "Cancel"}
        </button>
        <button class="btn-danger" type="button" disabled={busy} onclick={confirmDestroyTeam}>
          {busy ? tr("team_submitting", lang) : tr("destroy", lang)}
        </button>
      </div>
    </div>
  </dialog>
{/if}

<style>
  .team-hero-icon {
    display: grid;
    width: 4.5rem;
    height: 4.5rem;
    place-items: center;
    color: var(--color-cyan);
    background:
      radial-gradient(circle at 50% 50%, color-mix(in oklab, var(--color-cyan) 16%, transparent), transparent 62%),
      #000;
    text-shadow: 0 0 18px currentColor;
  }

  .team-list {
    display: grid;
    gap: 0.85rem;
    margin-top: 1.4rem;
  }

  .team-card {
    display: grid;
    gap: 1rem;
    padding: 0;
    overflow: hidden;
    transition: box-shadow 160ms ease, border-color 160ms ease;
  }

  .ring {
    box-shadow: inset 3px 0 0 var(--color-cyan), 0 0 0 1px var(--color-primary);
  }

  .team-identity {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    min-width: 0;
    align-items: center;
    gap: 0.9rem;
    border: 0;
    padding: 1.15rem 1.2rem 0;
    background: transparent;
    color: var(--color-fg);
    cursor: pointer;
    text-align: left;
  }

  .team-identity:focus-visible,
  .team-action:focus-visible {
    outline: 2px solid var(--color-cyan);
    outline-offset: -2px;
  }

  .team-mark,
  .assistant-row-icon {
    display: grid;
    place-items: center;
    color: var(--color-cyan);
    background: color-mix(in oklab, var(--color-cyan) 7%, var(--color-card-2));
    box-shadow: inset 0 0 0 1px var(--color-border-strong);
    clip-path: polygon(0.45rem 0, 100% 0, 100% calc(100% - 0.45rem), calc(100% - 0.45rem) 100%, 0 100%, 0 0.45rem);
  }

  .team-mark { width: 3.2rem; height: 3.2rem; }
  .team-copy { display: block; min-width: 0; }
  .team-name { display: block; font-family: var(--font-mono); font-weight: 700; }
  .team-id { display: block; overflow: hidden; color: var(--color-muted-2); font-size: 0.66rem; text-overflow: ellipsis; white-space: nowrap; }

  .team-facts {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem 1rem;
    margin-top: 0.45rem;
    color: var(--color-muted);
    font-size: 0.68rem;
  }

  .team-facts > span { display: inline-flex; align-items: center; gap: 0.35rem; }

  .status-signal {
    width: 0.4rem;
    height: 0.4rem;
    background: var(--color-green);
    border-radius: 50%;
    box-shadow: 0 0 7px color-mix(in oklab, var(--color-green) 60%, transparent);
  }

  .team-actions {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    border-top: 1px solid var(--color-border);
  }

  .team-action {
    display: inline-flex;
    min-width: 0;
    min-height: 3rem;
    align-items: center;
    justify-content: center;
    gap: 0.55rem;
    border: 0;
    border-right: 1px solid var(--color-border);
    padding: 0.65rem 0.85rem;
    background: color-mix(in oklab, var(--color-card-2) 86%, transparent);
    color: var(--color-muted);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 0.68rem;
    font-weight: 650;
    letter-spacing: 0.06em;
    text-decoration: none;
    text-transform: uppercase;
  }

  .team-action:last-child { border-right: 0; }
  .team-action:hover { background: color-mix(in oklab, var(--color-cyan) 7%, var(--color-card-2)); color: var(--color-cyan); }
  .team-action-danger:hover { background: color-mix(in oklab, var(--color-magenta) 8%, var(--color-card-2)); color: var(--color-magenta); }
  .team-action:disabled { cursor: not-allowed; opacity: 0.5; }

  .action-count {
    min-width: 1.35rem;
    padding: 0.12rem 0.3rem;
    background: var(--color-bg);
    color: var(--color-fg);
    text-align: center;
  }

  .chevron { margin-left: 0.15rem; transition: transform 150ms ease; }
  .chevron.expanded { transform: rotate(180deg); }

  .assistant-drawer {
    margin-top: -1rem;
    padding: 1rem 1.2rem 1.2rem;
    border-top: 1px solid var(--color-border);
    background: color-mix(in oklab, var(--color-bg) 40%, transparent);
  }

  .drawer-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem; }
  .drawer-heading .kicker { margin: 0; }
  .drawer-team { color: var(--color-muted-2); font-size: 0.65rem; }
  .drawer-state { margin: 0.85rem 0 0; font-size: 0.85rem; }
  .drawer-error { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.7rem; color: var(--color-magenta); }

  .assistant-list { display: grid; gap: 0.55rem; margin-top: 0.85rem; }
  .assistant-row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; align-items: center; gap: 0.65rem; }
  .assistant-row-icon { width: 2rem; height: 2rem; }
  .assistant-name { overflow: hidden; font-size: 0.76rem; text-overflow: ellipsis; white-space: nowrap; }
  .assistant-uninstall { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.45rem 0.65rem; font-size: 0.65rem; }

  .empty-state {
    display: flex;
    align-items: center;
    gap: 1rem;
    color: var(--color-muted);
  }

  .empty-state :global(svg) { color: var(--color-cyan); }
  .empty-state p { margin: 0; }

  @media (max-width: 600px) {
    .team-identity { grid-template-columns: auto minmax(0, 1fr); }
    .team-identity > .badge { grid-column: 2; justify-self: start; }
    .team-actions { grid-template-columns: 1fr; }
    .team-action { justify-content: flex-start; border-right: 0; border-bottom: 1px solid var(--color-border); }
    .team-action:last-child { border-bottom: 0; }
    .assistant-row { grid-template-columns: auto minmax(0, 1fr) auto; }
    .assistant-uninstall { grid-column: 2 / -1; justify-self: start; }
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

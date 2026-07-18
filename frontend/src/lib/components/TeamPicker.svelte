<script lang="ts">
  import { goto } from "$app/navigation";
  import { onMount, tick } from "svelte";
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import HudIcon from "$lib/components/HudIcon.svelte";

  let { lang }: { lang: Locale } = $props();

  let name = $state("");
  let open = $state(false);
  let loading = $state(false);
  let authenticated = $state(false);
  let teams = $state<any[]>([]);
  let dialog = $state<HTMLElement>();

  onMount(() => {
    name = localStorage.getItem("shimpz_current_team_name") ?? "";
  });

  async function openPicker() {
    open = true;
    await tick();
    dialog?.focus();
    loading = true;
    teams = [];
    const me = await fetch("/api/me")
      .then((response) => response.json())
      .catch(() => ({}));
    authenticated = !!me.authenticated;
    if (authenticated) {
      const response = await fetch("/api/teams").catch(() => null);
      teams = response?.ok ? ((await response.json()).teams ?? []) : [];
    }
    loading = false;
  }

  function closePicker() {
    open = false;
  }

  function chooseTeam(team: any) {
    name = team.team_name;
    localStorage.setItem("shimpz_current_team", team.team_id);
    localStorage.setItem("shimpz_current_team_name", name);
    closePicker();
    goto(u.chat(lang, team.team_id));
  }

  $effect(() => {
    if (typeof document === "undefined") return;
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  });
</script>

<svelte:window onkeydown={(event) => event.key === "Escape" && open && closePicker()} />

<button class="team-trigger" type="button" onclick={openPicker} aria-haspopup="dialog" aria-expanded={open}>
  <span class="status-dot" aria-hidden="true"></span>
  <span>{name || tr("my_teams", lang)}</span>
</button>

{#if open}
  <div
    class="team-dialog"
    role="dialog"
    aria-modal="true"
    aria-labelledby="team-dialog-title"
    tabindex="-1"
    bind:this={dialog}
  >
    <header>
      <div class="wrap dialog-topbar">
        <h2 id="team-dialog-title"><span aria-hidden="true"><HudIcon name="team" size={24} /></span> {tr("my_teams", lang)}</h2>
        <button class="btn-ghost" type="button" onclick={closePicker} aria-label={tr("close", lang)}>✕</button>
      </div>
    </header>
    <div class="wrap dialog-content">
      {#if loading}
        <p class="dim">{tr("loading", lang)}</p>
      {:else if !authenticated}
        <div class="dialog-message">
          <p>{tr("team_picker_login", lang)}</p>
          <a href={u.login(lang)} class="btn-primary" onclick={closePicker}>{tr("log_in", lang)} →</a>
        </div>
      {:else if teams.length === 0}
        <div class="dialog-message">
          <p>{tr("team_picker_none", lang)}</p>
          <a href={u.team(lang)} class="btn-primary" onclick={closePicker}>{tr("team_picker_new", lang)} →</a>
        </div>
      {:else}
        <div class="team-grid">
          {#each teams as team (team.team_id)}
            <button class="card team-card" type="button" onclick={() => chooseTeam(team)}>
              <span class="team-glyph" aria-hidden="true"><HudIcon name="team" size={25} /></span>
              <span>
                <strong>{team.team_name}</strong>
                <small>{team.team_id}</small>
              </span>
              <em>{tr("team_picker_open", lang)}</em>
            </button>
          {/each}
        </div>
        <a href={u.team(lang)} class="btn-ghost new-team" onclick={closePicker}><HudIcon name="add" size={17} /> {tr("team_picker_new", lang)}</a>
      {/if}
    </div>
  </div>
{/if}

<style>
  .team-trigger {
    display: inline-flex;
    max-width: 11rem;
    min-height: 2.75rem;
    align-items: center;
    gap: 0.45rem;
    border: 0;
    border-left: 1px solid var(--color-border-strong);
    padding: 0.8rem 0.72rem 0.8rem 1rem;
    background: transparent;
    color: var(--color-muted);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .team-trigger:hover { color: var(--color-fg); }
  .team-trigger > span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .status-dot {
    width: 0.42rem;
    height: 0.42rem;
    flex: none;
    background: var(--color-green);
    border-radius: 50%;
    box-shadow: 0 0 8px rgba(5, 255, 161, 0.55);
  }

  .team-dialog {
    position: fixed;
    z-index: 70;
    inset: 0;
    overflow-y: auto;
    background: var(--color-bg);
    text-align: left;
    text-transform: none;
  }

  .team-dialog > header { border-bottom: 1px solid var(--color-border); }
  .dialog-topbar { display: flex; min-height: 5.25rem; align-items: center; justify-content: space-between; gap: 1rem; }
  .dialog-topbar h2 { display: flex; align-items: center; gap: 0.65rem; margin: 0; font-size: 1.2rem; }
  .dialog-topbar h2 span { color: var(--color-cyan); }
  .dialog-content { padding-block: 2.5rem; }
  .dialog-message { max-width: 30rem; }
  .dialog-message p { margin: 0 0 1.5rem; color: var(--color-muted); font-size: 1.05rem; }
  .team-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; }
  .team-card {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 0.85rem;
    border: 0;
    color: var(--color-fg);
    cursor: pointer;
    text-align: left;
  }
  .team-glyph {
    display: grid;
    width: 2.8rem;
    height: 2.8rem;
    place-items: center;
    color: var(--color-cyan);
    box-shadow: inset 0 0 0 1px var(--color-border-strong);
  }
  .team-card strong, .team-card small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .team-card small { color: var(--color-muted-2); font-family: var(--font-mono); font-size: 0.68rem; }
  .team-card em {
    grid-column: 2;
    color: var(--color-cyan);
    font-family: var(--font-mono);
    font-size: 0.65rem;
    font-style: normal;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .new-team { display: inline-flex; align-items: center; gap: 0.45rem; margin-top: 1.25rem; }

  @media (max-width: 960px) {
    .team-trigger { flex: none; }
    .team-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }

  @media (max-width: 620px) {
    .team-trigger {
      width: 100%;
      max-width: none;
      grid-column: 1 / -1;
      justify-content: center;
      border-top: 1px solid var(--color-border);
      border-left: 0;
    }

    .team-grid { grid-template-columns: 1fr; }
  }
</style>

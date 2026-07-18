<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import BrainSetupWizard from "$lib/components/BrainSetupWizard.svelte";
  import HudIcon from "$lib/components/HudIcon.svelte";
  import PageIntro from "$lib/components/PageIntro.svelte";
  import Seo from "$lib/components/Seo.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);

  let me = $state<any>(null);
  let ready = $state(false);
  let busy = $state(false);

  onMount(async () => {
    const account = await fetch("/api/me").then((response) => response.json()).catch(() => ({}));
    if (!account.authenticated) {
      goto(u.login(lang));
      return;
    }
    me = account;
    ready = true;
  });

  async function logout() {
    busy = true;
    await fetch("/api/logout", { method: "POST" }).catch(() => null);
    localStorage.removeItem("shimpz_current_team");
    localStorage.removeItem("shimpz_current_team_name");
    goto(u.home(lang));
  }
</script>

<Seo title={`${tr("account_title", lang)} · Shimpz`} description={tr("account_lead", lang)} {lang} />

<section class="wrap pt-10 pb-12" aria-labelledby="account-title">
  {#snippet media()}
    <div class="identity-mark"><HudIcon name="user" size={38} /></div>
  {/snippet}
  {#snippet meta()}
    {#if me}<span class="mono text-xs dim">@{me.username}</span>{/if}
  {/snippet}
  <PageIntro
    headingId="account-title"
    kicker={tr("account_kicker", lang)}
    title={tr("account_title", lang)}
    description={tr("account_lead", lang)}
    {media}
    {meta} />

  {#if !ready}
    <p class="mt-8 dim" role="status">{tr("loading", lang)}</p>
  {:else}
    <div class="account-grid">
      <BrainSetupWizard {lang} />

      <aside class="account-aside">
        <section class="panel compact-panel" aria-labelledby="identity-title">
          <div class="panel-title">
            <span class="panel-icon"><HudIcon name="user" size={18} /></span>
            <h2 id="identity-title">{tr("account_identity", lang)}</h2>
          </div>
          <dl>
            <div>
              <dt>{tr("username", lang)}</dt>
              <dd>@{me.username}</dd>
            </div>
            <div>
              <dt>{tr("account_id_label", lang)}</dt>
              <dd title={me.account_id}>{me.account_id}</dd>
            </div>
          </dl>
        </section>

        <section class="panel compact-panel" aria-labelledby="session-title">
          <div class="panel-title">
            <span class="panel-icon"><HudIcon name="session" size={18} /></span>
            <h2 id="session-title">{tr("account_session", lang)}</h2>
          </div>
          <div class="session-actions">
            <a href={u.team(lang)} class="btn-ghost">{tr("my_teams", lang)} →</a>
            <button class="btn-danger" type="button" disabled={busy} onclick={logout}>{tr("log_out", lang)}</button>
          </div>
        </section>
      </aside>
    </div>
  {/if}
</section>

<style>
  .identity-mark {
    display: grid;
    width: 5rem;
    height: 5rem;
    place-items: center;
    color: var(--color-cyan);
    background:
      linear-gradient(145deg, color-mix(in oklab, var(--color-cyan) 12%, #000), #000 55%),
      #000;
  }

  .account-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(15rem, 0.34fr);
    align-items: start;
    gap: 1rem;
    margin-top: 1rem;
  }

  .account-aside {
    display: grid;
    gap: 1rem;
  }

  .compact-panel { padding: 1rem; }

  .panel-title {
    display: flex;
    align-items: center;
    gap: 0.65rem;
  }

  .panel-title h2 {
    margin: 0;
    color: var(--color-muted);
    font-size: 0.72rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .panel-icon {
    display: grid;
    width: 2rem;
    height: 2rem;
    place-items: center;
    color: var(--color-cyan);
    background: #000;
    box-shadow: inset 0 0 0 1px var(--color-border-strong);
    clip-path: polygon(6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%, 0 6px);
  }

  dl { margin: 0.85rem 0 0; }
  dl > div { border-top: 1px solid var(--color-border); padding: 0.65rem 0; }
  dt { color: var(--color-muted); font-size: 0.68rem; }
  dd { margin: 0.15rem 0 0; overflow: hidden; font-family: var(--font-mono); font-size: 0.72rem; text-overflow: ellipsis; white-space: nowrap; }

  .session-actions {
    display: grid;
    gap: 0.55rem;
    margin-top: 0.85rem;
  }

  .session-actions :global(.btn-ghost),
  .session-actions :global(.btn-danger) {
    min-height: 2.5rem;
    padding: 0.55rem 0.7rem;
    font-size: 0.65rem;
  }

  @media (max-width: 900px) {
    .account-grid { grid-template-columns: 1fr; }
    .account-aside { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }

  @media (max-width: 580px) {
    .account-aside { grid-template-columns: 1fr; }
  }
</style>

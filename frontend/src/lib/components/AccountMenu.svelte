<script lang="ts">
  import { goto } from "$app/navigation";
  import { onMount } from "svelte";
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";

  let { lang }: { lang: Locale } = $props();

  let account = $state<any>(null);
  let open = $state(false);

  onMount(async () => {
    account = await fetch("/api/me")
      .then((response) => response.json())
      .catch(() => ({ authenticated: false }));
  });

  async function logout() {
    open = false;
    await fetch("/api/logout", { method: "POST" }).catch(() => null);
    account = { authenticated: false };
    localStorage.removeItem("shimpz_current_team");
    localStorage.removeItem("shimpz_current_team_name");
    goto(u.home(lang));
  }
</script>

<svelte:window onkeydown={(event) => event.key === "Escape" && (open = false)} />

{#if account?.authenticated}
  <div class="account-control">
    <button class="account-trigger" type="button" onclick={() => (open = !open)} aria-haspopup="menu" aria-expanded={open}>
      <span class="avatar" aria-hidden="true">{(account.username?.[0] ?? "?").toUpperCase()}</span>
      <span class="account-name">{account.username}</span>
      <span aria-hidden="true">▾</span>
    </button>
    {#if open}
      <button
        class="menu-dismiss"
        type="button"
        aria-label={lang === "pt" ? "Fechar menu da conta" : "Close account menu"}
        onclick={() => (open = false)}
      ></button>
      <div class="account-menu" role="menu">
        <div class="account-handle">@{account.username}</div>
        <a href={u.account(lang)} role="menuitem" onclick={() => (open = false)}>{tr("account", lang)}</a>
        <a href={u.team(lang)} role="menuitem" onclick={() => (open = false)}>{tr("my_teams", lang)}</a>
        <button type="button" role="menuitem" onclick={logout}>{tr("log_out", lang)}</button>
      </div>
    {/if}
  </div>
{:else}
  <a href={u.login(lang)} class="login-link">{tr("log_in", lang)}</a>
{/if}

<style>
  .account-control { position: relative; }

  .account-trigger {
    display: flex;
    min-height: 2.4rem;
    align-items: center;
    gap: 0.45rem;
    border: 0;
    padding: 0.35rem 0.65rem;
    background: var(--color-bg);
    box-shadow: inset 0 0 0 1px var(--color-border-strong);
    clip-path: polygon(6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%, 0 6px);
    color: var(--color-muted);
    cursor: pointer;
    font-size: 0.75rem;
  }

  .account-trigger:hover { color: var(--color-fg); }

  .avatar {
    display: grid;
    width: 1.45rem;
    height: 1.45rem;
    place-items: center;
    background: var(--color-cyan);
    border-radius: 50%;
    color: var(--color-accent-ink);
    font-size: 0.62rem;
    font-weight: 700;
  }

  .account-name { max-width: 6rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .menu-dismiss {
    position: fixed;
    z-index: 40;
    inset: 0;
    border: 0;
    background: transparent;
    cursor: default;
  }

  .account-menu {
    position: absolute;
    z-index: 50;
    top: calc(100% + 0.55rem);
    right: 0;
    width: 12rem;
    padding: 0.35rem;
    background: linear-gradient(145deg, var(--color-card-2), var(--color-card));
    box-shadow: inset 0 0 0 1px var(--color-border-strong), var(--shadow-panel);
    clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px);
  }

  .account-handle {
    overflow: hidden;
    padding: 0.65rem 0.7rem;
    border-bottom: 1px solid var(--color-border);
    color: var(--color-muted-2);
    font-family: var(--font-mono);
    font-size: 0.68rem;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .account-menu a,
  .account-menu button {
    display: block;
    width: 100%;
    min-height: 2.5rem;
    border: 0;
    padding: 0.65rem 0.7rem;
    background: transparent;
    color: var(--color-fg);
    cursor: pointer;
    font-size: 0.82rem;
    text-align: left;
  }

  .account-menu a:hover,
  .account-menu button:hover { background: var(--color-elevated); }
  .account-menu button { color: var(--color-danger); }

  .login-link {
    display: grid;
    min-height: 2.4rem;
    place-items: center;
    padding: 0.45rem 0.7rem;
    color: var(--color-muted);
    font-family: var(--font-mono);
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .login-link:hover { color: var(--color-fg); }

  @media (max-width: 620px) {
    .account-name { display: none; }
  }

  @media (max-width: 420px) {
    .login-link { padding-inline: 0.5rem; }
  }
</style>

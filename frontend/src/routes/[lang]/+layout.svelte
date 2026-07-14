<script lang="ts">
  import { onMount } from "svelte";
  import { page } from "$app/stores";
  import { goto } from "$app/navigation";
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u, swapLocale } from "$lib/url";

  let { data, children } = $props();
  const lang = $derived(data.lang as Locale);
  const path = $derived($page.url.pathname);

  // The Creator's currently-selected Capsule name, shown on the menu button (persisted across pages).
  let capName = $state("");
  // The signed-in account, for the header account menu.
  let account = $state<any>(null); // { authenticated, username, account_id }
  let accountMenu = $state(false);
  onMount(async () => {
    capName = localStorage.getItem("shimpz_current_capsule_name") ?? "";
    account = await fetch("/api/me").then((r) => r.json()).catch(() => ({ authenticated: false }));
  });

  async function doLogout() {
    accountMenu = false;
    await fetch("/api/logout", { method: "POST" }).catch(() => null);
    account = { authenticated: false };
    capName = "";
    localStorage.removeItem("shimpz_current_capsule");
    localStorage.removeItem("shimpz_current_capsule_name");
    goto(u.home(lang));
  }

  // "Minhas Cápsulas" — a full-screen chooser reachable from the menu on EVERY page.
  let capOpen = $state(false);
  let capLoading = $state(false);
  let capAuthed = $state(false);
  let capList = $state<any[]>([]);

  async function openCaps() {
    capOpen = true;
    capLoading = true;
    capList = [];
    const me = await fetch("/api/me").then((r) => r.json()).catch(() => ({}));
    capAuthed = !!me.authenticated;
    if (capAuthed) {
      const r = await fetch("/api/capsules").catch(() => null);
      capList = r?.ok ? ((await r.json()).capsules ?? []) : [];
    }
    capLoading = false;
  }
  const closeCaps = () => (capOpen = false);
  function chooseCap(c: any) {
    const name = c.name ?? c.id;
    localStorage.setItem("shimpz_current_capsule", c.id);
    localStorage.setItem("shimpz_current_capsule_name", name);
    capName = name;
    closeCaps();
    goto(u.chat(lang));
  }

  // lock the page scroll while the full-screen chooser is open
  $effect(() => {
    if (typeof document === "undefined") return;
    document.body.style.overflow = capOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  });
</script>

<svelte:window onkeydown={(e) => { if (e.key === "Escape") { if (capOpen) closeCaps(); accountMenu = false; } }} />

<header class="sticky top-0 z-20 border-b hair backdrop-blur" style="background:color-mix(in oklab, var(--color-bg) 82%, transparent)">
  <!-- row 1 — the wordmark centered; locale toggle tucked into the corner -->
  <div class="wrap relative flex h-16 items-center justify-center">
    <a href={u.home(lang)} class="mono flex items-center gap-2.5 text-lg font-extrabold uppercase tracking-wide">
      <span class="app-icon grid place-items-center" style="--g1:var(--color-cyan);--g2:var(--color-magenta);width:28px;height:28px;font-size:15px">◆</span>
      <span class="glitch" data-text="SHIMPZ" style="color:var(--color-fg)">SHIMPZ</span>
    </a>
    <div class="absolute right-0 flex items-center gap-2">
      {#if account?.authenticated}
        <div class="relative">
          <button class="hud-pill flex items-center gap-2 px-2 py-1 text-xs" onclick={() => (accountMenu = !accountMenu)} aria-haspopup="menu" aria-expanded={accountMenu}>
            <span class="grid size-5 place-items-center rounded-full text-[10px] font-bold" style="background:var(--color-primary);color:#04121a">{(account.username?.[0] ?? "?").toUpperCase()}</span>
            <span class="hidden max-w-24 truncate normal-case sm:inline">{account.username}</span>
            <span class="opacity-70">▾</span>
          </button>
          {#if accountMenu}
            <button class="fixed inset-0 z-40 cursor-default" aria-hidden="true" tabindex="-1" onclick={() => (accountMenu = false)}></button>
            <div class="notice absolute right-0 top-full z-50 mt-2 w-48 py-1" style="background:var(--color-card);box-shadow:inset 0 0 0 1px var(--color-border);filter:drop-shadow(0 12px 28px rgba(0,0,0,0.55))" role="menu">
              <div class="mono truncate border-b hair px-3 py-2 text-xs dim">@{account.username}</div>
              <a href={u.account(lang)} class="block px-3 py-2 text-sm transition hover:bg-[var(--color-elevated)]" role="menuitem" onclick={() => (accountMenu = false)}>{tr("account", lang)}</a>
              <a href={u.capsule(lang)} class="block px-3 py-2 text-sm transition hover:bg-[var(--color-elevated)]" role="menuitem" onclick={() => (accountMenu = false)}>{tr("my_capsules", lang)}</a>
              <button class="block w-full px-3 py-2 text-left text-sm transition hover:bg-[var(--color-elevated)]" style="color:var(--color-magenta)" role="menuitem" onclick={doLogout}>{tr("log_out", lang)}</button>
            </div>
          {/if}
        </div>
      {:else}
        <a href={u.login(lang)} class="hud-pill px-3 py-1.5 font-mono text-xs uppercase transition hover:text-[var(--color-fg)]">{tr("log_in", lang)}</a>
      {/if}
      <div class="hud-pill flex items-center p-0.5 text-xs">
        <a href={swapLocale(path, "en")} class="px-2 py-1 font-mono uppercase transition" style={lang === "en" ? "background:var(--color-primary);color:#04121a;font-weight:700" : "color:var(--color-muted)"}>EN</a>
        <a href={swapLocale(path, "pt")} class="px-2 py-1 font-mono uppercase transition" style={lang === "pt" ? "background:var(--color-primary);color:#04121a;font-weight:700" : "color:var(--color-muted)"}>PT</a>
      </div>
    </div>
  </div>
  <!-- row 2 — the menu, in its own bar. The divider from the wordmark row is on this FULL-WIDTH wrapper
       (edge to edge of the viewport), not the max-width nav. The Capsule chooser is set off on the right
       by a vertical divider. -->
  <div class="border-t hair">
    <nav class="wrap flex flex-wrap items-center gap-2 py-3" aria-label={tr("nav_main", lang)}>
      <a href={u.drivers(lang)} class="navbtn" class:is-active={path.includes("/drivers")}>{tr("nav_drivers", lang)}</a>
      <a href={u.creators(lang)} class="navbtn" class:is-active={path.includes("/creators")}>{tr("nav_creators", lang)}</a>
      <a href={u.chat(lang)} class="navbtn" class:is-active={path.includes("/chat")}>{tr("nav_chat", lang)}</a>
      <span class="ml-auto hidden h-7 w-px self-center sm:block" style="background:var(--color-border-strong)" aria-hidden="true"></span>
      <button class="navbtn" onclick={openCaps} aria-haspopup="dialog" aria-expanded={capOpen}>
        <span style="color:var(--color-primary)">⬡</span>
        <span class="max-w-32 truncate normal-case">{capName || tr("my_capsules", lang)}</span>
      </button>
    </nav>
  </div>
</header>

{@render children()}

<footer class="mt-24 border-t hair py-10">
  <div class="wrap flex flex-wrap items-center justify-between gap-4 text-sm dim">
    <span>Shimpz · {tr("footer", lang)}</span>
    <div class="flex gap-4">
      <a href={u.drivers(lang)} class="transition hover:text-[var(--color-fg)]">{tr("nav_drivers", lang)}</a>
    </div>
  </div>
</footer>

<!-- Minhas Cápsulas — full-screen choice overlay (above the scanline layer at z-60) -->
{#if capOpen}
  <div class="fixed inset-0 z-[70] flex flex-col" style="background:var(--color-bg)" role="dialog" aria-modal="true" aria-label={tr("my_capsules", lang)}>
    <div class="wrap flex items-center justify-between border-b hair py-5">
      <h2 class="mono flex items-center gap-2.5 text-xl font-extrabold uppercase tracking-wide">
        <span style="color:var(--color-primary)">⬡</span> {tr("my_capsules", lang)}
      </h2>
      <button class="navbtn" onclick={closeCaps} aria-label={tr("close", lang)}>✕</button>
    </div>
    <div class="wrap flex-1 overflow-y-auto py-8">
      {#if capLoading}
        <p class="dim">{tr("loading", lang)}</p>
      {:else if !capAuthed}
        <div class="max-w-md">
          <p class="text-lg">{tr("caps_login", lang)}</p>
          <a href={u.login(lang)} class="btn-primary mt-6 inline-flex" onclick={closeCaps}>{tr("log_in", lang)} →</a>
        </div>
      {:else if capList.length === 0}
        <div class="max-w-md">
          <p class="text-lg">{tr("caps_none", lang)}</p>
          <a href={u.capsule(lang)} class="btn-primary mt-6 inline-flex" onclick={closeCaps}>{tr("caps_new", lang)} →</a>
        </div>
      {:else}
        <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {#each capList as c (c.id)}
            <button class="card group text-left" onclick={() => chooseCap(c)}>
              <div class="flex items-center gap-3">
                <span class="app-icon grid shrink-0 place-items-center" style="--g1:var(--color-cyan);--g2:var(--color-magenta);width:44px;height:44px;font-size:20px">⬡</span>
                <div class="min-w-0 flex-1">
                  <div class="truncate font-semibold">{c.name ?? c.id}</div>
                  <div class="mono truncate text-xs dim">{c.id}</div>
                </div>
              </div>
              <div class="mt-4 text-xs font-semibold uppercase tracking-wide transition group-hover:text-[var(--color-fg)]" style="color:var(--color-primary)">{tr("caps_open", lang)}</div>
            </button>
          {/each}
        </div>
        <a href={u.capsule(lang)} class="btn-ghost mt-6 inline-flex" onclick={closeCaps}>{tr("caps_new", lang)} +</a>
      {/if}
    </div>
  </div>
{/if}

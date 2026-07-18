<script lang="ts">
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { swapLocale, u } from "$lib/url";
  import AccountMenu from "$lib/components/AccountMenu.svelte";
  import TeamPicker from "$lib/components/TeamPicker.svelte";
  import ShimpzBrand from "$lib/components/ShimpzBrand.svelte";

  let { lang, path }: { lang: Locale; path: string } = $props();
</script>

<a class="skip-link" href="#main-content">{lang === "pt" ? "Pular para o conteúdo" : "Skip to content"}</a>

<header class="site-header">
  <div class="wrap topbar">
    <ShimpzBrand href={u.home(lang)} product="Space" ariaLabel="Shimpz home" />

    <nav class="primary-nav" aria-label={tr("nav_main", lang)}>
      <a href={u.services(lang)} class:active={path.includes("/services")} aria-current={path.includes("/services") ? "page" : undefined}>
        {tr("nav_drivers", lang)}
      </a>
      <a href={u.assistants(lang)} class:active={path.includes("/assistants")} aria-current={path.includes("/assistants") ? "page" : undefined}>
        {tr("nav_assistants", lang)}
      </a>
      <a href={u.creators(lang)} class:active={path.includes("/creators")} aria-current={path.includes("/creators") ? "page" : undefined}>
        {tr("nav_creators", lang)}
      </a>
      <a href={u.chat(lang)} class:active={path.includes("/chat")} aria-current={path.includes("/chat") ? "page" : undefined}>
        {tr("nav_chat", lang)}
      </a>
      <a href="https://docs.shimpz.com" target="_blank" rel="noopener noreferrer">Docs <span aria-hidden="true">↗</span></a>
      <TeamPicker {lang} />
    </nav>

    <div class="header-actions">
      <AccountMenu {lang} />
      <div class="locale" aria-label={lang === "pt" ? "Idioma" : "Language"}>
        <a href={swapLocale(path, "en")} class:active={lang === "en"} aria-current={lang === "en" ? "page" : undefined}>EN</a>
        <a href={swapLocale(path, "pt")} class:active={lang === "pt"} aria-current={lang === "pt" ? "page" : undefined}>PT</a>
      </div>
    </div>
  </div>
</header>

<style>
  .skip-link {
    position: fixed;
    z-index: 100;
    top: 0.75rem;
    left: 1rem;
    padding: 0.65rem 0.9rem;
    background: var(--color-fg);
    color: var(--color-bg);
    font-family: var(--font-mono);
    font-size: 0.72rem;
    font-weight: 700;
    transform: translateY(-180%);
  }

  .skip-link:focus { transform: translateY(0); }

  .site-header {
    position: sticky;
    z-index: 50;
    top: 0;
    border-bottom: 1px solid var(--color-border);
    background: color-mix(in oklab, var(--color-bg) 88%, transparent);
    backdrop-filter: blur(18px);
  }

  .topbar {
    display: grid;
    min-height: 5.25rem;
    grid-template-columns: minmax(9rem, 1fr) auto minmax(9rem, 1fr);
    align-items: center;
    gap: 1rem;
  }

  .primary-nav {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.1rem;
  }

  .primary-nav > a {
    position: relative;
    min-height: 2.75rem;
    padding: 0.8rem 0.72rem;
    color: var(--color-muted);
    font-family: var(--font-mono);
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .primary-nav > a::after {
    position: absolute;
    right: 0.72rem;
    bottom: 0.35rem;
    left: 0.72rem;
    height: 1px;
    background: transparent;
    content: "";
  }

  .primary-nav > a:hover,
  .primary-nav > a.active { color: var(--color-fg); }

  .primary-nav > a.active::after {
    background: linear-gradient(90deg, var(--color-cyan), var(--color-magenta));
    box-shadow: 0 0 8px rgba(0, 240, 255, 0.45);
  }

  .header-actions {
    display: flex;
    min-width: 0;
    align-items: center;
    justify-content: flex-end;
    gap: 0.55rem;
  }

  .locale {
    display: flex;
    min-height: 2.4rem;
    align-items: center;
    padding: 0.2rem;
    background: var(--color-bg);
    box-shadow: inset 0 0 0 1px var(--color-border-strong);
    clip-path: polygon(6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%, 0 6px);
  }

  .locale a {
    display: grid;
    min-width: 2rem;
    min-height: 2rem;
    place-items: center;
    color: var(--color-muted);
    font-family: var(--font-mono);
    font-size: 0.65rem;
    font-weight: 600;
  }

  .locale a.active { background: var(--color-cyan); color: var(--color-accent-ink); }

  @media (max-width: 960px) {
    .topbar { grid-template-columns: 1fr auto; padding-top: 0.7rem; }
    .primary-nav {
      grid-row: 2;
      grid-column: 1 / -1;
      justify-content: flex-start;
      overflow-x: auto;
      border-top: 1px solid var(--color-border);
      scrollbar-width: none;
    }
    .primary-nav::-webkit-scrollbar { display: none; }
    .primary-nav > a { flex: none; }
    .header-actions { grid-column: 2; grid-row: 1; }
  }

  @media (max-width: 620px) {
    .primary-nav {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      overflow: visible;
    }

    .primary-nav > a {
      display: flex;
      min-width: 0;
      align-items: center;
      justify-content: center;
      padding-inline: 0.3rem;
      text-align: center;
      white-space: nowrap;
    }

    .primary-nav > a::after {
      right: 0.3rem;
      left: 0.3rem;
    }
  }

  @media (max-width: 420px) {
    .topbar { column-gap: 0.5rem; }
    .locale a { min-width: 1.8rem; }
  }
</style>

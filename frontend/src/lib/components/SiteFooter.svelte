<script lang="ts">
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import ShimpzBrand from "$lib/components/ShimpzBrand.svelte";

  let { lang, minimal = false }: { lang: Locale; minimal?: boolean } = $props();
</script>

<footer class="site-footer">
  <div class="wrap footer-inner">
    <div class="footer-brand">
      {#if minimal}
        <a class="wordmark" href={u.home(lang)} aria-label="Shimpz home">Shimpz</a>
      {:else}
        <ShimpzBrand href={u.home(lang)} />
      {/if}
      <p>{tr("footer", lang)}</p>
    </div>
    <nav aria-label={lang === "pt" ? "Links do rodapé" : "Footer links"}>
      <a href="https://docs.shimpz.com" target="_blank" rel="noopener noreferrer">Docs ↗</a>
      <a href="https://github.com/TheShimpz" target="_blank" rel="noopener noreferrer">GitHub ↗</a>
    </nav>
    <span class="environment"><i aria-hidden="true"></i> Space platform // development</span>
  </div>
</footer>

<style>
  .site-footer {
    margin-top: clamp(5rem, 10vw, 8rem);
    border-top: 1px solid var(--color-border);
  }

  .footer-inner {
    display: grid;
    min-height: 8.5rem;
    grid-template-columns: 1fr auto;
    align-items: center;
    gap: 1.5rem;
  }

  .footer-brand { display: flex; align-items: center; gap: 1.5rem; }
  .footer-brand p { max-width: 34rem; margin: 0; color: var(--color-muted-2); font-size: 0.78rem; }
  .wordmark { font-family: var(--font-mono); font-size: 1rem; font-weight: 700; letter-spacing: -0.04em; }

  nav { display: flex; gap: 1rem; }
  nav a {
    color: var(--color-muted);
    font-family: var(--font-mono);
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  nav a:hover { color: var(--color-cyan); }

  .environment {
    display: inline-flex;
    grid-column: 1 / -1;
    align-items: center;
    gap: 0.45rem;
    padding: 0.85rem 0;
    border-top: 1px solid var(--color-border);
    color: var(--color-muted-2);
    font-family: var(--font-mono);
    font-size: 0.6rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .environment i {
    width: 0.42rem;
    height: 0.42rem;
    background: var(--color-green);
    border-radius: 50%;
    box-shadow: 0 0 8px rgba(5, 255, 161, 0.55);
  }

  @media (max-width: 620px) {
    .footer-inner { grid-template-columns: 1fr; padding-block: 1.5rem; }
    .footer-brand { align-items: flex-start; flex-direction: column; gap: 0.75rem; }
    nav { justify-content: flex-start; }
    .environment { grid-column: 1; }
  }
</style>

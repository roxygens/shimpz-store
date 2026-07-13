<script lang="ts">
  import { APPS, usedCategories, type AppCategory, type Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import Seo from "$lib/components/Seo.svelte";
  import AppCard from "$lib/components/AppCard.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);

  // The home IS the marketplace: every REAL Shimpz (the catalog carries only registry-backed ones),
  // filtered by the lateral category sidebar.
  let selected = $state<AppCategory | "">("");
  const shown = $derived(selected ? APPS.filter((a) => a.category === selected) : APPS);

  let copied = $state(false);
  function copyInstall() {
    navigator.clipboard?.writeText("curl -fsSL https://install.shimpz.com | sh");
    copied = true;
    setTimeout(() => (copied = false), 1600);
  }
</script>

<Seo title={tr("home_title", lang)} description={tr("home_desc", lang)} {lang} />

<section class="wrap pt-14 pb-6 sm:pt-20">
  <span class="badge" style="border-color:color-mix(in oklab, var(--color-primary) 30%, var(--color-border))">
    <span class="mr-1.5 inline-block size-1.5 rounded-full" style="background:var(--color-primary)"></span>
    Shimpz · {tr("brand_tag", lang)}
  </span>
  <h1 class="mt-6 max-w-4xl text-5xl font-extrabold leading-[1.04] tracking-tight sm:text-6xl">
    {tr("pitch_a", lang)} <span class="gradient-text">{tr("pitch_b", lang)}</span> {tr("pitch_c", lang)}
  </h1>
  <p class="mt-5 max-w-2xl text-lg leading-relaxed dim">{tr("pitch_sub", lang)}</p>

  <!-- the install one-liner (ADR-0005): self-host a Capsule on your own machine -->
  <div class="mt-8 max-w-2xl">
    <div class="panel flex items-center gap-3 !py-3 !px-4">
      <span class="mono shrink-0 text-sm" style="color:var(--color-primary)">$</span>
      <code class="mono min-w-0 flex-1 truncate text-sm">curl -fsSL https://install.shimpz.com | sh</code>
      <button class="btn-ghost !px-3 !py-1.5 text-xs" onclick={copyInstall}>{copied ? tr("copied", lang) : tr("copy", lang)}</button>
    </div>
    <div class="mt-4 flex flex-wrap gap-3">
      <a href={u.install(lang)} class="btn-primary">{tr("install_cta", lang)} →</a>
      <a href={u.capsule(lang)} class="btn-ghost">{tr("or_hosted", lang)}</a>
    </div>
  </div>
</section>

<section class="wrap mt-10 flex flex-col gap-8 lg:flex-row">
  <aside class="lg:w-56 lg:shrink-0">
    <div class="lg:sticky lg:top-24">
      <span class="kicker">{tr("categories", lang)}</span>
      <nav class="mt-3 flex flex-wrap gap-2 lg:flex-col lg:gap-1">
        <button
          class="rounded-lg px-3 py-2 text-left text-sm transition hover:text-[var(--color-fg)]"
          style={selected === "" ? "background:var(--color-elevated);color:var(--color-fg);font-weight:600" : "color:var(--color-muted)"}
          onclick={() => (selected = "")}>{tr("all_apps", lang)} <span class="ml-1 text-xs dim">{APPS.length}</span></button>
        {#each usedCategories() as cat (cat)}
          <button
            class="rounded-lg px-3 py-2 text-left text-sm transition hover:text-[var(--color-fg)]"
            style={selected === cat ? "background:var(--color-elevated);color:var(--color-fg);font-weight:600" : "color:var(--color-muted)"}
            onclick={() => (selected = selected === cat ? "" : cat)}>{cat}</button>
        {/each}
      </nav>
    </div>
  </aside>

  <div class="min-w-0 flex-1">
    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {#each shown as app (app.id)}<AppCard {app} {lang} />{/each}
    </div>
    {#if shown.length === 0}<p class="dim">{tr("no_apps", lang)}</p>{/if}
  </div>
</section>

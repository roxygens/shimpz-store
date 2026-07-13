<script lang="ts">
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import Seo from "$lib/components/Seo.svelte";
  import Breadcrumbs from "$lib/components/Breadcrumbs.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);

  const USE_CMD = "curl -fsSL https://install.shimpz.com | sh";
  const DEV_CMD = "curl -fsSL https://install.shimpz.com | sh -s -- --dev";
  let copied = $state("");
  function copy(cmd: string) {
    navigator.clipboard?.writeText(cmd);
    copied = cmd;
    setTimeout(() => (copied = ""), 1600);
  }
</script>

<Seo title={tr("install_title", lang)} description={tr("install_lead", lang)} {lang} />

<section class="wrap pt-10 pb-16">
  <Breadcrumbs items={[{ label: tr("home", lang), href: u.home(lang) }, { label: tr("nav_install", lang) }]} />
  <h1 class="mt-6 max-w-3xl text-4xl font-extrabold tracking-tight sm:text-5xl">{tr("nav_install", lang)}</h1>
  <p class="mt-4 max-w-2xl text-lg leading-relaxed dim">{tr("install_lead", lang)}</p>

  <div class="mt-10 grid gap-6 lg:grid-cols-2">
    <!-- Captain: use -->
    <div class="panel space-y-4">
      <span class="kicker">{tr("install_captain_t", lang)}</span>
      <p class="text-sm leading-relaxed dim">{tr("install_captain_d", lang)}</p>
      <div class="flex items-center gap-3 border p-3" style="border-color:var(--color-border);background:#000;clip-path:polygon(8px 0,100% 0,100% calc(100% - 8px),calc(100% - 8px) 100%,0 100%,0 8px)">
        <span class="mono shrink-0 text-sm" style="color:var(--color-primary)">$</span>
        <code class="mono min-w-0 flex-1 overflow-x-auto whitespace-nowrap text-xs">{USE_CMD}</code>
        <button class="btn-ghost !px-3 !py-1.5 text-xs" onclick={() => copy(USE_CMD)}>{copied === USE_CMD ? tr("copied", lang) : tr("copy", lang)}</button>
      </div>
      <p class="text-xs dim">{tr("install_reqs", lang)} <code class="mono" style="color:var(--color-primary)">http://localhost:7777</code></p>
    </div>

    <!-- Developer: build -->
    <div class="panel space-y-4">
      <span class="kicker">{tr("install_dev_t", lang)}</span>
      <p class="text-sm leading-relaxed dim">{tr("install_dev_d", lang)}</p>
      <div class="flex items-center gap-3 border p-3" style="border-color:var(--color-border);background:#000;clip-path:polygon(8px 0,100% 0,100% calc(100% - 8px),calc(100% - 8px) 100%,0 100%,0 8px)">
        <span class="mono shrink-0 text-sm" style="color:var(--color-primary)">$</span>
        <code class="mono min-w-0 flex-1 overflow-x-auto whitespace-nowrap text-xs">{DEV_CMD}</code>
        <button class="btn-ghost !px-3 !py-1.5 text-xs" onclick={() => copy(DEV_CMD)}>{copied === DEV_CMD ? tr("copied", lang) : tr("copy", lang)}</button>
      </div>
      <p class="text-xs dim">{tr("install_reqs", lang)} <code class="mono" style="color:var(--color-primary)">http://localhost:7777</code></p>
    </div>
  </div>

  <div class="panel mt-6 max-w-3xl">
    <span class="kicker">{tr("install_manage", lang)}</span>
    <pre class="mono mt-3 overflow-x-auto text-xs" style="color:var(--color-muted)">cd ~/.shimpz &amp;&amp; docker compose logs      # ver os logs
cd ~/.shimpz &amp;&amp; docker compose down       # parar
cd ~/.shimpz &amp;&amp; docker compose up -d       # subir de novo</pre>
  </div>
</section>

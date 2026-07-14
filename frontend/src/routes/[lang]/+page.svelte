<script lang="ts">
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import Seo from "$lib/components/Seo.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);
</script>

<Seo title={tr("home_title", lang)} description={tr("home_desc", lang)} {lang} />

<div class="wrap">
  <section class="pt-14 pb-6 sm:pt-20">
    <span class="badge" style="border-color:color-mix(in oklab, var(--color-primary) 30%, var(--color-border))">
      <span class="mr-1.5 inline-block size-1.5 rounded-full" style="background:var(--color-primary)"></span>
      Shimpz · {tr("home_badge", lang)}
    </span>
    <h1 class="mt-6 max-w-4xl text-5xl font-extrabold leading-[1.04] tracking-tight text-balance sm:text-6xl">
      {tr("pitch_a", lang)} <span style="color:var(--color-primary)">{tr("pitch_b", lang)}</span>{tr("pitch_c", lang)}
    </h1>
    <p class="mt-5 max-w-2xl text-lg leading-relaxed dim text-pretty">{tr("pitch_sub", lang)}</p>

    <div class="mt-8">
      <a href={u.capsule(lang)} class="btn-primary">{tr("create_capsule", lang)} →</a>
    </div>
  </section>
</div>

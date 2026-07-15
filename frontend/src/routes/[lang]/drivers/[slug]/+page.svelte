<script lang="ts">
  import { t, creatorOf, type Driver, type Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import Seo from "$lib/components/Seo.svelte";
  import Icon from "$lib/components/Icon.svelte";
  import CreatorTag from "$lib/components/CreatorTag.svelte";
  import PageIntro from "$lib/components/PageIntro.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);
  const driver = $derived(data.driver as Driver);
</script>

<Seo title={`${driver.name} · Shimpz drivers`} description={t(driver.summary, lang)} {lang} />

<section class="wrap pt-10" aria-labelledby="driver-title">
  {#snippet media()}
    <Icon glyph={driver.icon} id={driver.id} size={80} brand={driver.brand} />
  {/snippet}
  {#snippet meta()}
    <CreatorTag handle={creatorOf(driver)} {lang} />
  {/snippet}
  <PageIntro
    headingId="driver-title"
    kicker={driver.category}
    title={driver.name}
    description={t(driver.summary, lang)}
    {media}
    {meta} />

  <div class="mt-10 grid gap-8 lg:grid-cols-[1fr_320px]">
    <div class="space-y-10">
      <div>
        <h2 class="kicker">{tr("what_it_does", lang)}</h2>
        <p class="mt-3 max-w-2xl text-lg leading-relaxed">{t(driver.blurb, lang)}</p>
      </div>
      <div>
        <h2 class="kicker">{tr("features_title", lang)} <span class="ml-1 opacity-60">{driver.features.length}</span></h2>
        <ul class="mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-2">
          {#each driver.features as f (f.en)}
            <li class="flex gap-2.5 text-sm leading-relaxed">
              <span class="mt-px shrink-0" style="color:var(--color-primary)">▸</span>
              <span>{t(f, lang)}</span>
            </li>
          {/each}
        </ul>
      </div>
    </div>

    <aside class="lg:sticky lg:top-32 lg:self-start">
      <div class="panel">
        <h2 class="kicker">{tr("access_boundary", lang)}</h2>
        <ul class="mt-4 space-y-3 text-sm">
          {#each driver.boundaries as boundary (boundary.en)}
            <li class="flex gap-2"><span style="color:var(--color-primary)">✓</span><span>{t(boundary, lang)}</span></li>
          {/each}
        </ul>
      </div>
    </aside>
  </div>
</section>

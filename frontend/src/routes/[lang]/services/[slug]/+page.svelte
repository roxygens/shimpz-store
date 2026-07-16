<script lang="ts">
  import { t, creatorOf, type Locale, type Service } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import Seo from "$lib/components/Seo.svelte";
  import ServiceIcon from "$lib/components/ServiceIcon.svelte";
  import CreatorTag from "$lib/components/CreatorTag.svelte";
  import InstallCommand from "$lib/components/InstallCommand.svelte";
  import PageIntro from "$lib/components/PageIntro.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);
  const service = $derived(data.service as Service);
</script>

<Seo title={`${service.name} · Shimpz Services`} description={t(service.summary, lang)} {lang} />

<section class="wrap pt-10" aria-labelledby="service-title">
  {#snippet media()}
    <ServiceIcon icon={service.icon} size={80} brand={service.brand} />
  {/snippet}
  {#snippet meta()}
    <CreatorTag handle={creatorOf(service)} {lang} showAvatar={false} />
  {/snippet}
  <PageIntro
    headingId="service-title"
    kicker={service.category}
    title={service.name}
    description={t(service.summary, lang)}
    {media}
    {meta} />

  <div class="panel mt-8 grid gap-5 lg:grid-cols-[minmax(0,0.7fr)_minmax(0,1fr)] lg:items-center">
    <div>
      <h2 class="kicker">{tr("service_quick_install_title", lang)}</h2>
      <p class="mt-3 text-sm leading-relaxed dim">{tr("service_quick_install_body", lang)}</p>
    </div>
    <InstallCommand {lang} />
  </div>

  <div class="mt-10 grid gap-8 lg:grid-cols-[1fr_320px]">
    <div class="space-y-10">
      <div>
        <h2 class="kicker">{tr("what_it_does", lang)}</h2>
        <p class="mt-3 max-w-2xl text-lg leading-relaxed">{t(service.blurb, lang)}</p>
      </div>
      <div>
        <h2 class="kicker">{tr("features_title", lang)} <span class="ml-1 opacity-60">{service.features.length}</span></h2>
        <ul class="mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-2">
          {#each service.features as feature (feature.en)}
            <li class="flex gap-2.5 text-sm leading-relaxed">
              <span class="mt-px shrink-0" style="color:var(--color-primary)">▸</span>
              <span>{t(feature, lang)}</span>
            </li>
          {/each}
        </ul>
      </div>
    </div>

    <aside class="lg:sticky lg:top-32 lg:self-start">
      <div class="panel">
        <h2 class="kicker">{tr("access_boundary", lang)}</h2>
        <ul class="mt-4 space-y-3 text-sm">
          {#each service.boundaries as boundary (boundary.en)}
            <li class="flex gap-2"><span style="color:var(--color-primary)">✓</span><span>{t(boundary, lang)}</span></li>
          {/each}
        </ul>
      </div>
    </aside>
  </div>
</section>

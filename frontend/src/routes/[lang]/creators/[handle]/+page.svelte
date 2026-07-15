<script lang="ts">
  import { t, type Driver, type Creator, type Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import Seo from "$lib/components/Seo.svelte";
  import DriverCard from "$lib/components/DriverCard.svelte";
  import PageIntro from "$lib/components/PageIntro.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);
  const cap = $derived(data.creator as Creator);
  const drivers = $derived(data.drivers as Driver[]);
</script>

<Seo title={`${cap.name} (@${cap.handle}) · Shimpz`} description={t(cap.bio, lang)} {lang} />

<section class="wrap pt-10" aria-labelledby="creator-title">
  {#snippet media()}
    <img
      src={`https://github.com/${cap.github}.png?size=200`}
      alt={cap.name}
      width="96"
      height="96"
      class="size-24 shrink-0 rounded-full"
      style="box-shadow:inset 0 0 0 1px var(--color-border-strong)"
      onerror={(e) => ((e.currentTarget as HTMLImageElement).style.display = "none")} />
  {/snippet}
  {#snippet meta()}
    <a href={`https://github.com/${cap.github}`} target="_blank" rel="noopener" class="btn-ghost inline-flex !py-2 text-sm">{tr("view_github", lang)}</a>
  {/snippet}
  <PageIntro
    headingId="creator-title"
    kicker={`@${cap.handle}`}
    title={cap.name}
    description={t(cap.bio, lang)}
    {media}
    {meta} />

  {#if drivers.length}
    <div class="mt-12">
      <h2 class="kicker">{tr("created_drivers", lang)} <span class="ml-1 opacity-60">{drivers.length}</span></h2>
      <div class="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {#each drivers as driver (driver.id)}<DriverCard {driver} {lang} />{/each}
      </div>
    </div>
  {/if}

  {#if !drivers.length}
    <p class="mt-12 dim">{tr("creator_none", lang)}</p>
  {/if}
</section>

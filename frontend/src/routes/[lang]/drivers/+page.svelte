<script lang="ts">
  import { DRIVERS, type Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import Seo from "$lib/components/Seo.svelte";
  import DriverCard from "$lib/components/DriverCard.svelte";
  import PageIntro from "$lib/components/PageIntro.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);
</script>

<Seo title={`${tr("drivers_title", lang)} · Shimpz`} description={tr("drivers_lead", lang)} {lang} />

<section class="wrap pt-10" aria-labelledby="drivers-title">
  <PageIntro
    headingId="drivers-title"
    title={tr("drivers_title", lang)}
    description={tr("drivers_lead", lang)} />

  <div class="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
    {#each DRIVERS as driver (driver.id)}<DriverCard {driver} {lang} />{/each}
  </div>
</section>

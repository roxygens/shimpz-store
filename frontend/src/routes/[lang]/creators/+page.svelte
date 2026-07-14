<script lang="ts">
  import { CREATORS, driversByCreator, type Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import Seo from "$lib/components/Seo.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);
</script>

<Seo title={`${tr("creators_title", lang)} · Shimpz`} description={tr("creators_lead", lang)} {lang} />

<section class="wrap pt-10">
  <h1 class="text-3xl font-bold">{tr("creators_title", lang)}</h1>
  <p class="mt-3 max-w-2xl dim">{tr("creators_lead", lang)}</p>

  <div class="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
    {#each CREATORS as c (c.handle)}
      <a class="card" href={u.creator(lang, c.handle)}>
        <div class="flex items-center gap-4">
          <img
            src={`https://github.com/${c.github}.png?size=96`}
            alt=""
            width="52"
            height="52"
            loading="lazy"
            class="size-12 rounded-full"
            style="box-shadow:inset 0 0 0 1px var(--color-border-strong)"
            onerror={(e) => ((e.currentTarget as HTMLImageElement).style.display = "none")} />
          <div class="min-w-0">
            <div class="truncate font-semibold">{c.name}</div>
            <div class="mono truncate text-xs" style="color:var(--color-primary)">@{c.handle}</div>
          </div>
        </div>
        <p class="mt-4 text-xs dim">{driversByCreator(c.handle).length} drivers</p>
      </a>
    {/each}
  </div>
</section>

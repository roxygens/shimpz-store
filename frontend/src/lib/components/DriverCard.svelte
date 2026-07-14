<script lang="ts">
  import { t, creatorOf, type Driver, type Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import Icon from "./Icon.svelte";
  import CreatorTag from "./CreatorTag.svelte";

  let { driver, lang }: { driver: Driver; lang: Locale } = $props();
</script>

<div class="card relative flex flex-col">
  <a href={u.driver(lang, driver)} class="absolute inset-0" aria-label={driver.name}></a>
  <div class="flex items-start gap-4">
    <Icon glyph={driver.icon} id={driver.id} size={52} brand={driver.brand} />
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <span class="truncate text-[15px] font-semibold">{driver.name}</span>
        <span class="badge">{driver.category}</span>
      </div>
      <p class="mt-1 line-clamp-2 text-sm dim">{t(driver.summary, lang)}</p>
      <div class="relative z-10 mt-2 w-fit"><CreatorTag handle={creatorOf(driver)} {lang} /></div>
    </div>
  </div>
  <p class="mt-auto pt-4 text-xs dim">{driver.features.length} {tr("capabilities", lang)}</p>
</div>

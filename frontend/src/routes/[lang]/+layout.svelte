<script lang="ts">
  import { page } from "$app/stores";
  import type { Locale } from "$lib/catalog";
  import SiteFooter from "$lib/components/SiteFooter.svelte";
  import SiteHeader from "$lib/components/SiteHeader.svelte";

  let { data, children } = $props();
  const lang = $derived(data.lang as Locale);
  const path = $derived($page.url.pathname);
  const embedded = $derived(/^\/(?:en|pt)\/assistants\/embed\/?$/.test(path));
</script>

{#if !embedded}<SiteHeader {lang} {path} />{/if}

<main id="main-content" class:embedded>
  {@render children()}
</main>

{#if !embedded}<SiteFooter {lang} />{/if}

<style>
  main { min-height: calc(100vh - 12rem); }
  main.embedded { min-height: 100vh; padding-bottom: 2rem; }
</style>

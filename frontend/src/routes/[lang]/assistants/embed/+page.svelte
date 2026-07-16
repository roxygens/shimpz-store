<script lang="ts">
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import AssistantStore from "$lib/components/AssistantStore.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);
</script>

<svelte:head>
  <title>{tr("assistants_title", lang)} · Shimpz</title>
  <meta name="description" content={tr("assistants_lead", lang)} />
  <meta name="robots" content="noindex,nofollow" />
  <link rel="canonical" href={`https://shimpz.com/${lang}/assistants`} />
</svelte:head>

<AssistantStore {lang} />

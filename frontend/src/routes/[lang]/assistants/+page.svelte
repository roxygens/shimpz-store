<script lang="ts">
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import AssistantStore from "$lib/components/AssistantStore.svelte";
  import Seo from "$lib/components/Seo.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);
</script>

<Seo title={`${tr("assistants_title", lang)} · Shimpz`} description={tr("assistants_lead", lang)} {lang} />
<AssistantStore {lang} />

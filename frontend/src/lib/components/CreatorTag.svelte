<script lang="ts">
  // "Created by @handle" — the Creator who built a Shimpz/driver, linking to their profile.
  import { CREATOR_BY_HANDLE, type Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";

  let {
    handle,
    lang,
    showAvatar = true,
  }: { handle: string; lang: Locale; showAvatar?: boolean } = $props();
  const cap = $derived(CREATOR_BY_HANDLE.get(handle));
</script>

{#if cap}
  <a href={u.creator(lang, cap.handle)} class="inline-flex items-center gap-2 text-sm transition hover:opacity-80">
    {#if showAvatar}
      <img
        src={`https://github.com/${cap.github}.png?size=48`}
        alt=""
        width="24"
        height="24"
        loading="lazy"
        class="size-6 rounded-full"
        style="box-shadow:inset 0 0 0 1px var(--color-border-strong)"
        onerror={(e) => ((e.currentTarget as HTMLImageElement).style.display = "none")} />
    {/if}
    <span class="dim">{tr("created_by", lang)}</span>
    <span class="mono" style="color:var(--color-primary)">@{cap.handle}</span>
  </a>
{/if}

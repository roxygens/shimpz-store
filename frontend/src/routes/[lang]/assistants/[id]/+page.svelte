<script lang="ts">
  import { t, type AssistantListing, type Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import { closedAssistantStoreHref } from "$lib/cloudAssistantLifecycle.js";
  import AssistantIcon from "$lib/components/AssistantIcon.svelte";
  import HudIcon from "$lib/components/HudIcon.svelte";
  import PageIntro from "$lib/components/PageIntro.svelte";
  import Seo from "$lib/components/Seo.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);
  const assistant = $derived(data.assistant as AssistantListing);
</script>

<Seo title={`${assistant.name} · Shimpz Assistants`} description={t(assistant.summary, lang)} {lang} />

<section class="wrap assistant-detail" aria-labelledby="assistant-title">
  <a class="back-link" href={u.assistants(lang)}><span aria-hidden="true">←</span>{tr("assistants_back_store", lang)}</a>

  {#snippet media()}<AssistantIcon size={82} />{/snippet}
  {#snippet meta()}
    <span class="creator">@{assistant.creator}</span>
    <span class="free-badge">{tr("assistants_free", lang)}</span>
  {/snippet}
  <PageIntro
    headingId="assistant-title"
    kicker="Assistant"
    title={assistant.name}
    description={t(assistant.summary, lang)}
    {media}
    {meta} />

  <div class="detail-grid">
    <main>
      <section aria-labelledby="assistant-about-title">
        <h2 id="assistant-about-title">{tr("assistants_detail_about", lang)}</h2>
        <p class="about-copy">{t(assistant.description, lang)}</p>
      </section>

      <section class="powers" aria-labelledby="assistant-powers-title">
        <p class="kicker">{tr("assistants_detail_powers", lang)}</p>
        <h2 id="assistant-powers-title">{assistant.powers.length} {tr("assistants_power", lang)}</h2>
        <ul>
          {#each assistant.powers as power (power.id)}
            <li>
              <span class="power-icon" aria-hidden="true"><HudIcon name="retry" size={18} /></span>
              <div>
                <code>{power.id}</code>
                <strong>{t(power.name, lang)}</strong>
                <p>{t(power.summary, lang)}</p>
              </div>
            </li>
          {/each}
        </ul>
      </section>
    </main>

    <aside>
      <dl class="facts">
        <div><dt>{tr("assistants_version", lang)}</dt><dd>{assistant.version}</dd></div>
        <div><dt>{tr("assistants_architectures", lang)}</dt><dd>{assistant.archs.join(" + ")}</dd></div>
        <div>
          <dt>{tr("assistants_permissions", lang)}</dt>
          <dd>
            {#if assistant.permissions.length}
              <ul class="permission-list">
                {#each assistant.permissions as permission}
                  <li>{t(permission, lang)}</li>
                {/each}
              </ul>
            {:else}
              {tr("assistants_no_permissions", lang)}
            {/if}
          </dd>
        </div>
      </dl>
      <a
        class="btn-primary install-link"
        href={closedAssistantStoreHref(lang, assistant.id)}>
        <HudIcon name="add" size={18} />{tr("assistants_cloud_choose", lang)}
      </a>
    </aside>
  </div>
</section>

<style>
  .assistant-detail { padding-top: 1.5rem; }
  .back-link { display: inline-flex; align-items: center; gap: 0.55rem; margin-bottom: 1rem; color: var(--color-cyan); font-family: var(--font-mono); font-size: 0.68rem; font-weight: 600; text-transform: uppercase; }
  .back-link span { color: var(--color-magenta); }
  .creator, .free-badge { font-family: var(--font-mono); font-size: 0.64rem; }
  .creator { color: var(--color-muted); }
  .free-badge { border: 1px solid color-mix(in oklab, var(--color-green) 38%, var(--color-border)); padding: 0.25rem 0.45rem; color: var(--color-green); font-weight: 700; text-transform: uppercase; }
  .detail-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(17rem, 21rem); gap: clamp(2rem, 6vw, 5rem); margin-top: 2rem; }
  .detail-grid main { display: grid; gap: 2.5rem; }
  .detail-grid main h2 { margin: 0.45rem 0 0; font-size: clamp(1.35rem, 2.5vw, 1.8rem); }
  .about-copy { max-width: 48rem; margin: 0.75rem 0 0; color: var(--color-muted); font-size: clamp(1rem, 1.8vw, 1.15rem); line-height: 1.7; }
  .powers h2 { margin: 0.45rem 0 0; font-size: 1.35rem; }
  .powers ul { display: grid; gap: 0.7rem; margin: 1rem 0 0; padding: 0; list-style: none; }
  .powers li { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 0.8rem; border: 1px solid var(--color-border); padding: 0.9rem; background: var(--color-card); }
  .power-icon { display: grid; width: 2.5rem; height: 2.5rem; place-items: center; color: var(--color-yellow); background: #000; }
  .powers code { color: var(--color-cyan); font-size: 0.62rem; }
  .powers strong { display: block; margin-top: 0.2rem; font-family: var(--font-mono); font-size: 0.9rem; }
  .powers li p { margin: 0.25rem 0 0; color: var(--color-muted); font-size: 0.8rem; line-height: 1.55; }
  .detail-grid aside { align-self: start; background: var(--color-card); box-shadow: inset 0 0 0 1px var(--color-border); }
  .facts { margin: 0; }
  .facts div { padding: 0.9rem 1rem; border-bottom: 1px solid var(--color-border); }
  .facts dt { color: var(--color-muted-2); font-family: var(--font-mono); font-size: 0.56rem; letter-spacing: 0.08em; text-transform: uppercase; }
  .facts dd { margin: 0.3rem 0 0; color: var(--color-fg); font-size: 0.76rem; overflow-wrap: anywhere; }
  .permission-list { display: grid; gap: 0.45rem; margin: 0; padding: 0; list-style: none; }
  .permission-list li { position: relative; padding-left: 0.75rem; line-height: 1.45; }
  .permission-list li::before { position: absolute; left: 0; color: var(--color-cyan); content: "·"; }
  .install-link { width: calc(100% - 2rem); margin: 1rem; padding-inline: 0.75rem; font-size: 0.62rem; }
  @media (max-width: 760px) {
    .detail-grid { grid-template-columns: 1fr; }
  }
</style>

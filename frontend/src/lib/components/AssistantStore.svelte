<script lang="ts">
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import PageIntro from "$lib/components/PageIntro.svelte";

  let { lang }: { lang: Locale } = $props();

  const principles = [
    ["assistants_capsule_title", "assistants_capsule_body", "CAPSULE // 01"],
    ["assistants_capabilities_title", "assistants_capabilities_body", "CAPABILITY // 02"],
    ["assistants_routines_title", "assistants_routines_body", "ROUTINE // 03"],
    ["assistants_secrets_title", "assistants_secrets_body", "SECRET // 04"],
  ] as const;

  const steps = [
    "assistants_step_manifest",
    "assistants_step_operations",
    "assistants_step_permissions",
    "assistants_step_routines",
  ] as const;
</script>

<section class="wrap assistants-page" aria-labelledby="assistants-title">
  <PageIntro
    headingId="assistants-title"
    kicker={tr("assistants_preview", lang)}
    title={tr("assistants_title", lang)}
    description={tr("assistants_lead", lang)} />

  <p class="preview-notice"><span aria-hidden="true">PREVIEW</span>{tr("assistants_preview_notice", lang)}</p>

  <section class="model" aria-labelledby="assistant-model-title">
    <header class="section-copy">
      <p class="kicker">{tr("assistants_model_kicker", lang)}</p>
      <h2 id="assistant-model-title">{tr("assistants_model_title", lang)}</h2>
      <p>{tr("assistants_model_lead", lang)}</p>
    </header>

    <div class="principle-grid">
      {#each principles as principle (principle[0])}
        <article class="panel">
          <span>{principle[2]}</span>
          <h3>{tr(principle[0], lang)}</h3>
          <p>{tr(principle[1], lang)}</p>
        </article>
      {/each}
    </div>
  </section>

  <section class="creator-panel" aria-labelledby="creator-path-title">
    <div class="creator-copy">
      <p class="kicker">{tr("assistants_creator_kicker", lang)}</p>
      <h2 id="creator-path-title">{tr("assistants_creator_title", lang)}</h2>
      <p>{tr("assistants_creator_lead", lang)}</p>
      <a class="btn-ghost" href="https://docs.shimpz.com/developers/assistants/" target="_blank" rel="noopener noreferrer">
        {tr("assistants_read_spec", lang)} <span aria-hidden="true">↗</span>
        <span class="sr-only"> ({tr("opens_new_tab", lang)})</span>
      </a>
    </div>
    <ol>
      {#each steps as step, index (step)}
        <li><span>{String(index + 1).padStart(2, "0")}</span>{tr(step, lang)}</li>
      {/each}
    </ol>
  </section>

  <div class="future-grid">
    <article class="example" aria-labelledby="salesnator-title">
      <p class="kicker">{tr("assistants_example_kicker", lang)}</p>
      <h2 id="salesnator-title">{tr("assistants_example_title", lang)}</h2>
      <p>{tr("assistants_example_body", lang)}</p>
      <ul aria-label={lang === "pt" ? "Limites do exemplo Salesnator" : "Salesnator example boundaries"}>
        <li>campaign-health</li>
        <li>meta-ads.read</li>
        <li>notifications.send</li>
      </ul>
    </article>

    <aside class="later" aria-labelledby="marketplace-title">
      <span aria-hidden="true">⌁</span>
      <div>
        <p class="kicker">{tr("assistants_later_kicker", lang)}</p>
        <h2 id="marketplace-title">{tr("assistants_later_title", lang)}</h2>
        <p>{tr("assistants_later_body", lang)}</p>
      </div>
    </aside>
  </div>
</section>

<style>
  .assistants-page { padding-top: 2.5rem; }
  .preview-notice {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    margin: 1rem 0 0;
    padding: 0.85rem 1rem;
    border-left: 2px solid var(--color-yellow);
    background: color-mix(in oklab, var(--color-yellow) 5%, var(--color-card));
    color: var(--color-muted);
    font-size: 0.85rem;
  }
  .preview-notice span { color: var(--color-yellow); font-family: var(--font-mono); font-size: 0.62rem; font-weight: 700; letter-spacing: 0.1em; }
  .model, .creator-panel, .future-grid { margin-top: clamp(4rem, 8vw, 7rem); }

  .section-copy {
    display: grid;
    max-width: 68rem;
    grid-template-columns: minmax(18rem, 0.9fr) minmax(24rem, 1.1fr);
    column-gap: clamp(2rem, 8vw, 7rem);
  }

  .section-copy .kicker { grid-column: 1 / -1; margin: 0 0 1rem; }
  .section-copy h2, .creator-copy h2, .example h2, .later h2 {
    margin: 0;
    font-size: clamp(1.85rem, 4vw, 3.35rem);
    line-height: 1.05;
    letter-spacing: -0.06em;
  }
  .section-copy > p:last-child, .creator-copy > p, .example > p:last-of-type, .later p:last-child {
    margin: 0;
    align-self: end;
    color: var(--color-muted);
    line-height: 1.72;
  }

  .principle-grid {
    display: grid;
    margin-top: 2rem;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.75rem;
  }
  .principle-grid article { min-height: 14rem; }
  .principle-grid span {
    color: var(--color-muted-2);
    font-family: var(--font-mono);
    font-size: 0.58rem;
    font-weight: 600;
    letter-spacing: 0.1em;
  }
  .principle-grid h3 { margin: 3.5rem 0 0.65rem; font-size: 1.15rem; }
  .principle-grid p { margin: 0; color: var(--color-muted); font-size: 0.88rem; line-height: 1.65; }

  .creator-panel {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(18rem, 0.8fr);
    gap: clamp(2rem, 7vw, 6rem);
    padding: clamp(1.5rem, 4vw, 3rem);
    background: linear-gradient(120deg, color-mix(in oklab, var(--color-cyan) 7%, var(--color-card)), var(--color-card));
    box-shadow: inset 0 0 0 1px var(--color-border);
    clip-path: polygon(var(--cut-lg) 0, 100% 0, 100% calc(100% - var(--cut-lg)), calc(100% - var(--cut-lg)) 100%, 0 100%, 0 var(--cut-lg));
  }
  .creator-copy .kicker { margin: 0 0 0.9rem; }
  .creator-copy > p { max-width: 42rem; margin-top: 1rem; }
  .creator-copy a { margin-top: 1.6rem; }
  .creator-panel ol { display: grid; margin: 0; padding: 0; gap: 0.55rem; list-style: none; }
  .creator-panel li {
    display: grid;
    min-height: 3.5rem;
    grid-template-columns: 2.2rem 1fr;
    align-items: center;
    gap: 0.75rem;
    border-bottom: 1px solid var(--color-border);
    color: var(--color-muted);
    font-size: 0.88rem;
  }
  .creator-panel li span { color: var(--color-cyan); font-family: var(--font-mono); font-size: 0.65rem; }

  .future-grid { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(19rem, 0.85fr); gap: 1rem; }
  .example, .later {
    padding: clamp(1.5rem, 4vw, 2.5rem);
    background: var(--color-card);
    box-shadow: inset 0 0 0 1px var(--color-border);
  }
  .example .kicker, .later .kicker { margin: 0 0 0.8rem; }
  .example > p:last-of-type { max-width: 48rem; margin-top: 1rem; }
  .example ul { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 1.5rem 0 0; padding: 0; list-style: none; }
  .example li {
    padding: 0.4rem 0.65rem;
    border: 1px solid var(--color-border-strong);
    color: var(--color-cyan);
    font-family: var(--font-mono);
    font-size: 0.65rem;
  }
  .later { display: flex; align-items: flex-start; gap: 1rem; }
  .later > span { color: var(--color-magenta); font-family: var(--font-mono); font-size: 2.5rem; line-height: 1; }
  .later h2 { font-size: clamp(1.5rem, 3vw, 2.35rem); }
  .later p:last-child { margin-top: 0.9rem; }

  @media (max-width: 900px) {
    .principle-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media (max-width: 720px) {
    .section-copy, .creator-panel, .future-grid { grid-template-columns: 1fr; }
    .section-copy > p:last-child { margin-top: 1rem; }
  }
  @media (max-width: 520px) {
    .principle-grid { grid-template-columns: 1fr; }
    .principle-grid article { min-height: auto; }
    .principle-grid h3 { margin-top: 2rem; }
    .example ul { align-items: stretch; flex-direction: column; }
    .example li { overflow-wrap: anywhere; }
  }
</style>

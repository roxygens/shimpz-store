<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    headingId,
    title,
    description,
    kicker,
    media,
    meta,
  }: {
    headingId: string;
    title: string;
    description: string;
    kicker?: string;
    media?: Snippet;
    meta?: Snippet;
  } = $props();
</script>

<header class:has-media={media} class="page-intro">
  {#if media}
    <div class="page-intro__media">
      {@render media()}
    </div>
  {/if}

  <div class="page-intro__copy">
    {#if kicker}<p class="kicker">{kicker}</p>{/if}
    <h1 id={headingId}>{title}</h1>
    <p class="page-intro__description">{description}</p>
    {#if meta}
      <div class="page-intro__meta">
        {@render meta()}
      </div>
    {/if}
  </div>
</header>

<style>
  .page-intro {
    position: relative;
    display: grid;
    min-width: 0;
    padding: clamp(1.25rem, 3vw, 2rem);
    overflow: hidden;
    background:
      linear-gradient(115deg, color-mix(in oklab, var(--color-cyan) 7%, transparent), transparent 42%),
      linear-gradient(180deg, var(--color-card-2), var(--color-card));
    box-shadow: inset 0 0 0 1px var(--color-border);
    clip-path: polygon(
      var(--cut-lg) 0,
      100% 0,
      100% calc(100% - var(--cut-lg)),
      calc(100% - var(--cut-lg)) 100%,
      0 100%,
      0 var(--cut-lg)
    );
  }

  .page-intro::before {
    content: "";
    position: absolute;
    inset: 0 auto auto var(--cut-lg);
    width: clamp(3rem, 12vw, 8rem);
    height: 2px;
    background: linear-gradient(90deg, var(--color-cyan), var(--color-magenta));
    box-shadow: 0 0 12px rgba(0, 240, 255, 0.35);
  }

  .page-intro::after {
    content: "";
    position: absolute;
    right: clamp(1rem, 3vw, 2rem);
    bottom: 0.8rem;
    width: 2.5rem;
    height: 1px;
    background: var(--color-border-strong);
    box-shadow: 0.45rem 0 0 var(--color-border-strong), 0.9rem 0 0 var(--color-border-strong);
  }

  .page-intro.has-media {
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: clamp(1.1rem, 3vw, 2rem);
  }

  .page-intro__media {
    display: grid;
    place-items: center;
    align-self: start;
    padding: 0.65rem;
    background: #000000;
    box-shadow: inset 0 0 0 1px var(--color-border-strong);
    clip-path: polygon(
      var(--cut) 0,
      100% 0,
      100% calc(100% - var(--cut)),
      calc(100% - var(--cut)) 100%,
      0 100%,
      0 var(--cut)
    );
  }

  .page-intro__copy { min-width: 0; }

  .kicker { margin: 0 0 0.65rem; }

  h1 {
    max-width: 20ch;
    margin: 0;
    font-family: var(--font-mono);
    font-size: clamp(2rem, 5vw, 3.65rem);
    font-weight: 700;
    line-height: 1;
    letter-spacing: -0.06em;
    overflow-wrap: anywhere;
  }

  .page-intro__description {
    max-width: 46rem;
    margin: 0.85rem 0 0;
    color: var(--color-muted);
    font-size: clamp(0.95rem, 1.6vw, 1.08rem);
    line-height: 1.7;
  }

  .page-intro__meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.65rem 0.9rem;
    margin-top: 1rem;
  }

  @media (max-width: 639px) {
    .page-intro.has-media { grid-template-columns: minmax(0, 1fr); }
    .page-intro__media { justify-self: start; }
  }

  @media (max-width: 420px) {
    .page-intro { padding: 1.1rem; }
    h1 { font-size: clamp(1.85rem, 11vw, 2.6rem); }
  }

  @media (forced-colors: active) {
    .page-intro,
    .page-intro__media { outline: 1px solid CanvasText; }
    .page-intro::before,
    .page-intro::after { background: CanvasText; box-shadow: none; }
  }
</style>

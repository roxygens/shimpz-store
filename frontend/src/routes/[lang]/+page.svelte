<script lang="ts">
  import type { Locale } from "$lib/catalog";
  import InstallCommand from "$lib/components/InstallCommand.svelte";
  import Seo from "$lib/components/Seo.svelte";
  import SpaceTopology from "$lib/components/SpaceTopology.svelte";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);
</script>

<Seo title={tr("home_title", lang)} description={tr("home_desc", lang)} {lang} />

<section class="hero wrap" aria-labelledby="hero-title">
  <div class="hero-copy">
    <p class="hero-kicker"><i aria-hidden="true"></i>{tr("home_badge", lang)}</p>
    <h1 id="hero-title">
      <span>{tr("home_hero_1", lang)}</span>
      <span>{tr("home_hero_2", lang)}</span>
      <span class="gradient-text">{tr("home_hero_3", lang)}</span>
    </h1>
    <p class="hero-lead">{tr("home_hero_lead", lang)}</p>

    <div class="hero-actions">
      <a class="btn-primary" href="https://docs.shimpz.com" target="_blank" rel="noopener noreferrer">
        {tr("home_install", lang)} <span aria-hidden="true">↗</span><span class="sr-only"> ({tr("opens_new_tab", lang)})</span>
      </a>
      <a class="btn-ghost" href={u.team(lang)}>{tr("home_open_teams", lang)} <span aria-hidden="true">→</span></a>
    </div>

    <ul class="signals" aria-label={lang === "pt" ? "Princípios da plataforma" : "Platform principles"}>
      <li><i aria-hidden="true"></i>{tr("home_signal_self_hosted", lang)}</li>
      <li><i aria-hidden="true"></i>{tr("home_signal_permissions", lang)}</li>
      <li><i aria-hidden="true"></i>{tr("home_signal_isolation", lang)}</li>
    </ul>
  </div>

  <SpaceTopology {lang} />
</section>

<section class="architecture section" aria-labelledby="architecture-title">
  <div class="wrap">
    <div class="section-intro">
      <p class="kicker">{tr("home_arch_kicker", lang)}</p>
      <h2 id="architecture-title">{tr("home_arch_title", lang)}</h2>
      <p>{tr("home_arch_lead", lang)}</p>
    </div>

    <ol class="architecture-flow">
      <li>
        <span class="step">01</span>
        <div>
          <h3>{tr("home_space_title", lang)}</h3>
          <p>{tr("home_space_body", lang)}</p>
        </div>
      </li>
      <li>
        <span class="step">02</span>
        <div>
          <h3>{tr("home_drivers_title", lang)}</h3>
          <p>{tr("home_drivers_body", lang)}</p>
        </div>
      </li>
      <li>
        <span class="step">03</span>
        <div>
          <h3>{tr("home_teams_title", lang)}</h3>
          <p>{tr("home_teams_body", lang)}</p>
        </div>
      </li>
      <li>
        <span class="step">04</span>
        <div>
          <h3>{tr("home_apps_title", lang)}</h3>
          <p>{tr("home_apps_body", lang)}</p>
        </div>
      </li>
    </ol>
  </div>
</section>

<section class="principles section wrap" aria-labelledby="principles-title">
  <div class="principles-intro">
    <p class="kicker">{tr("home_control_kicker", lang)}</p>
    <h2 id="principles-title">{tr("home_control_title", lang)}</h2>
    <p>{tr("home_control_lead", lang)}</p>
  </div>

  <div class="principle-grid">
    <article class="principle-featured">
      <span class="principle-code">ROOT // 01</span>
      <div class="control-orbit" aria-hidden="true"><i></i><i></i><i></i></div>
      <h3>{tr("home_self_title", lang)}</h3>
      <p>{tr("home_self_body", lang)}</p>
    </article>
    <article>
      <span class="principle-code">BOUNDARY // 02</span>
      <h3>{tr("home_isolation_title", lang)}</h3>
      <p>{tr("home_isolation_body", lang)}</p>
    </article>
    <article>
      <span class="principle-code">SPEC // 03</span>
      <h3>{tr("home_specs_title", lang)}</h3>
      <p>{tr("home_specs_body", lang)}</p>
    </article>
  </div>
</section>

<section class="install section wrap" aria-labelledby="install-title">
  <div class="install-copy">
    <p class="kicker">{tr("home_install_kicker", lang)}</p>
    <h2 id="install-title">{tr("home_install_title", lang)}</h2>
    <p>{tr("home_install_lead", lang)}</p>
    <a href="https://docs.shimpz.com" target="_blank" rel="noopener noreferrer">
      {tr("home_read_docs", lang)} <span aria-hidden="true">↗</span><span class="sr-only"> ({tr("opens_new_tab", lang)})</span>
    </a>
  </div>
  <InstallCommand {lang} />
</section>

<style>
  .section { padding-top: clamp(5.5rem, 11vw, 9rem); }

  .hero {
    display: grid;
    min-height: min(760px, calc(100vh - 5.25rem));
    grid-template-columns: minmax(0, 0.95fr) minmax(30rem, 1.05fr);
    align-items: center;
    gap: clamp(2.5rem, 6vw, 5rem);
    padding-block: clamp(4rem, 8vw, 7rem);
  }

  .hero-copy { min-width: 0; }

  .hero-kicker {
    display: inline-flex;
    align-items: center;
    gap: 0.6rem;
    margin: 0 0 1.5rem;
    color: var(--color-cyan);
    font-family: var(--font-mono);
    font-size: 0.66rem;
    font-weight: 600;
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }

  .hero-kicker i {
    width: 0.5rem;
    height: 0.5rem;
    flex: none;
    background: var(--color-green);
    border-radius: 50%;
    box-shadow: 0 0 10px rgba(5, 255, 161, 0.7);
  }

  h1 {
    max-width: 12ch;
    margin: 0;
    font-size: clamp(2.9rem, 5.8vw, 5.7rem);
    font-weight: 700;
    line-height: 0.96;
    letter-spacing: -0.075em;
  }

  h1 span { display: block; }

  .hero-lead {
    max-width: 42rem;
    margin: 1.8rem 0 0;
    color: var(--color-muted);
    font-size: clamp(1rem, 1.4vw, 1.15rem);
    line-height: 1.72;
  }

  .hero-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.7rem;
    margin-top: 2rem;
  }

  .signals {
    display: flex;
    flex-wrap: wrap;
    gap: 0.9rem 1.25rem;
    margin: 2.1rem 0 0;
    padding: 1.15rem 0 0;
    border-top: 1px solid var(--color-border);
    list-style: none;
  }

  .signals li {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    color: var(--color-muted-2);
    font-family: var(--font-mono);
    font-size: 0.58rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .signals i {
    width: 0.28rem;
    height: 0.28rem;
    background: var(--color-cyan);
    transform: rotate(45deg);
  }

  .architecture {
    position: relative;
    border-top: 1px solid var(--color-border);
    border-bottom: 1px solid var(--color-border);
    background:
      linear-gradient(90deg, transparent 49.95%, rgba(255, 255, 255, 0.025) 50%, transparent 50.05%),
      var(--color-card);
    padding-bottom: clamp(5rem, 10vw, 8rem);
  }

  .section-intro,
  .principles-intro {
    display: grid;
    max-width: 68rem;
    grid-template-columns: minmax(18rem, 0.8fr) minmax(24rem, 1.2fr);
    column-gap: clamp(3rem, 9vw, 8rem);
  }

  .section-intro .kicker,
  .principles-intro .kicker { grid-column: 1 / -1; margin: 0 0 1.2rem; }

  h2 {
    margin: 0;
    font-size: clamp(2.15rem, 4.8vw, 4.25rem);
    font-weight: 700;
    line-height: 1.02;
    letter-spacing: -0.065em;
  }

  .section-intro > p:last-child,
  .principles-intro > p:last-child,
  .install-copy > p:last-of-type {
    margin: 0;
    align-self: end;
    color: var(--color-muted);
    font-size: 1rem;
    line-height: 1.72;
  }

  .architecture-flow {
    display: grid;
    margin: clamp(3.5rem, 8vw, 6rem) 0 0;
    padding: 0;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    list-style: none;
  }

  .architecture-flow li {
    position: relative;
    min-height: 15rem;
    padding: 1.4rem 1.25rem;
    border-top: 1px solid var(--color-border-strong);
    border-bottom: 1px solid var(--color-border);
    border-left: 1px solid var(--color-border);
    background: rgba(0, 0, 0, 0.4);
  }

  .architecture-flow li:last-child { border-right: 1px solid var(--color-border); }

  .architecture-flow li::before {
    position: absolute;
    top: -0.23rem;
    left: 1.25rem;
    width: 0.42rem;
    height: 0.42rem;
    background: var(--color-cyan);
    box-shadow: 0 0 8px rgba(0, 240, 255, 0.45);
    content: "";
    transform: rotate(45deg);
  }

  .architecture-flow li:nth-child(3)::before,
  .architecture-flow li:nth-child(4)::before { background: var(--color-magenta); }

  .architecture-flow li > div { position: absolute; right: 1.25rem; bottom: 1.35rem; left: 1.25rem; }

  .step {
    color: var(--color-muted-2);
    font-family: var(--font-mono);
    font-size: 0.66rem;
    font-weight: 600;
    letter-spacing: 0.1em;
  }

  .architecture-flow h3,
  .principle-grid h3 {
    margin: 0;
    font-size: clamp(1.25rem, 2.3vw, 1.75rem);
    font-weight: 700;
    line-height: 1.15;
    letter-spacing: -0.045em;
  }

  .architecture-flow p,
  .principle-grid p {
    margin: 0.75rem 0 0;
    color: var(--color-muted);
    font-size: 0.88rem;
    line-height: 1.65;
  }

  .principle-grid {
    display: grid;
    margin-top: clamp(3rem, 7vw, 5rem);
    grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.8fr);
    gap: 0.75rem;
  }

  .principle-grid article {
    position: relative;
    min-height: 15rem;
    padding: clamp(1.4rem, 3vw, 2rem);
    overflow: hidden;
    background: linear-gradient(145deg, var(--color-card-2), var(--color-card));
    box-shadow: inset 0 0 0 1px var(--color-border);
    clip-path: polygon(var(--cut) 0, 100% 0, 100% calc(100% - var(--cut)), calc(100% - var(--cut)) 100%, 0 100%, 0 var(--cut));
  }

  .principle-grid article:not(.principle-featured) {
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
  }

  .principle-featured {
    min-height: 30.75rem !important;
    grid-row: span 2;
    background:
      radial-gradient(circle at 73% 31%, rgba(0, 240, 255, 0.12), transparent 34%),
      linear-gradient(145deg, var(--color-card-2), var(--color-card)) !important;
  }

  .principle-featured h3,
  .principle-featured p { max-width: 26rem; }
  .principle-featured h3 { margin-top: clamp(13rem, 24vw, 17rem); }

  .principle-code {
    position: absolute;
    top: 1.25rem;
    left: 1.35rem;
    color: var(--color-muted-2);
    font-family: var(--font-mono);
    font-size: 0.58rem;
    font-weight: 600;
    letter-spacing: 0.12em;
  }

  .control-orbit {
    position: absolute;
    top: 3.6rem;
    right: clamp(1.5rem, 8vw, 7rem);
    width: clamp(10rem, 20vw, 15rem);
    aspect-ratio: 1;
    border: 1px solid color-mix(in oklab, var(--color-cyan) 28%, var(--color-border));
    border-radius: 50%;
  }

  .control-orbit::before,
  .control-orbit::after {
    position: absolute;
    border: 1px solid var(--color-border-strong);
    border-radius: 50%;
    content: "";
  }

  .control-orbit::before { inset: 18%; }
  .control-orbit::after { inset: 41%; background: var(--color-cyan); box-shadow: 0 0 18px rgba(0, 240, 255, 0.55); }

  .control-orbit i {
    position: absolute;
    width: 0.5rem;
    height: 0.5rem;
    background: var(--color-magenta);
    box-shadow: 0 0 8px rgba(255, 42, 109, 0.5);
  }

  .control-orbit i:nth-child(1) { top: 6%; left: 66%; }
  .control-orbit i:nth-child(2) { right: 4%; bottom: 27%; }
  .control-orbit i:nth-child(3) { bottom: 4%; left: 28%; }

  .install {
    display: grid;
    grid-template-columns: minmax(19rem, 0.75fr) minmax(29rem, 1.25fr);
    align-items: end;
    gap: clamp(2.5rem, 8vw, 7rem);
  }

  .install-copy .kicker { margin: 0 0 1.2rem; }
  .install-copy h2 { font-size: clamp(2rem, 4.2vw, 3.7rem); }
  .install-copy > p:last-of-type { margin-top: 1.2rem; }

  .install-copy a {
    display: inline-flex;
    margin-top: 1.5rem;
    padding-bottom: 0.16rem;
    border-bottom: 1px solid var(--color-cyan);
    color: var(--color-fg);
    font-family: var(--font-mono);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  .install-copy a:hover { color: var(--color-cyan); box-shadow: 0 5px 12px -7px var(--color-cyan); }

  @media (max-width: 1040px) {
    .hero {
      min-height: auto;
      grid-template-columns: minmax(0, 1fr);
      padding-top: 5rem;
    }
    .hero-copy { max-width: 48rem; }
    h1 { max-width: 13ch; }
  }

  @media (max-width: 860px) {
    .install { grid-template-columns: minmax(0, 1fr); }
  }

  @media (max-width: 780px) {
    .section-intro,
    .principles-intro { grid-template-columns: minmax(0, 1fr); }
    .section-intro > p:last-child,
    .principles-intro > p:last-child { margin-top: 1.4rem; }
    .architecture-flow { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .architecture-flow li:nth-child(3) { border-top: 0; }
    .architecture-flow li:nth-child(4) { border-top: 0; border-right: 1px solid var(--color-border); }
    .principle-grid { grid-template-columns: minmax(0, 1fr); }
    .principle-featured { min-height: 27rem !important; grid-row: auto; }
  }

  @media (max-width: 520px) {
    .hero { gap: 3rem; padding-block: 3.75rem; }
    h1 { font-size: clamp(2.55rem, 13.2vw, 4rem); }
    .hero-actions { flex-direction: column; }
    .hero-actions a { width: 100%; }
    .signals { align-items: flex-start; flex-direction: column; }
    .architecture-flow { grid-template-columns: minmax(0, 1fr); }
    .architecture-flow li { min-height: 12rem; border-top: 0; border-right: 1px solid var(--color-border); }
    .architecture-flow li:first-child { border-top: 1px solid var(--color-border-strong); }
    .architecture-flow li > div { position: static; margin-top: 3rem; }
    .principle-featured { min-height: 25rem !important; }
    .principle-featured h3 { margin-top: 12rem; }
    .control-orbit { right: 1.5rem; }
    .install { grid-template-columns: minmax(0, 1fr); }
  }
</style>

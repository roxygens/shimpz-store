<script lang="ts">
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";

  let { lang }: { lang: Locale } = $props();
</script>

<figure class="topology" aria-labelledby="topology-label topology-title">
  <div class="topology-header">
    <span class="topology-index" id="topology-label">01 // {tr("topology_label", lang)}</span>
    <span class="status"><i aria-hidden="true"></i>{tr("topology_status", lang)}</span>
  </div>

  <div class="space-node">
    <img src="/brand/shimpz-cyberchimp.png" alt="" aria-hidden="true" width="1254" height="1254" />
    <div>
      <span class="node-type">{tr("topology_space", lang)}</span>
      <strong id="topology-title">Shimpz</strong>
    </div>
    <span class="control-plane">control_plane</span>
  </div>

  <section class="driver-rail" aria-labelledby="drivers-title">
    <div class="rail-title">
      <span id="drivers-title">{tr("topology_drivers", lang)}</span>
      <small>{tr("topology_shared", lang)}</small>
    </div>
    <ul aria-label={tr("topology_drivers", lang)}>
      <li>PostgreSQL</li>
    </ul>
  </section>

  <div class="connector" aria-hidden="true"><span></span></div>

  <ol class="teams" aria-label={lang === "pt" ? "Times isolados" : "Isolated Teams"}>
    <li>
      <div class="team-heading">
        <span>{tr("topology_team", lang)} // 01</span>
        <small>{tr("topology_boundary", lang)}</small>
      </div>
      <div class="apps">
        <span>Assistant 01</span>
        <span>Assistant 02</span>
        <span aria-hidden="true">+</span>
      </div>
      <p>{tr("topology_apps", lang)}</p>
    </li>
    <li>
      <div class="team-heading">
        <span>{tr("topology_team", lang)} // 02</span>
        <small>{tr("topology_boundary", lang)}</small>
      </div>
      <div class="apps">
        <span>Assistant 01</span>
        <span>Assistant 02</span>
        <span aria-hidden="true">+</span>
      </div>
      <p>{tr("topology_apps", lang)}</p>
    </li>
  </ol>

  <figcaption>{tr("topology_caption", lang)}</figcaption>
</figure>

<style>
  .topology {
    position: relative;
    margin: 0;
    padding: clamp(1rem, 2.3vw, 1.5rem);
    overflow: hidden;
    background:
      radial-gradient(circle at 86% 8%, rgba(0, 240, 255, 0.1), transparent 27%),
      linear-gradient(145deg, var(--color-card-2), var(--color-card) 68%);
    box-shadow:
      inset 0 0 0 1px var(--color-border-strong),
      var(--shadow-panel);
    clip-path: polygon(var(--cut-lg) 0, 100% 0, 100% calc(100% - var(--cut-lg)), calc(100% - var(--cut-lg)) 100%, 0 100%, 0 var(--cut-lg));
  }

  .topology::before {
    position: absolute;
    top: 0;
    right: 0;
    left: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--color-cyan), var(--color-magenta) 72%, transparent);
    content: "";
  }

  .topology-header,
  .space-node,
  .rail-title,
  .team-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .topology-index,
  .status,
  .node-type,
  .control-plane,
  .rail-title,
  .team-heading,
  .apps,
  figcaption {
    font-family: var(--font-mono);
  }

  .topology-index {
    color: var(--color-muted-2);
    font-size: 0.58rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  .status {
    color: var(--color-green);
    font-size: 0.58rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  .status i {
    width: 0.42rem;
    height: 0.42rem;
    flex: none;
    background: currentColor;
    border-radius: 50%;
    box-shadow: 0 0 9px rgba(5, 255, 161, 0.65);
  }

  .space-node {
    min-height: 7.2rem;
    margin-top: 1rem;
    padding: 0.85rem 1rem;
    background: rgba(0, 0, 0, 0.72);
    box-shadow: inset 0 0 0 1px var(--color-border);
    clip-path: polygon(var(--cut) 0, 100% 0, 100% calc(100% - var(--cut)), calc(100% - var(--cut)) 100%, 0 100%, 0 var(--cut));
  }

  .space-node img {
    width: clamp(4.5rem, 9vw, 6.2rem);
    height: clamp(4.5rem, 9vw, 6.2rem);
    flex: none;
    object-fit: contain;
    mix-blend-mode: screen;
  }

  .space-node > div {
    display: flex;
    min-width: 0;
    flex: 1;
    flex-direction: column;
  }

  .node-type {
    color: var(--color-cyan);
    font-size: 0.6rem;
    font-weight: 600;
    letter-spacing: 0.15em;
    text-transform: uppercase;
  }

  .space-node strong {
    font-family: var(--font-mono);
    font-size: clamp(1.65rem, 4.2vw, 2.4rem);
    line-height: 1.08;
    letter-spacing: -0.065em;
  }

  .control-plane {
    align-self: flex-end;
    color: var(--color-muted-2);
    font-size: 0.625rem;
    letter-spacing: 0.08em;
  }

  .driver-rail {
    position: relative;
    margin-top: 0.7rem;
    padding: 0.9rem;
    border: 1px solid color-mix(in oklab, var(--color-cyan) 30%, var(--color-border));
    background: color-mix(in oklab, var(--color-cyan) 4%, #000000);
  }

  .rail-title > span {
    color: var(--color-fg);
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.09em;
    text-transform: uppercase;
  }

  .rail-title small,
  .team-heading small {
    color: var(--color-muted-2);
    font-size: 0.625rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .driver-rail ul,
  .teams {
    padding: 0;
    list-style: none;
  }

  .driver-rail ul {
    display: grid;
    margin: 0.7rem 0 0;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.45rem;
  }

  .driver-rail li {
    min-width: 0;
    padding: 0.48rem 0.45rem;
    border-left: 2px solid var(--color-cyan);
    background: var(--color-card-2);
    color: var(--color-muted);
    font-family: var(--font-mono);
    font-size: 0.625rem;
    font-weight: 600;
    overflow-wrap: anywhere;
    text-align: center;
  }

  .connector {
    position: relative;
    width: 72%;
    height: 1.8rem;
    margin: 0 auto;
    border-right: 1px solid color-mix(in oklab, var(--color-cyan) 35%, var(--color-border));
    border-bottom: 1px solid color-mix(in oklab, var(--color-cyan) 35%, var(--color-border));
    border-left: 1px solid color-mix(in oklab, var(--color-cyan) 35%, var(--color-border));
  }

  .connector span {
    position: absolute;
    top: -1px;
    left: 50%;
    width: 1px;
    height: 100%;
    background: color-mix(in oklab, var(--color-cyan) 35%, var(--color-border));
  }

  .teams {
    display: grid;
    margin: 0;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.7rem;
  }

  .teams > li {
    position: relative;
    min-width: 0;
    padding: 0.85rem;
    border: 1px solid var(--color-border-strong);
    background: rgba(0, 0, 0, 0.8);
    clip-path: polygon(var(--cut-sm) 0, 100% 0, 100% calc(100% - var(--cut-sm)), calc(100% - var(--cut-sm)) 100%, 0 100%, 0 var(--cut-sm));
  }

  .team-heading > span {
    color: var(--color-magenta);
    font-size: 0.625rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .apps {
    display: grid;
    margin-top: 0.75rem;
    grid-template-columns: 1fr 1fr 1.7rem;
    gap: 0.35rem;
  }

  .apps span {
    display: grid;
    min-width: 0;
    min-height: 2.4rem;
    place-items: center;
    border: 1px solid var(--color-border);
    background: var(--color-card-2);
    color: var(--color-muted);
    font-size: 0.625rem;
    font-weight: 600;
    text-transform: uppercase;
  }

  .apps span:last-child { color: var(--color-cyan); }

  .teams p {
    margin: 0.55rem 0 0;
    color: var(--color-muted-2);
    font-size: 0.68rem;
  }

  figcaption {
    margin-top: 1rem;
    padding-top: 0.8rem;
    border-top: 1px solid var(--color-border);
    color: var(--color-muted-2);
    font-size: 0.625rem;
    letter-spacing: 0.02em;
  }

  @media (max-width: 560px) {
    .control-plane { display: none; }
    .driver-rail ul { grid-template-columns: 1fr; }
    .driver-rail li { text-align: left; }
    .connector { display: none; }
    .teams { margin-top: 0.7rem; grid-template-columns: 1fr; }
  }
</style>

<script lang="ts">
  import { onMount } from "svelte";
  import { ASSISTANT_CATALOG, t, type Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import {
    ASSISTANT_INSTALL_ACK_TIMEOUT_MS,
    classifyAssistantInstallAck,
    createAssistantInstallRequest,
    resolveInstallParentOrigin,
  } from "$lib/assistantInstallBridge.js";
  import HudIcon from "$lib/components/HudIcon.svelte";
  import InstallCommand from "$lib/components/InstallCommand.svelte";
  import PageIntro from "$lib/components/PageIntro.svelte";

  let { lang, embedded = false }: { lang: Locale; embedded?: boolean } = $props();
  let installState = $state<"idle" | "pending" | "sent" | "error">("idle");
  let pendingAssistant = $state("");
  let pendingParentOrigin = "";
  let ackTimeout: ReturnType<typeof setTimeout> | undefined;

  function finishInstallRequest(state: "sent" | "error") {
    if (ackTimeout) clearTimeout(ackTimeout);
    ackTimeout = undefined;
    installState = state;
    pendingAssistant = "";
    pendingParentOrigin = "";
  }

  function requestInstall(assistant: string) {
    if (installState === "pending") return;
    try {
      if (window.parent === window) throw new Error("not embedded");
      pendingParentOrigin = resolveInstallParentOrigin(document.referrer);
      pendingAssistant = assistant;
      installState = "pending";
      window.parent.postMessage(createAssistantInstallRequest(assistant), pendingParentOrigin);
      ackTimeout = setTimeout(() => finishInstallRequest("error"), ASSISTANT_INSTALL_ACK_TIMEOUT_MS);
    } catch {
      finishInstallRequest("error");
    }
  }

  function receiveInstallAck(event: MessageEvent) {
    if (!pendingAssistant || !pendingParentOrigin) return;
    const result = classifyAssistantInstallAck(event, {
      parentWindow: window.parent,
      parentOrigin: pendingParentOrigin,
      assistant: pendingAssistant,
    });
    if (result === "accepted") finishInstallRequest("sent");
    else if (result === "invalid") finishInstallRequest("error");
  }

  onMount(() => {
    window.addEventListener("message", receiveInstallAck);
    return () => {
      window.removeEventListener("message", receiveInstallAck);
      if (ackTimeout) clearTimeout(ackTimeout);
    };
  });

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

  <p class="preview-notice"><span aria-hidden="true">FREE // EVAL</span>{tr("assistants_preview_notice", lang)}</p>

  <section class="available" aria-labelledby="available-assistants-title">
    <header class="section-copy">
      <p class="kicker">{tr("assistants_available_kicker", lang)}</p>
      <h2 id="available-assistants-title">{tr("assistants_available_title", lang)}</h2>
      <p>{tr("assistants_available_lead", lang)}</p>
    </header>

    <div class="assistant-grid">
      {#each ASSISTANT_CATALOG as assistant (assistant.id)}
        <article class="assistant-card">
          <div class="assistant-mark" aria-hidden="true">
            <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 25h9l4-11 7 22 6-17 4 6h10" />
              <path d="M8 8h32v32H8z" opacity=".45" />
            </svg>
          </div>
          <div class="assistant-main">
            <div class="assistant-title">
              <div>
                <p class="kicker">@{assistant.creator}</p>
                <h3>{assistant.name}</h3>
              </div>
              <span class="free-badge">{tr("assistants_free", lang)}</span>
            </div>
            <p class="assistant-summary">{t(assistant.summary, lang)}</p>
            <p class="assistant-description">{t(assistant.description, lang)}</p>

            <dl class="assistant-facts">
              <div><dt>{tr("assistants_version", lang)}</dt><dd>{assistant.version}</dd></div>
              <div><dt>{tr("assistants_architectures", lang)}</dt><dd>{assistant.archs.join(" + ")}</dd></div>
              <div><dt>{tr("assistants_permissions", lang)}</dt><dd>{tr("assistants_no_permissions", lang)}</dd></div>
            </dl>

            <div class="operation">
              <span class="operation-icon" aria-hidden="true"><HudIcon name="retry" size={18} /></span>
              <div>
                <p class="kicker">{tr("assistants_operation", lang)} // {assistant.operations[0].id}</p>
                <strong>{t(assistant.operations[0].name, lang)}</strong>
                <small>{t(assistant.operations[0].summary, lang)}</small>
              </div>
            </div>

            {#if embedded}
              <button class="btn-primary install-action" type="button" disabled={installState === "pending"} onclick={() => requestInstall(assistant.id)}>
                <HudIcon name="add" size={18} />{tr(installState === "pending" ? "assistants_request_waiting" : "assistants_install_local", lang)}
              </button>
            {:else}
              <a class="btn-primary install-action" href="http://127.0.0.1:7777/assistants/" target="_blank" rel="noopener noreferrer">
                <HudIcon name="add" size={18} />{tr("assistants_install_local", lang)}
              </a>
            {/if}
            {#if installState === "sent" || installState === "error"}
              <p class:error={installState === "error"} class="install-status" role={installState === "error" ? "alert" : "status"}>
                {tr(installState === "sent" ? "assistants_request_sent" : "assistants_request_failed", lang)}
              </p>
            {/if}
          </div>
        </article>
      {/each}
    </div>

    {#if !embedded}
      <aside class="local-setup" aria-labelledby="local-setup-title">
        <div>
          <p class="kicker">LOCAL // 60 SECONDS</p>
          <h3 id="local-setup-title">{tr("assistants_local_setup", lang)}</h3>
          <p>{tr("assistants_local_setup_help", lang)}</p>
        </div>
        <InstallCommand {lang} />
      </aside>
    {/if}
  </section>

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
  .available { margin-top: clamp(3rem, 6vw, 5rem); }
  .model, .creator-panel, .future-grid { margin-top: clamp(4rem, 8vw, 7rem); }

  .assistant-grid { margin-top: 2rem; }
  .assistant-card {
    display: grid;
    grid-template-columns: 7.5rem minmax(0, 1fr);
    gap: clamp(1.2rem, 4vw, 2.5rem);
    padding: clamp(1.25rem, 4vw, 2.4rem);
    background:
      linear-gradient(120deg, color-mix(in oklab, var(--color-cyan) 8%, transparent), transparent 42%),
      var(--color-card);
    box-shadow: inset 3px 0 0 var(--color-cyan), inset 0 0 0 1px var(--color-border-strong);
    clip-path: polygon(var(--cut-lg) 0, 100% 0, 100% calc(100% - var(--cut-lg)), calc(100% - var(--cut-lg)) 100%, 0 100%, 0 var(--cut-lg));
  }
  .assistant-mark {
    display: grid;
    width: 7.5rem;
    height: 7.5rem;
    place-items: center;
    color: var(--color-cyan);
    background: #000;
    box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--color-cyan) 55%, var(--color-border));
    clip-path: polygon(18px 0, 100% 0, 100% calc(100% - 18px), calc(100% - 18px) 100%, 0 100%, 0 18px);
  }
  .assistant-mark svg { width: 4.4rem; filter: drop-shadow(0 0 9px rgba(0, 240, 255, 0.35)); }
  .assistant-main { min-width: 0; }
  .assistant-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
  .assistant-title .kicker { margin: 0 0 0.25rem; font-size: 0.58rem; }
  .assistant-title h3 { margin: 0; font-size: clamp(1.8rem, 4vw, 3rem); line-height: 1; }
  .free-badge {
    padding: 0.35rem 0.6rem;
    color: var(--color-green);
    background: color-mix(in oklab, var(--color-green) 7%, #000);
    box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--color-green) 45%, var(--color-border));
    font-family: var(--font-mono);
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .assistant-summary { max-width: 52rem; margin: 1.1rem 0 0; color: var(--color-fg); font-size: 1rem; font-weight: 600; }
  .assistant-description { max-width: 52rem; margin: 0.55rem 0 0; color: var(--color-muted); font-size: 0.86rem; line-height: 1.7; }
  .assistant-facts {
    display: grid;
    grid-template-columns: 0.55fr 0.8fr 1.65fr;
    margin: 1.3rem 0 0;
    border-block: 1px solid var(--color-border);
  }
  .assistant-facts div { min-width: 0; padding: 0.75rem 0.8rem; border-right: 1px solid var(--color-border); }
  .assistant-facts div:first-child { padding-left: 0; }
  .assistant-facts div:last-child { border-right: 0; }
  .assistant-facts dt { color: var(--color-muted-2); font-family: var(--font-mono); font-size: 0.56rem; letter-spacing: 0.08em; text-transform: uppercase; }
  .assistant-facts dd { margin: 0.25rem 0 0; color: var(--color-fg); font-size: 0.72rem; overflow-wrap: anywhere; }
  .operation {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 0.75rem;
    margin-top: 1rem;
    padding: 0.8rem;
    background: #000;
    box-shadow: inset 0 0 0 1px var(--color-border);
  }
  .operation-icon { display: grid; width: 2.5rem; height: 2.5rem; place-items: center; color: var(--color-yellow); background: var(--color-elevated); }
  .operation .kicker { margin: 0; color: var(--color-yellow); font-size: 0.52rem; }
  .operation strong { display: block; margin-top: 0.15rem; font-family: var(--font-mono); font-size: 0.8rem; }
  .operation small { display: block; margin-top: 0.15rem; color: var(--color-muted); font-size: 0.7rem; }
  .install-action { width: fit-content; margin-top: 1rem; border: 0; cursor: pointer; }
  .install-status { margin: 0.65rem 0 0; color: var(--color-green); font-size: 0.74rem; }
  .install-status.error { color: var(--color-danger); }
  .local-setup {
    display: grid;
    grid-template-columns: minmax(15rem, 0.7fr) minmax(22rem, 1.3fr);
    align-items: center;
    gap: clamp(1.5rem, 5vw, 4rem);
    margin-top: 1rem;
    padding: clamp(1.2rem, 3vw, 2rem);
    background: var(--color-card);
    box-shadow: inset 0 0 0 1px var(--color-border);
  }
  .local-setup .kicker { margin: 0 0 0.35rem; }
  .local-setup h3 { margin: 0; font-size: 1.2rem; }
  .local-setup p:last-child { margin: 0.45rem 0 0; color: var(--color-muted); font-size: 0.8rem; line-height: 1.6; }

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
    .section-copy, .creator-panel, .future-grid, .local-setup { grid-template-columns: 1fr; }
    .section-copy > p:last-child { margin-top: 1rem; }
    .assistant-card { grid-template-columns: 1fr; }
    .assistant-mark { width: 5rem; height: 5rem; }
    .assistant-mark svg { width: 3rem; }
  }
  @media (max-width: 520px) {
    .principle-grid { grid-template-columns: 1fr; }
    .principle-grid article { min-height: auto; }
    .principle-grid h3 { margin-top: 2rem; }
    .example ul { align-items: stretch; flex-direction: column; }
    .example li { overflow-wrap: anywhere; }
    .assistant-title { align-items: flex-start; flex-direction: column; }
    .assistant-facts { grid-template-columns: 1fr; }
    .assistant-facts div, .assistant-facts div:first-child { border-right: 0; border-bottom: 1px solid var(--color-border); padding: 0.65rem 0; }
    .assistant-facts div:last-child { border-bottom: 0; }
    .install-action { width: 100%; }
  }
</style>

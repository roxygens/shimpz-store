<script lang="ts">
  import { onMount } from "svelte";
  import { ASSISTANT_CATALOG, t, type Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import {
    ASSISTANT_INSTALL_ACK_TIMEOUT_MS,
    acceptAssistantStoreContext,
    acceptAssistantStoreState,
    assistantStoreActionForState,
    classifyAssistantInstallAck,
    classifyAssistantUninstallAck,
    createAssistantStoreFrameMessage,
    createAssistantInstallRequest,
    createAssistantUninstallRequest,
    resolveInstallParentOrigin,
    shouldReconcileAssistantStoreAction,
  } from "$lib/assistantInstallBridge.js";
  import AssistantIcon from "$lib/components/AssistantIcon.svelte";
  import HudIcon from "$lib/components/HudIcon.svelte";
  import InstallCommand from "$lib/components/InstallCommand.svelte";
  import PageIntro from "$lib/components/PageIntro.svelte";

  type ActionKind = "install" | "uninstall";
  type ActionState = "idle" | "pending" | "sent" | "error";
  type ContextState = "connecting" | "ready" | "error";
  type InventoryState = "legacy" | "loading" | "ready" | "error";
  type PendingAction = {
    action: ActionKind;
    parentOrigin: string;
    timeout: ReturnType<typeof setTimeout>;
  };

  let { lang, embedded = false }: { lang: Locale; embedded?: boolean } = $props();
  let actionStates = $state<Record<string, ActionState>>({});
  let actionKinds = $state<Record<string, ActionKind>>({});
  let contextState = $state<ContextState>("connecting");
  let inventoryState = $state<InventoryState>("legacy");
  let installedAssistantIds = $state<string[]>([]);
  let parentOrigin = $state("");
  let storeElement = $state<HTMLElement>();
  const pendingActions = new Map<string, PendingAction>();
  let contextTimeout: ReturnType<typeof setTimeout> | undefined;
  let frameRequest = 0;

  function actionState(assistant: string): ActionState {
    return actionStates[assistant] ?? "idle";
  }

  function setActionState(assistant: string, action: ActionKind, state: ActionState) {
    actionKinds = { ...actionKinds, [assistant]: action };
    actionStates = { ...actionStates, [assistant]: state };
  }

  function finishActionRequest(assistant: string, state: "sent" | "error") {
    const pending = pendingActions.get(assistant);
    if (pending) clearTimeout(pending.timeout);
    pendingActions.delete(assistant);
    if (pending) setActionState(assistant, pending.action, state);
  }

  function assistantInstalled(assistant: string): boolean {
    return assistantStoreActionForState(inventoryState, installedAssistantIds, assistant) === "uninstall";
  }

  function inventoryBlocksAction(assistant: string): boolean {
    return assistantStoreActionForState(inventoryState, installedAssistantIds, assistant) === "blocked";
  }

  function requestAssistantAction(assistant: string) {
    if (pendingActions.has(assistant)) return;
    const resolvedAction = assistantStoreActionForState(inventoryState, installedAssistantIds, assistant);
    if (resolvedAction === "blocked") return;
    const action: ActionKind = resolvedAction;
    try {
      if (window.parent === window) throw new Error("not embedded");
      if (!parentOrigin) throw new Error("local Admin context unavailable");
      const request = action === "uninstall"
        ? createAssistantUninstallRequest(assistant)
        : createAssistantInstallRequest(assistant);
      setActionState(assistant, action, "pending");
      window.parent.postMessage(request, parentOrigin);
      const timeout = setTimeout(
        () => finishActionRequest(assistant, "error"),
        ASSISTANT_INSTALL_ACK_TIMEOUT_MS,
      );
      pendingActions.set(assistant, { action, parentOrigin, timeout });
    } catch {
      setActionState(assistant, action, "error");
    }
  }

  function reconcileAuthoritativeState(installed: string[]) {
    const nextStates = { ...actionStates };
    const nextKinds = { ...actionKinds };
    for (const [assistant, action] of Object.entries(actionKinds)) {
      if (!shouldReconcileAssistantStoreAction(action, actionState(assistant), "ready", installed, assistant)) {
        continue;
      }
      const pending = pendingActions.get(assistant);
      if (pending) clearTimeout(pending.timeout);
      pendingActions.delete(assistant);
      delete nextStates[assistant];
      delete nextKinds[assistant];
    }
    actionStates = nextStates;
    actionKinds = nextKinds;
  }

  function actionLabel(assistant: string): string {
    if (actionState(assistant) === "pending") return tr("assistants_request_waiting", lang);
    if (contextState !== "ready") return tr("assistants_admin_connecting", lang);
    if (inventoryState === "loading") return tr("assistants_inventory_loading", lang);
    if (inventoryState === "error") return tr("assistants_inventory_unavailable", lang);
    return tr(assistantInstalled(assistant) ? "assistants_uninstall_local" : "assistants_install_local", lang);
  }

  function actionStatus(assistant: string): string {
    const uninstall = actionKinds[assistant] === "uninstall";
    const failed = actionState(assistant) === "error";
    if (uninstall) {
      return tr(failed ? "assistants_uninstall_request_failed" : "assistants_uninstall_request_sent", lang);
    }
    return tr(failed ? "assistants_request_failed" : "assistants_request_sent", lang);
  }

  function measureFrameHeight(): number {
    const contentBottom = storeElement
      ? storeElement.getBoundingClientRect().bottom + window.scrollY + 32
      : 0;
    return contentBottom;
  }

  function emitFrameMeasurement() {
    if (!embedded || window.parent === window) return;
    window.parent.postMessage(createAssistantStoreFrameMessage(measureFrameHeight()), "*");
  }

  function scheduleFrameMeasurement() {
    if (frameRequest) cancelAnimationFrame(frameRequest);
    frameRequest = requestAnimationFrame(() => {
      frameRequest = 0;
      emitFrameMeasurement();
    });
  }

  function requestAdminContext() {
    if (!embedded || window.parent === window) return;
    if (!parentOrigin) contextState = "connecting";
    emitFrameMeasurement();
    if (parentOrigin) return;
    if (contextTimeout) clearTimeout(contextTimeout);
    contextTimeout = setTimeout(() => {
      if (!parentOrigin) contextState = "error";
    }, ASSISTANT_INSTALL_ACK_TIMEOUT_MS);
  }

  function receiveStoreMessage(event: MessageEvent) {
    const contextOrigin = acceptAssistantStoreContext(event, window.parent);
    if (contextOrigin) {
      parentOrigin = contextOrigin;
      contextState = "ready";
      if (contextTimeout) clearTimeout(contextTimeout);
      contextTimeout = undefined;
      return;
    }

    const storeState = parentOrigin
      ? acceptAssistantStoreState(event, window.parent, parentOrigin)
      : null;
    if (storeState) {
      inventoryState = storeState.status;
      installedAssistantIds = storeState.installed;
      if (storeState.status === "ready") reconcileAuthoritativeState(storeState.installed);
      return;
    }

    const assistant =
      event.data && typeof event.data === "object" && typeof event.data.assistant === "string"
        ? event.data.assistant
        : "";
    const pending = pendingActions.get(assistant);
    if (!pending) return;
    const classifyAck = pending.action === "uninstall"
      ? classifyAssistantUninstallAck
      : classifyAssistantInstallAck;
    const result = classifyAck(event, {
      parentWindow: window.parent,
      parentOrigin: pending.parentOrigin,
      assistant,
    });
    if (result === "accepted") finishActionRequest(assistant, "sent");
    else if (result === "invalid") finishActionRequest(assistant, "error");
  }

  onMount(() => {
    window.addEventListener("message", receiveStoreMessage);
    let mounted = true;
    let resizeObserver: ResizeObserver | undefined;
    if (embedded) {
      // Rolling-deployment compatibility only: new Admin images establish the preferred explicit
      // context handshake; old images still provide a strictly validated loopback referrer.
      try {
        parentOrigin = resolveInstallParentOrigin(document.referrer);
        contextState = "ready";
      } catch {
        contextState = "connecting";
      }

      if (typeof ResizeObserver !== "undefined") {
        resizeObserver = new ResizeObserver(scheduleFrameMeasurement);
        if (storeElement) resizeObserver.observe(storeElement);
      }
      requestAdminContext();
      scheduleFrameMeasurement();
      void document.fonts?.ready.then(() => {
        if (mounted) scheduleFrameMeasurement();
      });
    }
    return () => {
      mounted = false;
      window.removeEventListener("message", receiveStoreMessage);
      resizeObserver?.disconnect();
      if (frameRequest) cancelAnimationFrame(frameRequest);
      if (contextTimeout) clearTimeout(contextTimeout);
      for (const pending of pendingActions.values()) clearTimeout(pending.timeout);
      pendingActions.clear();
    };
  });
</script>

<section
  bind:this={storeElement}
  class:embedded
  class="wrap assistants-page"
  aria-label={embedded ? tr("assistants_title", lang) : undefined}
  aria-labelledby={embedded ? undefined : "assistants-title"}>
  {#if !embedded}
    <PageIntro
      headingId="assistants-title"
      kicker={tr("assistants_preview", lang)}
      title={tr("assistants_title", lang)}
      description={tr("assistants_lead", lang)} />
  {/if}

  {#if embedded && contextState === "error"}
    <div class="context-error" role="alert">
      <span>{tr("assistants_admin_connection_failed", lang)}</span>
      <button type="button" onclick={requestAdminContext}>
        {tr("assistants_admin_connection_retry", lang)}
      </button>
    </div>
  {/if}

  <div class="assistant-grid">
    {#each ASSISTANT_CATALOG as assistant (assistant.id)}
      <article class:installed={embedded && assistantInstalled(assistant.id)} class="assistant-card">
        <a
          class="assistant-details"
          href={u.assistant(lang, assistant)}
          target={embedded ? "_blank" : undefined}
          rel={embedded ? "noopener noreferrer" : undefined}
          aria-label={`${assistant.name} — ${tr("assistants_view_details", lang)}`}>
          <div class="assistant-heading">
            <AssistantIcon size={64} />
            <div class="assistant-identity">
              <h2>{assistant.name}</h2>
              <p>@{assistant.creator}</p>
            </div>
            {#if embedded && assistantInstalled(assistant.id)}
              <span class="installed-badge"><HudIcon name="check" size={13} />{tr("assistants_installed_local", lang)}</span>
            {:else}
              <span class="free-badge">{tr("assistants_free", lang)}</span>
            {/if}
          </div>
          <p class="assistant-summary">{t(assistant.summary, lang)}</p>
          <span class="details-label">{tr("assistants_view_details", lang)} <b aria-hidden="true">→</b></span>
        </a>

        <div class="assistant-action">
          {#if embedded}
            <button
              class:btn-primary={!assistantInstalled(assistant.id)}
              class:btn-danger={assistantInstalled(assistant.id)}
              class="install-action"
              type="button"
              disabled={contextState !== "ready" || inventoryBlocksAction(assistant.id) || actionState(assistant.id) === "pending"}
              onclick={() => requestAssistantAction(assistant.id)}>
              <HudIcon name={assistantInstalled(assistant.id) ? "uninstall" : "add"} size={17} />
              {actionLabel(assistant.id)}
            </button>
          {:else}
            <a
              class="btn-primary install-action"
              href="http://127.0.0.1:7777/assistants/"
              target="_blank"
              rel="noopener noreferrer">
              <HudIcon name="add" size={17} />{tr("assistants_install_local", lang)}
            </a>
          {/if}

          {#if actionState(assistant.id) === "sent" || actionState(assistant.id) === "error"}
            <p
              class:error={actionState(assistant.id) === "error"}
              class="install-status"
              role={actionState(assistant.id) === "error" ? "alert" : "status"}>
              {actionStatus(assistant.id)}
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
        <h2 id="local-setup-title">{tr("assistants_local_setup", lang)}</h2>
        <p>{tr("assistants_local_setup_help", lang)}</p>
      </div>
      <InstallCommand {lang} />
    </aside>
  {/if}
</section>

<style>
  .assistants-page { padding-top: 2.5rem; }
  .assistants-page.embedded { padding-top: 0; }
  .assistants-page.embedded .assistant-grid { margin-top: 0; }

  .assistant-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 19rem), 23rem));
    gap: 1rem;
    margin-top: 1.25rem;
  }
  .assistant-card {
    display: flex;
    min-height: 17.5rem;
    overflow: hidden;
    flex-direction: column;
    background: linear-gradient(180deg, var(--color-card-2), var(--color-card));
    box-shadow: inset 0 0 0 1px var(--color-border);
    clip-path: polygon(var(--cut) 0, 100% 0, 100% calc(100% - var(--cut)), calc(100% - var(--cut)) 100%, 0 100%, 0 var(--cut));
    transition: box-shadow 0.18s ease, transform 0.18s var(--ease-shimpz);
  }
  .assistant-card:hover, .assistant-card:focus-within {
    box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--color-cyan) 52%, var(--color-border));
    transform: translateY(-2px);
  }
  .assistant-card.installed {
    box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--color-green) 52%, var(--color-border));
  }
  .assistant-card.installed:hover, .assistant-card.installed:focus-within {
    box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--color-green) 75%, var(--color-border));
  }
  .assistant-details { display: flex; min-width: 0; flex: 1; flex-direction: column; padding: 1rem; }
  .assistant-heading { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 0.8rem; }
  .assistant-identity { min-width: 0; }
  .assistant-identity h2 { overflow: hidden; margin: 0; font-size: 1.05rem; line-height: 1.2; text-overflow: ellipsis; white-space: nowrap; }
  .assistant-identity p { overflow: hidden; margin: 0.25rem 0 0; color: var(--color-muted-2); font-family: var(--font-mono); font-size: 0.62rem; text-overflow: ellipsis; white-space: nowrap; }
  .free-badge {
    align-self: start;
    border: 1px solid color-mix(in oklab, var(--color-green) 38%, var(--color-border));
    padding: 0.22rem 0.4rem;
    color: var(--color-green);
    font-family: var(--font-mono);
    font-size: 0.54rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }
  .installed-badge {
    display: inline-flex;
    align-items: center;
    align-self: start;
    gap: 0.25rem;
    border: 1px solid color-mix(in oklab, var(--color-green) 58%, var(--color-border));
    padding: 0.22rem 0.4rem;
    background: color-mix(in oklab, var(--color-green) 7%, #000);
    color: var(--color-green);
    font-family: var(--font-mono);
    font-size: 0.54rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }
  .assistant-summary {
    display: -webkit-box;
    margin: 1rem 0 0;
    overflow: hidden;
    color: var(--color-muted);
    font-size: 0.84rem;
    line-height: 1.55;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
  }
  .details-label { margin-top: auto; padding-top: 1.1rem; color: var(--color-cyan); font-family: var(--font-mono); font-size: 0.62rem; font-weight: 600; text-transform: uppercase; }
  .details-label b { color: var(--color-magenta); }
  .assistant-action { border-top: 1px solid var(--color-border); padding: 0.75rem 1rem 1rem; }
  .install-action { width: 100%; min-height: 2.5rem; border: 0; padding: 0.6rem 0.75rem; cursor: pointer; font-size: 0.62rem; }
  .install-status { margin: 0.55rem 0 0; color: var(--color-green); font-size: 0.68rem; line-height: 1.45; }
  .install-status.error { color: var(--color-danger); }
  .context-error {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    margin-top: 1rem;
    border-left: 2px solid var(--color-danger);
    padding: 0.65rem 0.75rem;
    background: color-mix(in oklab, var(--color-danger) 5%, #000);
    color: var(--color-danger);
    font-size: 0.68rem;
    line-height: 1.45;
  }
  .context-error button {
    min-height: 2rem;
    border: 1px solid color-mix(in oklab, var(--color-danger) 55%, var(--color-border));
    padding: 0 0.65rem;
    background: #000;
    color: var(--color-danger);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 0.58rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .local-setup {
    display: grid;
    grid-template-columns: minmax(15rem, 0.7fr) minmax(22rem, 1.3fr);
    align-items: center;
    gap: clamp(1.5rem, 5vw, 4rem);
    margin-top: 2rem;
    padding: clamp(1.2rem, 3vw, 2rem);
    background: var(--color-card);
    box-shadow: inset 0 0 0 1px var(--color-border);
  }
  .local-setup .kicker { margin: 0 0 0.35rem; }
  .local-setup h2 { margin: 0; font-size: 1.2rem; }
  .local-setup p:last-child { margin: 0.45rem 0 0; color: var(--color-muted); font-size: 0.8rem; line-height: 1.6; }

  @media (max-width: 720px) {
    .assistant-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .local-setup { grid-template-columns: 1fr; }
  }
  @media (max-width: 540px) {
    .assistant-grid { grid-template-columns: 1fr; }
    .assistant-card { min-height: 16.5rem; }
    .context-error { align-items: stretch; flex-direction: column; }
  }
  @media (prefers-reduced-motion: reduce) {
    .assistant-card { transition: none; }
    .assistant-card:hover, .assistant-card:focus-within { transform: none; }
  }
</style>

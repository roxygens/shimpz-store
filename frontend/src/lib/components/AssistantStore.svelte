<script lang="ts">
  import { goto } from "$app/navigation";
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
  import {
    assistantStoreMode,
    closedAssistantCapsuleHref,
    closedAssistantLoginHref,
    cloudAssistantAction,
    cloudRequestIsCurrent,
    cloudStoreCanStart,
    parseCloudAccount,
    parseCloudAssistantInventory,
    parseCloudCapsules,
    requestedAssistantFromSearch,
    selectCloudCapsule,
  } from "$lib/cloudAssistantLifecycle.js";
  import AssistantIcon from "$lib/components/AssistantIcon.svelte";
  import HudIcon from "$lib/components/HudIcon.svelte";
  import InstallCommand from "$lib/components/InstallCommand.svelte";
  import PageIntro from "$lib/components/PageIntro.svelte";

  type ActionKind = "install" | "uninstall";
  type ActionState = "idle" | "pending" | "sent" | "error";
  type ContextState = "connecting" | "ready" | "error";
  type InventoryState = "legacy" | "loading" | "ready" | "error";
  type CloudPhase = "checking" | "unauthenticated" | "empty" | "ready" | "error";
  type CloudInventoryState = "idle" | "loading" | "ready" | "error";
  type CloudCapsule = { id: string; name: string };
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
  let cloudPhase = $state<CloudPhase>("checking");
  let cloudInventoryState = $state<CloudInventoryState>("idle");
  let cloudCapsules = $state<CloudCapsule[]>([]);
  let cloudSelectedCapsule = $state("");
  let cloudInstalledAssistantIds = $state<string[]>([]);
  let cloudActionLatch = $state(false);
  let cloudPendingAction = $state<ActionKind | "">("");
  let cloudFeedback = $state<"" | "success" | "error">("");
  let cloudGeneration = 0;
  let requestedAssistant = $state("");
  const cloudTargetCapsule = $derived(
    cloudCapsules.find((capsule) => capsule.id === cloudSelectedCapsule),
  );

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

  function localAssistantInstalled(assistant: string): boolean {
    return assistantStoreActionForState(inventoryState, installedAssistantIds, assistant) === "uninstall";
  }

  function cloudAssistantInstalled(assistant: string): boolean {
    return cloudAssistantAction(
      cloudInventoryState === "ready",
      cloudInstalledAssistantIds,
      assistant,
    ) === "uninstall";
  }

  function renderedAssistantInstalled(assistant: string): boolean {
    return embedded ? localAssistantInstalled(assistant) : cloudAssistantInstalled(assistant);
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
    return tr(localAssistantInstalled(assistant) ? "assistants_uninstall_local" : "assistants_install_local", lang);
  }

  function actionStatus(assistant: string): string {
    const uninstall = actionKinds[assistant] === "uninstall";
    const failed = actionState(assistant) === "error";
    if (uninstall) {
      return tr(failed ? "assistants_uninstall_request_failed" : "assistants_uninstall_request_sent", lang);
    }
    return tr(failed ? "assistants_request_failed" : "assistants_request_sent", lang);
  }

  function clearCloudSession() {
    cloudGeneration += 1;
    cloudPhase = "unauthenticated";
    cloudInventoryState = "idle";
    cloudCapsules = [];
    cloudSelectedCapsule = "";
    cloudInstalledAssistantIds = [];
    cloudFeedback = "";
    localStorage.removeItem("shimpz_current_capsule");
    localStorage.removeItem("shimpz_current_capsule_name");
  }

  async function loadCloudInventory(capsule: string, generation: number): Promise<string[] | null> {
    if (!cloudRequestIsCurrent(generation, cloudGeneration, capsule, cloudSelectedCapsule)) return null;
    cloudInventoryState = "loading";
    cloudInstalledAssistantIds = [];
    try {
      const response = await fetch(`/api/capsules/${encodeURIComponent(capsule)}/assistants`, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!cloudRequestIsCurrent(generation, cloudGeneration, capsule, cloudSelectedCapsule)) return null;
      if (response.status === 401) {
        clearCloudSession();
        return null;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const installed = parseCloudAssistantInventory(await response.json());
      if (!cloudRequestIsCurrent(generation, cloudGeneration, capsule, cloudSelectedCapsule)) return null;
      cloudInstalledAssistantIds = installed;
      cloudInventoryState = "ready";
      return installed;
    } catch {
      if (cloudRequestIsCurrent(generation, cloudGeneration, capsule, cloudSelectedCapsule)) {
        cloudInstalledAssistantIds = [];
        cloudInventoryState = "error";
      }
      return null;
    }
  }

  async function bootCloudStore() {
    if (!cloudStoreCanStart("cloud", window.top === window.self)) {
      cloudPhase = "error";
      return;
    }
    const generation = ++cloudGeneration;
    cloudPhase = "checking";
    cloudInventoryState = "idle";
    cloudCapsules = [];
    cloudSelectedCapsule = "";
    cloudInstalledAssistantIds = [];
    cloudFeedback = "";
    try {
      const meResponse = await fetch("/api/me", {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (generation !== cloudGeneration) return;
      if (meResponse.status === 401) {
        clearCloudSession();
        return;
      }
      if (!meResponse.ok) throw new Error(`HTTP ${meResponse.status}`);
      const account = parseCloudAccount(await meResponse.json());
      if (!account.authenticated) {
        clearCloudSession();
        return;
      }

      const capsuleResponse = await fetch("/api/capsules", {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (generation !== cloudGeneration) return;
      if (capsuleResponse.status === 401) {
        clearCloudSession();
        return;
      }
      if (!capsuleResponse.ok) throw new Error(`HTTP ${capsuleResponse.status}`);
      const capsules = parseCloudCapsules(await capsuleResponse.json());
      if (generation !== cloudGeneration) return;
      cloudCapsules = capsules;
      if (capsules.length === 0) {
        cloudPhase = "empty";
        return;
      }
      cloudPhase = "ready";
      const remembered = selectCloudCapsule(
        capsules,
        localStorage.getItem("shimpz_current_capsule") ?? "",
      );
      if (!remembered) return;
      cloudSelectedCapsule = remembered;
      const capsule = capsules.find((candidate) => candidate.id === remembered);
      localStorage.setItem("shimpz_current_capsule_name", capsule?.name ?? remembered);
      await loadCloudInventory(remembered, generation);
    } catch {
      if (generation === cloudGeneration) cloudPhase = "error";
    }
  }

  async function chooseCloudCapsule(event: Event) {
    if (cloudActionLatch) return;
    const candidate = (event.currentTarget as HTMLSelectElement).value;
    const selected = selectCloudCapsule(cloudCapsules, candidate);
    cloudSelectedCapsule = selected;
    cloudInventoryState = "idle";
    cloudInstalledAssistantIds = [];
    cloudFeedback = "";
    const generation = ++cloudGeneration;
    if (!selected) {
      localStorage.removeItem("shimpz_current_capsule");
      localStorage.removeItem("shimpz_current_capsule_name");
      return;
    }
    const capsule = cloudCapsules.find((value) => value.id === selected);
    localStorage.setItem("shimpz_current_capsule", selected);
    localStorage.setItem("shimpz_current_capsule_name", capsule?.name ?? selected);
    await loadCloudInventory(selected, generation);
  }

  async function retryCloudInventory() {
    if (!cloudSelectedCapsule || cloudActionLatch) return;
    cloudFeedback = "";
    const generation = ++cloudGeneration;
    await loadCloudInventory(cloudSelectedCapsule, generation);
  }

  async function mutateCloudAssistant(assistant: string) {
    if (
      !cloudStoreCanStart("cloud", window.top === window.self) ||
      cloudActionLatch ||
      !cloudSelectedCapsule ||
      cloudInventoryState !== "ready"
    ) return;
    const action = cloudAssistantAction(true, cloudInstalledAssistantIds, assistant);
    if (action === "blocked") return;
    const capsule = cloudSelectedCapsule;
    const capsuleName = cloudTargetCapsule?.name ?? capsule;
    if (
      action === "uninstall" &&
      !window.confirm(
        lang === "pt"
          ? `Desinstalar ${assistant} da Cápsula ${capsuleName}?`
          : `Uninstall ${assistant} from Capsule ${capsuleName}?`,
      )
    ) {
      return;
    }

    cloudActionLatch = true;
    cloudPendingAction = action;
    cloudFeedback = "";
    const generation = cloudGeneration;
    try {
      const base = `/api/capsules/${encodeURIComponent(capsule)}/assistants`;
      const response = action === "install"
        ? await fetch(base, {
            method: "POST",
            headers: { Accept: "application/json", "Content-Type": "application/json" },
            body: JSON.stringify({ assistant }),
          })
        : await fetch(`${base}/${encodeURIComponent(assistant)}`, {
            method: "DELETE",
            headers: { Accept: "application/json" },
          });
      if (!cloudRequestIsCurrent(generation, cloudGeneration, capsule, cloudSelectedCapsule)) return;
      if (response.status === 401) {
        clearCloudSession();
        return;
      }
    } catch {
      // The authoritative refresh below decides what actually committed.
    } finally {
      if (cloudRequestIsCurrent(generation, cloudGeneration, capsule, cloudSelectedCapsule)) {
        const installed = await loadCloudInventory(capsule, generation);
        if (installed && cloudRequestIsCurrent(generation, cloudGeneration, capsule, cloudSelectedCapsule)) {
          const nextAction = cloudAssistantAction(true, installed, assistant);
          const committed = action === "install" ? nextAction === "uninstall" : nextAction === "install";
          cloudFeedback = committed ? "success" : "error";
        }
      }
      cloudActionLatch = false;
      cloudPendingAction = "";
    }
  }

  function cloudButtonLabel(assistant: string): string {
    if (cloudActionLatch) {
      return tr(cloudPendingAction === "uninstall" ? "assistants_cloud_uninstalling" : "assistants_cloud_installing", lang);
    }
    if (cloudPhase === "checking") return tr("assistants_cloud_loading", lang);
    if (cloudPhase === "unauthenticated") return tr("assistants_cloud_sign_in", lang);
    if (cloudPhase === "empty") return tr("assistants_cloud_create_capsule", lang);
    if (cloudPhase === "error") return tr("assistants_cloud_retry", lang);
    if (!cloudSelectedCapsule) return tr("assistants_cloud_choose", lang);
    if (cloudInventoryState === "loading" || cloudInventoryState === "idle") {
      return tr("assistants_inventory_loading", lang);
    }
    if (cloudInventoryState === "error") return tr("assistants_cloud_retry_inventory", lang);
    return tr(cloudAssistantInstalled(assistant) ? "assistants_cloud_uninstall" : "assistants_cloud_install", lang);
  }

  function cloudButtonDisabled(): boolean {
    return cloudPhase === "checking" ||
      cloudActionLatch ||
      (cloudPhase === "ready" && (
        !cloudSelectedCapsule || cloudInventoryState === "loading" || cloudInventoryState === "idle"
      ));
  }

  async function cloudPrimaryAction(assistant: string) {
    if (cloudPhase === "unauthenticated") {
      await goto(closedAssistantLoginHref(lang, assistant));
      return;
    }
    if (cloudPhase === "empty") {
      await goto(closedAssistantCapsuleHref(lang, assistant));
      return;
    }
    if (cloudPhase === "error") {
      await bootCloudStore();
      return;
    }
    if (cloudInventoryState === "error") {
      await retryCloudInventory();
      return;
    }
    await mutateCloudAssistant(assistant);
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
    const mode = assistantStoreMode(embedded);
    if (mode === "cloud") {
      if (!cloudStoreCanStart(mode, window.top === window.self)) {
        cloudPhase = "error";
        return;
      }
      requestedAssistant = requestedAssistantFromSearch(window.location.search);
      void bootCloudStore();
      return () => {
        cloudGeneration += 1;
      };
    }

    window.addEventListener("message", receiveStoreMessage);
    let mounted = true;
    let resizeObserver: ResizeObserver | undefined;
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
  class:wrap={!embedded}
  class="assistants-page"
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

  {#if !embedded}
    <section class="cloud-context" aria-labelledby="cloud-context-title">
      <div class="cloud-context-copy">
        <p class="kicker">CLOUD // OFFICIAL SPACE</p>
        <h2 id="cloud-context-title">{tr("assistants_cloud_target_title", lang)}</h2>
        {#if cloudPhase === "checking"}
          <p>{tr("assistants_cloud_loading", lang)}</p>
        {:else if cloudPhase === "unauthenticated"}
          <p>{tr("assistants_cloud_sign_in_help", lang)}</p>
        {:else if cloudPhase === "empty"}
          <p>{tr("assistants_cloud_no_capsules", lang)}</p>
        {:else if cloudPhase === "error"}
          <p class="cloud-error" role="alert">{tr("assistants_cloud_load_failed", lang)}</p>
        {:else}
          <p>{tr("assistants_cloud_target_help", lang)}</p>
        {/if}
      </div>
      {#if cloudPhase === "ready"}
        <label class="cloud-selector">
          <span>{tr("assistants_cloud_target_label", lang)}</span>
          <select
            value={cloudSelectedCapsule}
            disabled={cloudActionLatch}
            onchange={chooseCloudCapsule}>
            <option value="">{tr("assistants_cloud_choose", lang)}</option>
            {#each cloudCapsules as capsule (capsule.id)}
              <option value={capsule.id}>{capsule.name}</option>
            {/each}
          </select>
        </label>
      {/if}
      {#if cloudTargetCapsule}
        <p class="cloud-target-name">
          <HudIcon name="capsule" size={17} />
          <span>{tr("assistants_cloud_selected", lang)}</span>
          <strong>{cloudTargetCapsule.name}</strong>
        </p>
      {/if}
    </section>
  {/if}

  <div class="assistant-grid">
    {#each ASSISTANT_CATALOG as assistant (assistant.id)}
      <article
        id={`assistant-${assistant.id}`}
        class:installed={renderedAssistantInstalled(assistant.id)}
        class:requested={!embedded && requestedAssistant === assistant.id}
        class="assistant-card">
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
            {#if renderedAssistantInstalled(assistant.id)}
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
              class:btn-primary={!localAssistantInstalled(assistant.id)}
              class:btn-danger={localAssistantInstalled(assistant.id)}
              class="install-action"
              type="button"
              disabled={contextState !== "ready" || inventoryBlocksAction(assistant.id) || actionState(assistant.id) === "pending"}
              onclick={() => requestAssistantAction(assistant.id)}>
              <HudIcon name={localAssistantInstalled(assistant.id) ? "uninstall" : "add"} size={17} />
              {actionLabel(assistant.id)}
            </button>
          {:else}
            <button
              class:btn-primary={!cloudAssistantInstalled(assistant.id)}
              class:btn-danger={cloudAssistantInstalled(assistant.id)}
              class="install-action"
              type="button"
              disabled={cloudButtonDisabled()}
              onclick={() => cloudPrimaryAction(assistant.id)}>
              <HudIcon name={cloudAssistantInstalled(assistant.id) ? "uninstall" : "add"} size={17} />
              {cloudButtonLabel(assistant.id)}
            </button>
          {/if}

          {#if actionState(assistant.id) === "sent" || actionState(assistant.id) === "error"}
            <p
              class:error={actionState(assistant.id) === "error"}
              class="install-status"
              role={actionState(assistant.id) === "error" ? "alert" : "status"}>
              {actionStatus(assistant.id)}
            </p>
          {/if}

          {#if !embedded && cloudFeedback}
            <p
              class:error={cloudFeedback === "error"}
              class="install-status"
              role={cloudFeedback === "error" ? "alert" : "status"}>
              {tr(cloudFeedback === "success" ? "assistants_cloud_committed" : "assistants_cloud_failed", lang)}
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
  .assistants-page.embedded { width: 100%; padding-top: 2px; }
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
  .assistant-card.requested { scroll-margin-top: 7rem; }
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

  .cloud-context {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(15rem, 22rem);
    align-items: center;
    gap: 1.25rem;
    margin-top: 1.25rem;
    border-left: 2px solid var(--color-cyan);
    padding: 1rem;
    background: linear-gradient(90deg, color-mix(in oklab, var(--color-cyan) 7%, #000), var(--color-card));
    box-shadow: inset 0 0 0 1px var(--color-border);
  }
  .cloud-context-copy .kicker { margin: 0 0 0.3rem; }
  .cloud-context-copy h2 { margin: 0; font-size: 1rem; }
  .cloud-context-copy > p:last-child { margin: 0.35rem 0 0; color: var(--color-muted); font-size: 0.74rem; line-height: 1.5; }
  .cloud-context-copy .cloud-error { color: var(--color-danger); }
  .cloud-selector { display: grid; gap: 0.35rem; }
  .cloud-selector > span { color: var(--color-muted-2); font-family: var(--font-mono); font-size: 0.56rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
  .cloud-selector select {
    width: 100%;
    min-height: 2.75rem;
    border: 1px solid var(--color-border-strong);
    padding: 0 0.75rem;
    background: #050708;
    color: var(--color-fg);
    font-family: var(--font-mono);
    font-size: 0.72rem;
  }
  .cloud-target-name {
    display: flex;
    grid-column: 1 / -1;
    align-items: center;
    gap: 0.45rem;
    margin: -0.35rem 0 0;
    color: var(--color-cyan);
    font-family: var(--font-mono);
    font-size: 0.65rem;
  }
  .cloud-target-name span { color: var(--color-muted-2); text-transform: uppercase; }
  .cloud-target-name strong { overflow: hidden; color: var(--color-fg); text-overflow: ellipsis; white-space: nowrap; }

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
    .cloud-context { grid-template-columns: 1fr; }
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

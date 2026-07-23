<script lang="ts">
  import { onDestroy, onMount, tick } from "svelte";
  import { goto } from "$app/navigation";
  import type { Locale } from "$lib/catalog";
  import {
    CHAT_WS_SUBPROTOCOL,
    createApprovalSubmission,
    createInputSubmission,
    createTeamChatTurn,
    parseChatEvent,
    parseTeamChatAssistantScope,
    parseTeamStorage,
    parseTeamUpload,
    teamChatReconnectDelay,
    teamChatWebSocketPath,
  } from "$lib/teamChat.js";
  import { tr } from "$lib/i18n";
  import {
    MODEL_PROVIDERS,
    defaultModelFor,
    modelOptionLabel,
    modelsForProvider,
    normalizeInferenceSelection,
  } from "$lib/modelProviders.js";
  import { u } from "$lib/url";
  import HudIcon from "$lib/components/HudIcon.svelte";
  import PageIntro from "$lib/components/PageIntro.svelte";
  import Seo from "$lib/components/Seo.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);

  const SEL_KEY = "shimpz_current_team";

  let phase = $state("checking"); // checking | login | none | ready
  let teams = $state<any[]>([]);
  let selected = $state("");
  let inference = $state<any>(null); // {provider, model}
  let configuredProviders = $state<string[]>([]);
  let chatAssistantIds = $state<string[]>([]);
  let assistantScopeReady = $state(false);
  let teamFiles = $state<any[]>([]);
  let storageUsed = $state(0);
  let storageLimit = $state(100 * 1024 * 1024);
  let storageRemaining = $state(100 * 1024 * 1024);
  let storageLoading = $state(false);
  let storageError = $state("");
  let deletingFile = $state("");
  let attachedFileIds = $state<string[]>([]);
  let messages = $state<any[]>([]);
  let draft = $state("");
  let busy = $state(false);
  let stopping = $state(false);
  let status = $state("");
  let humanChallenge = $state<any>(null);
  let humanAnswer = $state("");
  let humanChoices = $state<string[]>([]);
  let uploading = $state(false);
  let thread = $state<HTMLElement | null>(null);
  let fileInput = $state<HTMLInputElement | null>(null);

  const activeTeam = $derived(teams.find((team) => team.team_id === selected) ?? null);
  const teamName = $derived(typeof activeTeam?.team_name === "string" ? activeTeam.team_name : "");
  const providerReady = $derived(Boolean(inference?.provider && configuredProviders.includes(inference.provider)));
  const canChat = $derived(Boolean(teamName && providerReady && assistantScopeReady));
  const storagePercent = $derived(
    storageLimit > 0 ? Math.min(100, Math.max(0, (storageUsed / storageLimit) * 100)) : 0,
  );
  const attachedFiles = $derived(teamFiles.filter((file) => attachedFileIds.includes(file.id)));

  function formatBytes(value: number) {
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(value < 10 * 1024 ? 1 : 0)} KB`;
    return `${(value / (1024 * 1024)).toFixed(value < 10 * 1024 * 1024 ? 1 : 0)} MB`;
  }

  function applyStorage(payload: any) {
    const parsed = parseTeamStorage(payload);
    teamFiles = parsed.files;
    attachedFileIds = attachedFileIds.filter((fileId) => parsed.files.some((file) => file.id === fileId));
    storageUsed = parsed.used_bytes;
    storageLimit = parsed.limit_bytes;
    storageRemaining = parsed.remaining_bytes;
  }

  async function refreshStorage(team_id = selected) {
    if (!team_id) return;
    storageLoading = true;
    storageError = "";
    try {
      const response = await fetch(`/api/teams/${team_id}/files`);
      const payload = await response.json().catch(() => ({}));
      if (selected !== team_id) return;
      if (!response.ok) throw new Error(payload?.detail ?? payload?.error ?? "storage unavailable");
      applyStorage(payload);
    } catch (error) {
      if (selected === team_id) storageError = error instanceof Error ? error.message : "storage unavailable";
    } finally {
      if (selected === team_id) storageLoading = false;
    }
  }

  // markdown renderer — loaded client-side only (marked + DOMPurify), so SSR/prerender never touches
  // the browser build. Until it loads, replies render as safe escaped text.
  let renderMd = $state<(s: string) => string>((s) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c] as string));

  // One WebSocket per Team releases one closed terminal event for each admitted turn.
  let ws = $state<WebSocket | null>(null);
  let wsReady = $state(false);
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let reconnectAttempt = 0;
  let chatDestroyed = false;
  const canSend = $derived(canChat && wsReady);

  function chatErrorText(statusCode: unknown, detailValue: unknown) {
    const detail = typeof detailValue === "string" ? detailValue.trim() : "";
    const normalized = detail.toLowerCase();
    if (Number(statusCode) === 409) {
      if (normalized.includes("active chat turn") || normalized.includes("already has an active")) {
        return tr("chat_turn_active", lang);
      }
      if (normalized.includes("api key") || normalized.includes("model provider")) {
        return tr("brain_wait", lang);
      }
    }
    return "✗ " + (detail || "error");
  }

  function connectWs(team_id = selected) {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    const previous = ws;
    ws = null;
    previous?.close();
    wsReady = false;
    if (!team_id || selected !== team_id || chatDestroyed) return;
    const proto = location.protocol === "https:" ? "wss://" : "ws://";
    const sock = new WebSocket(
      `${proto}${location.host}${teamChatWebSocketPath(team_id)}`,
      CHAT_WS_SUBPROTOCOL,
    );
    sock.onopen = () => {
      if (ws !== sock || selected !== team_id) return;
      if (sock.protocol !== CHAT_WS_SUBPROTOCOL) {
        ws = null;
        sock.close(1002, "required subprotocol missing");
        messages.push({ role: "system", tone: "error", text: tr("chat_protocol_error", lang) });
        return;
      }
      reconnectAttempt = 0;
      wsReady = true;
    };
    sock.onclose = () => {
      if (ws !== sock || selected !== team_id) return;
      wsReady = false;
      ws = null;
      if (busy) {
        busy = false;
        stopping = false;
        status = "";
        messages.push({ role: "system", tone: "error", text: tr("chat_disconnected", lang) });
        scrollDown(true);
      }
      if (!chatDestroyed && phase === "ready" && selected === team_id && reconnectTimer === null) {
        const delay = teamChatReconnectDelay(reconnectAttempt);
        reconnectAttempt += 1;
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null;
          if (!chatDestroyed && phase === "ready" && selected === team_id) connectWs(team_id);
        }, delay);
      }
    };
    sock.onmessage = (ev) => {
      if (ws !== sock || selected !== team_id) return;
      let m;
      try {
        m = parseChatEvent(JSON.parse(ev.data), team_id, teamName);
      } catch {
        busy = false;
        stopping = false;
        status = "";
        messages.push({ role: "system", tone: "error", text: tr("chat_protocol_error", lang) });
        wsReady = false;
        ws = null;
        sock.close(1002, "invalid terminal event");
        scrollDown(true);
        return;
      }
      stopping = false;
      if (m.type === "input-required" || m.type === "approval-required") {
        humanChallenge = m;
        humanAnswer = m.type === "input-required" && m.request.type === "choice"
          ? (m.request.options[0] ?? "")
          : "";
        humanChoices = [];
        busy = false;
        status = "";
      } else if (m.type === "done") {
        humanChallenge = null;
        messages.push({ role: "assistant", team_name: m.team_name, text: m.reply });
        busy = false;
        status = "";
      } else if (m.type === "stopped") {
        humanChallenge = null;
        busy = false;
        status = "";
      } else if (m.type === "error") {
        busy = false;
        status = "";
        messages.push({ role: "system", tone: "error", text: chatErrorText(m.status, m.detail) });
      }
      scrollDown(true);
    };
    ws = sock;
  }

  function stopTurn() {
    if (!wsReady || !ws || stopping) return;
    stopping = true;
    try {
      ws.send(JSON.stringify({ type: "stop" }));
    } catch {
      stopping = false;
    }
  }

  function toggleHumanChoice(option: string) {
    humanChoices = humanChoices.includes(option)
      ? humanChoices.filter((item) => item !== option)
      : [...humanChoices, option];
  }

  function inputSubmissionAnswer() {
    const requestType = humanChallenge?.request?.type;
    if (requestType === "int") {
      const value = Number(humanAnswer);
      if (!Number.isSafeInteger(value) || humanAnswer.trim() === "") throw new TypeError("invalid integer");
      return value;
    }
    if (requestType === "float") {
      const value = Number(humanAnswer);
      if (!Number.isFinite(value) || humanAnswer.trim() === "") throw new TypeError("invalid number");
      return value;
    }
    if (requestType === "bool") {
      if (!["true", "false"].includes(humanAnswer)) throw new TypeError("invalid boolean");
      return humanAnswer === "true";
    }
    if (requestType === "choices") return humanChoices;
    return humanAnswer;
  }

  function humanSubmissionReady() {
    if (!humanChallenge || busy || stopping) return false;
    if (humanChallenge.type === "approval-required") return true;
    if (humanChallenge.request.type === "choices") return humanChoices.length > 0;
    return humanAnswer.trim() !== "";
  }

  function submitHumanChallenge() {
    if (!wsReady || !ws || !humanSubmissionReady()) return;
    try {
      const frame = humanChallenge.type === "approval-required"
        ? createApprovalSubmission(humanChallenge.challenge_id)
        : createInputSubmission(humanChallenge.challenge_id, inputSubmissionAnswer());
      busy = true;
      status = lang === "pt" ? "Continuando…" : "Continuing…";
      ws.send(JSON.stringify(frame));
    } catch {
      messages.push({
        role: "system",
        tone: "error",
        text: lang === "pt" ? "Resposta inválida." : "Invalid answer.",
      });
      busy = false;
      status = "";
    }
  }

  let providerChoice = $state("openai");
  let modelChoice = $state(defaultModelFor("openai"));
  let loadedProvider = $state("openai");
  let loadedModel = $state(defaultModelFor("openai"));
  let inferenceBusy = $state(false);
  let inferenceError = $state("");
  let inferenceSaved = $state("");

  const inferenceHasChanges = $derived(
    providerChoice !== loadedProvider || modelChoice.trim() !== loadedModel,
  );
  const runtimeBusy = $derived(busy || inferenceBusy || Boolean(humanChallenge));

  function chooseProvider(event: Event) {
    providerChoice = (event.currentTarget as HTMLSelectElement).value;
    modelChoice = defaultModelFor(providerChoice);
    inferenceError = "";
    inferenceSaved = "";
  }

  // Auto-follow only when the Captain is already at the bottom; never yank them while reading.
  let stick = $state(true);

  function onThreadScroll() {
    if (!thread) return;
    stick = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 80;
  }

  async function scrollDown(smooth = false) {
    await tick();
    if (!thread || !stick) return;
    const rm = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    thread.scrollTo({ top: thread.scrollHeight, behavior: smooth && !rm ? "smooth" : "auto" });
  }

  async function loadTeamContext() {
    const team_id = selected;
    inference = null;
    chatAssistantIds = [];
    assistantScopeReady = false;
    teamFiles = [];
    attachedFileIds = [];
    storageUsed = 0;
    storageRemaining = storageLimit;
    storageError = "";
    humanChallenge = null;
    humanAnswer = "";
    humanChoices = [];
    if (!team_id) return;
    localStorage.setItem(SEL_KEY, team_id);
    const teamName = teams.find((team) => team.team_id === team_id)?.team_name ?? team_id;
    localStorage.setItem(SEL_KEY + "_name", teamName);
    storageLoading = true;
    const [currentInference, f, assistants] = await Promise.all([
      fetch(`/api/teams/${team_id}/inference`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetch(`/api/teams/${team_id}/files`).then(async (r) => ({ ok: r.ok, data: await r.json().catch(() => ({})) })).catch(() => ({ ok: false, data: {} })),
      fetch(`/api/teams/${team_id}/chat/assistants`).then(async (r) => ({ ok: r.ok, data: await r.json().catch(() => ({})) })).catch(() => ({ ok: false, data: {} })),
    ]);
    if (selected !== team_id) return;
    inference = currentInference;
    try {
      if (!f.ok) throw new Error(f.data?.detail ?? f.data?.error ?? "storage unavailable");
      applyStorage(f.data);
    } catch (error) {
      storageError = error instanceof Error ? error.message : "storage unavailable";
    } finally {
      storageLoading = false;
    }
    if (assistants.ok) {
      try {
        chatAssistantIds = parseTeamChatAssistantScope(assistants.data);
        assistantScopeReady = true;
      } catch {
        assistantScopeReady = false;
      }
    }
    const team = teams.find((item) => item.team_id === team_id);
    loadedProvider = currentInference?.provider ?? team?.provider ?? "openai";
    loadedModel = String(currentInference?.model ?? team?.model ?? defaultModelFor(loadedProvider));
    providerChoice = loadedProvider;
    modelChoice = loadedModel;
    connectWs(team_id);
  }

  function resetTeamSession() {
    inferenceError = "";
    inferenceSaved = "";
    const previous = ws;
    ws = null;
    previous?.close();
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    reconnectAttempt = 0;
    wsReady = false;
    busy = false;
    stopping = false;
    status = "";
    messages = [];
    draft = "";
    teamFiles = [];
    chatAssistantIds = [];
    assistantScopeReady = false;
    attachedFileIds = [];
    storageUsed = 0;
    storageError = "";
    deletingFile = "";
  }

  async function changeTeam(next: string, updateUrl = true) {
    if (inferenceBusy || !teams.some((team) => team.team_id === next) || next === selected) return;
    resetTeamSession();
    selected = next;
    if (updateUrl) {
      await goto(u.chat(lang, next), { keepFocus: true, noScroll: true });
    }
    await loadTeamContext();
  }

  async function saveInference() {
    if (!selected || !inferenceHasChanges || inferenceBusy || busy) return;
    const team_id = selected;
    inferenceBusy = true;
    inferenceError = "";
    inferenceSaved = "";
    try {
      const payload = normalizeInferenceSelection(providerChoice, modelChoice);
      const response = await fetch(`/api/teams/${team_id}/inference`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        inferenceError = result?.detail ?? result?.error ?? tr("brain_switch_failed", lang);
        return;
      }
      if (selected !== team_id) return;
      inference = { provider: payload.provider, model: payload.model };
      loadedProvider = payload.provider;
      loadedModel = payload.model;
      teams = teams.map((item) =>
        item.team_id === team_id ? { ...item, provider: payload.provider, model: payload.model } : item,
      );
      inferenceSaved = tr("brain_switch_ok", lang);
    } catch {
      inferenceError = tr("brain_switch_failed", lang);
    } finally {
      inferenceBusy = false;
    }
  }

  function syncTeamFromUrl() {
    if (phase !== "ready" || location.pathname !== u.chat(lang)) return;
    const requested = new URL(location.href).searchParams.get("team") ?? "";
    const next = teams.some((team) => team.team_id === requested) ? requested : teams[0]?.team_id ?? "";
    if (!next) return;
    if (requested !== next) history.replaceState(history.state, "", u.chat(lang, next));
    if (next !== selected) void changeTeam(next, false);
  }

  async function boot() {
    const me = await (await fetch("/api/me")).json().catch(() => ({}));
    if (!me.authenticated) {
      phase = "login";
      return;
    }
    const [r, brainsResponse] = await Promise.all([
      fetch("/api/teams"),
      fetch("/api/brains").catch(() => null),
    ]);
    const brainsResult = await brainsResponse?.json().catch(() => null);
    configuredProviders = brainsResponse?.ok && Array.isArray(brainsResult?.brains)
      ? brainsResult.brains
          .filter((entry: any) => entry?.status === "configured" && (entry.provider === "openai" || entry.provider === "anthropic"))
          .map((entry: any) => entry.provider)
      : [];
    teams = r.ok ? ((await r.json()).teams ?? []) : [];
    if (teams.length === 0) {
      phase = "none";
      return;
    }
    const requested = new URL(location.href).searchParams.get("team") ?? "";
    const stored = localStorage.getItem(SEL_KEY) ?? "";
    selected = teams.some((team) => team.team_id === requested)
      ? requested
      : teams.some((team) => team.team_id === stored)
        ? stored
        : teams[0].team_id;
    if (requested !== selected) history.replaceState(history.state, "", u.chat(lang, selected));
    await loadTeamContext();
    phase = "ready";
  }

  async function send() {
    const text = draft.trim();
    if (!text || runtimeBusy || !selected || !canSend || !ws) return;
    let turn: { message: string; files: string[]; assistant_ids: string[] };
    try {
      turn = createTeamChatTurn(text, attachedFileIds, chatAssistantIds);
    } catch {
      return;
    }
    draft = "";
    busy = true;
    stopping = false;
    status = tr("chat_thinking", lang);
    messages.push({ role: "captain", text, files: attachedFiles.map((file) => file.name) });
    attachedFileIds = [];
    stick = true; // sending re-engages auto-follow
    scrollDown(true);
    ws.send(JSON.stringify({ type: "chat", ...turn }));
  }

  async function upload(ev: Event) {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (!file || !selected || uploading || inferenceBusy) return;
    uploading = true;
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await fetch(`/api/teams/${selected}/files`, { method: "POST", body: form });
      const d = await r.json().catch(() => ({}));
      if (r.ok) {
        const uploaded = parseTeamUpload(d);
        teamFiles = [...teamFiles, uploaded.file];
        storageUsed = uploaded.used_bytes;
        storageLimit = uploaded.limit_bytes;
        storageRemaining = uploaded.remaining_bytes;
        messages.push({
          role: "system",
          tone: "success",
          text: `${tr("chat_file_ok", lang)} ${uploaded.file.name}. ${tr("chat_file_boundary", lang)}`,
        });
      } else {
        messages.push({ role: "system", tone: "error", text: "✗ " + (d.error ?? d.detail ?? "upload error") });
      }
    } catch {
      messages.push({ role: "system", tone: "error", text: "✗ upload error" });
    } finally {
      uploading = false;
      if (fileInput) fileInput.value = "";
      stick = true;
      scrollDown(true);
    }
  }

  async function deleteFile(fileId: string) {
    if (!selected || deletingFile || uploading || runtimeBusy) return;
    deletingFile = fileId;
    storageError = "";
    try {
      const response = await fetch(`/api/teams/${selected}/files/${fileId}`, { method: "DELETE" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail ?? payload?.error ?? "delete failed");
      await refreshStorage(selected);
    } catch (error) {
      storageError = error instanceof Error ? error.message : "delete failed";
    } finally {
      deletingFile = "";
    }
  }

  function toggleFile(fileId: string) {
    if (runtimeBusy || uploading || deletingFile) return;
    if (attachedFileIds.includes(fileId)) {
      attachedFileIds = attachedFileIds.filter((value) => value !== fileId);
      return;
    }
    if (attachedFileIds.length >= 8 || !teamFiles.some((file) => file.id === fileId)) return;
    attachedFileIds = [...attachedFileIds, fileId];
  }

  onMount(async () => {
    // markdown, browser-only: raw model output is escaped first (marked won't emit HTML from us),
    // then DOMPurify strips anything unsafe — so a reply that contains HTML/script can't run.
    try {
      const [{ marked }, dp] = await Promise.all([import("marked"), import("dompurify")]);
      const purify = dp.default;
      renderMd = (s: string) => purify.sanitize(marked.parse(s ?? "", { breaks: true, gfm: true, async: false }) as string);
    } catch {
      /* keep the escaped-text fallback */
    }
    boot();
  });
  onDestroy(() => {
    chatDestroyed = true;
    if (reconnectTimer !== null) clearTimeout(reconnectTimer);
    ws?.close();
  });
</script>

<svelte:window onpopstate={syncTeamFromUrl} />

<Seo title={tr("chat_title", lang)} description={tr("chat_lead", lang)} {lang} />

<section class="wrap chat-page">
  {#snippet chatMedia()}
    <div class="chat-hero-icon"><HudIcon name="chat" size={40} /></div>
  {/snippet}

  {#snippet chatMeta()}
    {#if phase === "ready"}
      <span class="connection-chip" class:online={wsReady}>
        <i aria-hidden="true"></i>
        {wsReady ? tr("chat_connection_live", lang) : tr("chat_connection_offline", lang)}
      </span>
    {/if}
  {/snippet}

  <PageIntro
    headingId="chat-title"
    kicker={tr("chat_kicker", lang)}
    title={teamName || tr("nav_chat", lang)}
    description={tr("chat_lead", lang)}
    media={chatMedia}
    meta={chatMeta}
  />

  {#if phase === "checking"}
    <div class="panel page-state" aria-live="polite"><span class="loading-pulse" aria-hidden="true"></span><p>{tr("loading", lang)}</p></div>
  {:else if phase === "login"}
    <div class="panel page-state"><HudIcon name="user" size={28} /><p>{tr("chat_login", lang)}</p><a class="btn-primary" href={u.login(lang)}>{tr("log_in", lang)}</a></div>
  {:else if phase === "none"}
    <div class="panel page-state"><HudIcon name="team" size={30} /><p>{tr("chat_no_team", lang)}</p><a class="btn-primary" href={u.team(lang)}>{tr("team_submit", lang)}</a></div>
  {:else}
    <div class="chat-workspace">
      <aside class="control-rail" aria-label={tr("chat_team_title", lang)}>
        <section class="panel control-card" aria-labelledby="team-context-title">
          <header class="control-heading">
            <span class="control-icon" aria-hidden="true"><HudIcon name="team" size={21} /></span>
            <div><p class="kicker">Team</p><h2 id="team-context-title">{tr("chat_team_title", lang)}</h2></div>
          </header>
          <p class="control-help">{tr("chat_team_help", lang)}</p>
          <label class="field-stack">
            <span>{tr("my_teams", lang)}</span>
            <select
              class="field field-sm"
              aria-label={tr("my_teams", lang)}
              value={selected}
              disabled={runtimeBusy}
              onchange={(event) => changeTeam((event.currentTarget as HTMLSelectElement).value)}>
              {#each teams as team (team.team_id)}<option value={team.team_id}>{team.team_name}</option>{/each}
            </select>
          </label>
          <code class="team-id">{selected}</code>
        </section>

        <section class="panel control-card brain-control" aria-labelledby="brain-control-title" aria-busy={inferenceBusy}>
          <header class="control-heading">
            <span class="control-icon brain-icon" aria-hidden="true"><HudIcon name="brain" size={21} /></span>
            <div><p class="kicker">Runtime</p><h2 id="brain-control-title">{tr("chat_brain_title", lang)}</h2></div>
            {#if inference}
              <span class="brain-state" class:ready={providerReady} class:pending={!providerReady}>
                <i aria-hidden="true"></i>
                {providerReady ? tr("brain_authenticated_verified", lang) : tr("brain_not_configured", lang)}
              </span>
            {/if}
          </header>
          <p class="control-help">{tr("chat_brain_help", lang)}</p>

          {#if inference}
            <div class="brain-editor">
              <label class="field-stack">
                <span>{tr("brain_provider", lang)}</span>
                <select class="field field-sm" value={providerChoice} disabled={runtimeBusy} onchange={chooseProvider}>
                  {#each MODEL_PROVIDERS as option (option.id)}
                    <option value={option.id}>{option.title}</option>
                  {/each}
                </select>
              </label>
              <label class="field-stack">
                <span>{tr("model_label", lang)}</span>
                <select class="field field-sm" bind:value={modelChoice} disabled={runtimeBusy}>
                  {#each modelsForProvider(providerChoice) as option (option.id)}
                    <option value={option.id}>{modelOptionLabel(option, lang)}</option>
                  {/each}
                </select>
              </label>
              <button class="btn-primary brain-switch" type="button" disabled={!inferenceHasChanges || runtimeBusy} onclick={saveInference}>
                <HudIcon name="retry" size={16} />
                {inferenceBusy ? tr("brain_switching", lang) : tr("brain_switch", lang)}
              </button>
              <p class="brain-hint"><HudIcon name="shield" size={15} />{tr("brain_switch_hint", lang)}</p>
              <p class="brain-hint"><HudIcon name="brain" size={15} />{tr("model_price_note", lang)}</p>
              {#if inferenceError}<p class="notice notice-error compact-notice" role="alert">{inferenceError}</p>{/if}
              {#if inferenceSaved}<p class="notice notice-success compact-notice" role="status">{inferenceSaved}</p>{/if}
            </div>

            <div class="brain-access">
              <div class="access-heading"><HudIcon name="key" size={16} /><span>{tr("brain_auth_type", lang)}</span></div>
              {#if providerReady}
                <p class="access-state success"><HudIcon name="check" size={16} />{tr("brain_authenticated_verified", lang)}</p>
              {:else}
                <p class="access-copy">{tr("brain_wait", lang)}</p>
                <div class="access-actions">
                  <a class="btn-primary" href={u.account(lang)}>{tr("brain_account_cta", lang)}</a>
                </div>
              {/if}
            </div>
          {:else}
            <p class="inference-progress"><span class="loading-pulse" aria-hidden="true"></span>{tr("loading", lang)}</p>
          {/if}
        </section>

        <section class="panel control-card storage-control" aria-labelledby="storage-context-title">
          <header class="control-heading">
            <span class="control-icon storage-icon" aria-hidden="true"><HudIcon name="attach" size={20} /></span>
            <div><p class="kicker">Team</p><h2 id="storage-context-title">{tr("chat_storage_title", lang)}</h2></div>
            <span class="storage-count">{teamFiles.length}</span>
          </header>
          <p class="control-help">{tr("chat_storage_help", lang)}</p>
          <div class="storage-meter" aria-label={`${formatBytes(storageUsed)} / ${formatBytes(storageLimit)}`}>
            <span style={`width:${storagePercent}%`}></span>
          </div>
          <p class="storage-usage">
            <span>{formatBytes(storageUsed)} / {formatBytes(storageLimit)}</span>
            <span>{formatBytes(storageRemaining)} {tr("chat_storage_free", lang)}</span>
          </p>
          {#if storageLoading}
            <p class="storage-state"><span class="loading-pulse" aria-hidden="true"></span>{tr("loading", lang)}</p>
          {:else if storageError}
            <div class="storage-error" role="alert">
              <p>{storageError}</p>
              <button class="btn-ghost" type="button" onclick={() => refreshStorage()}>{tr("retry", lang)}</button>
            </div>
          {:else if teamFiles.length}
            <ul class="file-list">
              {#each teamFiles as file (file.id)}
                <li class:attached={attachedFileIds.includes(file.id)}>
                  <label class="file-select" title={tr("chat_file_select", lang)}>
                    <input
                      type="checkbox"
                      checked={attachedFileIds.includes(file.id)}
                      disabled={runtimeBusy || uploading || Boolean(deletingFile) || (attachedFileIds.length >= 8 && !attachedFileIds.includes(file.id))}
                      aria-label={`${tr("chat_file_select", lang)} ${file.name}`}
                      onchange={() => toggleFile(file.id)} />
                    <span class="file-icon" aria-hidden="true"><HudIcon name="attach" size={14} /></span>
                  </label>
                  <span class="file-metadata">
                    <strong>{file.name}</strong>
                    <small>{file.media_type} · {formatBytes(file.size)}</small>
                  </span>
                  <button
                    class="file-delete"
                    type="button"
                    title={tr("chat_file_delete", lang)}
                    aria-label={`${tr("chat_file_delete", lang)} ${file.name}`}
                    disabled={Boolean(deletingFile) || uploading || runtimeBusy}
                    onclick={() => deleteFile(file.id)}>
                    {#if deletingFile === file.id}…{:else}<HudIcon name="uninstall" size={14} />{/if}
                  </button>
                </li>
              {/each}
            </ul>
          {:else}
            <p class="storage-state">{tr("chat_storage_empty", lang)}</p>
          {/if}
        </section>
      </aside>

      <main class="conversation-shell" aria-labelledby="conversation-title">
        <header class="conversation-header">
          <span class="conversation-avatar" aria-hidden="true"><HudIcon name="team" size={24} /></span>
          <div>
            <p class="kicker">{tr("chat_team_target", lang)}</p>
            <h2 id="conversation-title">{teamName}</h2>
          </div>
          <span class="conversation-status" class:online={wsReady && canChat}>
            <i aria-hidden="true"></i>{canChat ? tr("chat_ready", lang) : tr("chat_setup_required", lang)}
          </span>
        </header>
        <div
          bind:this={thread}
          onscroll={onThreadScroll}
          role="log"
          aria-live="polite"
          aria-relevant="additions"
          aria-label={tr("chat_thread_label", lang)}
          aria-busy={runtimeBusy}
          tabindex="-1"
          class="conversation-thread">
          {#each messages as m, i (i)}
            {#if m.role === "captain"}
              <div class="message captain-message">
                <span>{m.text}</span>
                {#if m.files?.length}
                  <span class="message-files">
                    {#each m.files as filename (filename)}<code>{filename}</code>{/each}
                  </span>
                {/if}
              </div>
            {:else if m.role === "assistant"}
              <div class="message assistant-message">
                <small class="message-author">{m.team_name || teamName}</small>
                <div class="md">{@html renderMd(m.text || "")}</div>
              </div>
            {:else}
              <p
                class="px-3 py-2 text-center text-xs"
                class:dim={!m.tone}
                class:notice={Boolean(m.tone)}
                class:notice-error={m.tone === "error"}
                class:notice-success={m.tone === "success"}
                role={m.tone === "error" ? "alert" : m.tone === "success" ? "status" : undefined}
              >{m.text}</p>
            {/if}
          {/each}
          {#if busy && status}<p class="turn-status"><span class="loading-pulse" aria-hidden="true"></span>{status}</p>{/if}
          {#if messages.length === 0 && !busy}<div class="conversation-empty"><HudIcon name="chat" size={30} /><p>{tr("chat_empty", lang)}</p></div>{/if}
        </div>
        {#if humanChallenge}
          <section class="human-challenge" aria-live="polite" aria-busy={busy}>
            {#if humanChallenge.type === "approval-required"}
              {@const requirement = humanChallenge.requirements[0]}
              <p class="kicker">{requirement.assistant_name} · {requirement.power_id}</p>
              <h3>{requirement.title}</h3>
              <p>{requirement.summary}</p>
              {#if requirement.docs}<small>{requirement.docs}</small>{/if}
            {:else}
              <p class="kicker">{lang === "pt" ? "Entrada necessária" : "Input required"}</p>
              <h3>{humanChallenge.request.title}</h3>
              <p>{humanChallenge.request.summary}</p>
              {#if humanChallenge.request.type === "choice"}
                <select class="field" bind:value={humanAnswer} disabled={busy}>
                  {#each humanChallenge.request.options as option (option)}
                    <option value={option}>{option}</option>
                  {/each}
                </select>
              {:else if humanChallenge.request.type === "choices"}
                <div class="challenge-options">
                  {#each humanChallenge.request.options as option (option)}
                    <label>
                      <input
                        type="checkbox"
                        checked={humanChoices.includes(option)}
                        disabled={busy}
                        onchange={() => toggleHumanChoice(option)} />
                      <span>{option}</span>
                    </label>
                  {/each}
                </div>
              {:else if humanChallenge.request.type === "bool"}
                <select class="field" bind:value={humanAnswer} disabled={busy}>
                  <option value="">{lang === "pt" ? "Selecione" : "Select"}</option>
                  <option value="true">{lang === "pt" ? "Sim" : "Yes"}</option>
                  <option value="false">{lang === "pt" ? "Não" : "No"}</option>
                </select>
              {:else}
                <input
                  class="field"
                  type={humanChallenge.request.type === "str" ? "text" : "number"}
                  step={humanChallenge.request.type === "int" ? "1" : "any"}
                  bind:value={humanAnswer}
                  disabled={busy} />
              {/if}
              {#if humanChallenge.request.docs}<small>{humanChallenge.request.docs}</small>{/if}
            {/if}
            <div class="challenge-actions">
              <button class="btn-ghost" type="button" disabled={stopping} onclick={stopTurn}>
                {tr("chat_stop", lang)}
              </button>
              <button
                class="btn-primary"
                type="button"
                disabled={!humanSubmissionReady()}
                onclick={submitHumanChallenge}>
                {humanChallenge.type === "approval-required"
                  ? (lang === "pt" ? "Aprovar" : "Approve")
                  : (lang === "pt" ? "Continuar" : "Continue")}
              </button>
            </div>
          </section>
        {/if}
        <div class="composer">
          {#if attachedFiles.length}
            <div class="attachment-tray" aria-label={tr("chat_files_selected", lang)}>
              <span>{attachedFiles.length}/8</span>
              {#each attachedFiles as file (file.id)}
                <button type="button" onclick={() => toggleFile(file.id)} aria-label={`${tr("chat_file_unselect", lang)} ${file.name}`}>
                  <HudIcon name="attach" size={12} />{file.name}<span aria-hidden="true">×</span>
                </button>
              {/each}
            </div>
          {/if}
          <input bind:this={fileInput} type="file" class="hidden" onchange={upload} />
          <button class="btn-ghost composer-icon" type="button" title={tr("chat_attach", lang)} aria-label={tr("chat_attach", lang)} disabled={uploading || runtimeBusy || !selected} onclick={() => fileInput?.click()}>
            {#if uploading}
              …
            {:else}
              <HudIcon name="attach" size={18} />
            {/if}
          </button>
          <textarea
            class="field field-area composer-input"
            placeholder={tr("chat_placeholder", lang)}
            aria-label={tr("chat_placeholder", lang)}
            rows="2"
            disabled={runtimeBusy || !canSend}
            bind:value={draft}
            onkeydown={(event) => event.key === "Enter" && !event.shiftKey && !event.isComposing && (event.preventDefault(), send())}></textarea>
          {#if busy}
            <button class="btn-danger composer-action" type="button" disabled={stopping} onclick={stopTurn}><HudIcon name="stop" size={17} />{tr("chat_stop", lang)}</button>
          {:else}
            <button class="btn-primary composer-action" type="button" disabled={!draft.trim() || runtimeBusy || !canSend} onclick={send}><HudIcon name="send" size={17} />{tr("chat_send", lang)}</button>
          {/if}
        </div>
      </main>
    </div>
  {/if}
</section>

<style>
  .chat-page { padding-block: 2.5rem 4rem; }

  .chat-hero-icon {
    display: grid;
    width: 4.5rem;
    height: 4.5rem;
    place-items: center;
    color: var(--color-cyan);
    background: color-mix(in oklab, var(--color-cyan) 7%, #000);
    box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--color-cyan) 46%, var(--color-border));
    clip-path: polygon(12px 0, 100% 0, 100% calc(100% - 12px), calc(100% - 12px) 100%, 0 100%, 0 12px);
  }

  .connection-chip,
  .conversation-status,
  .brain-state {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    color: var(--color-muted);
    font-family: var(--font-mono);
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .connection-chip i,
  .conversation-status i,
  .brain-state i {
    width: 0.45rem;
    height: 0.45rem;
    flex: none;
    background: var(--color-muted-2);
    box-shadow: 0 0 0 1px #000;
  }

  .connection-chip.online,
  .conversation-status.online,
  .brain-state.ready { color: var(--color-green); }

  .connection-chip.online i,
  .conversation-status.online i,
  .brain-state.ready i {
    background: var(--color-green);
    box-shadow: 0 0 8px color-mix(in oklab, var(--color-green) 64%, transparent);
  }

  .brain-state.pending { color: var(--color-yellow); }
  .brain-state.pending i { background: var(--color-yellow); }

  .page-state {
    display: flex;
    min-height: 14rem;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    margin-top: 1.5rem;
    color: var(--color-muted);
    text-align: center;
  }

  .page-state > :global(svg) { color: var(--color-cyan); }
  .page-state p { max-width: 34rem; }

  .loading-pulse {
    width: 0.55rem;
    height: 0.55rem;
    flex: none;
    background: var(--color-cyan);
    box-shadow: 0 0 10px rgba(0, 240, 255, 0.7);
    animation: pulse 1.2s steps(2, end) infinite;
  }

  .chat-workspace {
    display: grid;
    grid-template-columns: minmax(17.5rem, 20rem) minmax(0, 1fr);
    align-items: start;
    gap: 1rem;
    margin-top: 1.5rem;
  }

  .control-rail {
    position: sticky;
    top: 7rem;
    display: grid;
    max-height: calc(100vh - 8rem);
    gap: 0.8rem;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: var(--color-border-strong) transparent;
  }

  .control-card { padding: 1rem; }
  .control-card::before {
    content: "";
    position: absolute;
    inset: 0 auto 0 0;
    width: 2px;
    background: color-mix(in oklab, var(--color-cyan) 48%, transparent);
  }

  .control-heading {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 0.7rem;
  }

  .control-icon,
  .conversation-avatar {
    display: grid;
    width: 2.5rem;
    height: 2.5rem;
    flex: none;
    place-items: center;
    color: var(--color-cyan);
    background: #000;
    box-shadow: inset 0 0 0 1px var(--color-border-strong);
    clip-path: polygon(7px 0, 100% 0, 100% calc(100% - 7px), calc(100% - 7px) 100%, 0 100%, 0 7px);
  }

  .brain-icon { color: var(--color-magenta); }
  .control-heading .kicker,
  .conversation-header .kicker { margin: 0 0 0.08rem; font-size: 0.55rem; }

  .control-heading h2,
  .conversation-header h2 {
    margin: 0;
    font-size: 0.92rem;
    line-height: 1.2;
    letter-spacing: -0.025em;
  }

  .control-help {
    margin: 0.85rem 0;
    color: var(--color-muted);
    font-size: 0.74rem;
    line-height: 1.55;
  }

  .field-stack { display: grid; gap: 0.35rem; }
  .field-stack > span,
  .access-heading {
    color: var(--color-muted);
    font-family: var(--font-mono);
    font-size: 0.61rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .team-id {
    display: block;
    max-width: 100%;
    margin-top: 0.65rem;
    overflow: hidden;
    color: var(--color-muted-2);
    font-size: 0.58rem;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .brain-state { justify-self: end; font-size: 0.54rem; text-align: right; }
  .brain-editor,
  .brain-access { display: grid; gap: 0.65rem; }
  .brain-editor { padding-top: 0.1rem; }
  .brain-access { margin-top: 0.9rem; border-top: 1px solid var(--color-border); padding-top: 0.85rem; }
  .brain-switch { width: 100%; min-height: 2.55rem; padding: 0.55rem 0.8rem; font-size: 0.68rem; }

  .brain-hint,
  .access-copy,
  .inference-progress {
    margin: 0;
    color: var(--color-muted);
    font-size: 0.7rem;
    line-height: 1.5;
  }

  .brain-hint,
  .inference-progress,
  .access-heading,
  .access-state { display: flex; align-items: flex-start; gap: 0.45rem; }
  .brain-hint { color: var(--color-muted-2); }
  .brain-hint > :global(svg) { margin-top: 0.12rem; color: var(--color-cyan); }
  .compact-notice { margin: 0; padding: 0.65rem 0.75rem; font-size: 0.68rem; line-height: 1.45; }
  .access-heading { align-items: center; color: var(--color-fg); }
  .access-heading > :global(svg) { color: var(--color-cyan); }
  .access-state { margin: 0; color: var(--color-muted); font-size: 0.72rem; }
  .access-state.success { color: var(--color-green); }
  .access-actions { display: grid; gap: 0.5rem; }
  .access-actions { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .access-actions > :global(*) { min-width: 0; padding-inline: 0.65rem; font-size: 0.62rem; }
  .inference-progress { align-items: center; }

  .storage-count {
    min-width: 1.8rem;
    padding: 0.15rem 0.4rem;
    color: var(--color-green);
    background: color-mix(in oklab, var(--color-green) 7%, #000);
    box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--color-green) 35%, var(--color-border));
    font-family: var(--font-mono);
    font-size: 0.64rem;
    text-align: center;
  }

  .storage-icon { color: var(--color-green); }
  .storage-meter { height: 0.32rem; overflow: hidden; background: var(--color-border); }
  .storage-meter span { display: block; height: 100%; min-width: 1px; background: var(--color-green); box-shadow: 0 0 8px color-mix(in oklab, var(--color-green) 55%, transparent); }
  .storage-usage { display: flex; justify-content: space-between; gap: 0.5rem; margin: 0.35rem 0 0; color: var(--color-muted-2); font-family: var(--font-mono); font-size: 0.54rem; }
  .storage-state { display: flex; align-items: center; gap: 0.5rem; margin: 0.75rem 0 0; color: var(--color-muted); font-size: 0.68rem; }
  .storage-error { display: grid; gap: 0.45rem; margin-top: 0.7rem; }
  .storage-error p { margin: 0; color: var(--color-danger); font-size: 0.65rem; line-height: 1.4; overflow-wrap: anywhere; }
  .storage-error button { width: fit-content; min-height: 2rem; padding: 0.35rem 0.55rem; font-size: 0.58rem; }
  .file-list { display: grid; gap: 0.35rem; margin: 0.75rem 0 0; padding: 0; list-style: none; }
  .file-list li { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 0.45rem; border-top: 1px solid var(--color-border); padding-top: 0.45rem; }
  .file-list li.attached { color: var(--color-cyan); }
  .file-select { display: grid; grid-template-columns: auto auto; align-items: center; gap: 0.3rem; cursor: pointer; }
  .file-select input { width: 0.75rem; height: 0.75rem; margin: 0; accent-color: var(--color-cyan); }
  .file-icon { color: var(--color-green); }
  .file-list li.attached .file-icon { color: var(--color-cyan); }
  .file-metadata { display: grid; min-width: 0; }
  .file-metadata strong { overflow: hidden; font-family: var(--font-mono); font-size: 0.62rem; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
  .file-metadata small { overflow: hidden; color: var(--color-muted-2); font-size: 0.51rem; text-overflow: ellipsis; white-space: nowrap; }
  .file-delete { display: grid; width: 1.8rem; height: 1.8rem; place-items: center; border: 0; padding: 0; color: var(--color-muted); background: transparent; cursor: pointer; }
  .file-delete:hover:not(:disabled) { color: var(--color-danger); background: color-mix(in oklab, var(--color-danger) 8%, transparent); }
  .file-delete:focus-visible { outline: 2px solid var(--color-cyan); outline-offset: 2px; }
  .file-delete:disabled { cursor: not-allowed; opacity: 0.45; }

  .conversation-shell {
    display: flex;
    min-width: 0;
    min-height: 42rem;
    flex-direction: column;
    overflow: hidden;
    background: linear-gradient(180deg, var(--color-card-2), #020202);
    box-shadow: inset 0 0 0 1px var(--color-border);
    clip-path: polygon(14px 0, 100% 0, 100% calc(100% - 14px), calc(100% - 14px) 100%, 0 100%, 0 14px);
  }

  .conversation-header {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 0.75rem;
    border-bottom: 1px solid var(--color-border);
    padding: 0.9rem 1rem;
    background: #050505;
  }

  .conversation-avatar { width: 2.75rem; height: 2.75rem; color: var(--color-magenta); }
  .conversation-status { justify-self: end; }

  .conversation-thread {
    display: flex;
    height: clamp(31rem, 62vh, 48rem);
    min-height: 28rem;
    flex: 1 1 auto;
    flex-direction: column;
    gap: 0.85rem;
    overflow-y: auto;
    padding: 1.2rem;
    background-image:
      linear-gradient(rgba(0, 240, 255, 0.018) 1px, transparent 1px),
      linear-gradient(90deg, rgba(0, 240, 255, 0.018) 1px, transparent 1px);
    background-size: 32px 32px;
    scrollbar-width: thin;
    scrollbar-color: var(--color-border-strong) transparent;
    outline: none;
  }

  .message {
    width: fit-content;
    max-width: min(86%, 46rem);
    padding: 0.8rem 0.95rem;
    font-size: 0.86rem;
    line-height: 1.58;
    overflow-wrap: anywhere;
  }

  .captain-message {
    display: grid;
    gap: 0.55rem;
    align-self: flex-end;
    color: #dffcff;
    background: color-mix(in oklab, var(--color-cyan) 11%, #050505);
    box-shadow: inset 2px 0 0 var(--color-cyan), inset 0 0 0 1px color-mix(in oklab, var(--color-cyan) 26%, var(--color-border));
    clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px);
  }

  .message-files { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 0.3rem; }
  .message-files code { max-width: 12rem; overflow: hidden; padding: 0.18rem 0.35rem; color: var(--color-cyan); background: #000; font-size: 0.56rem; text-overflow: ellipsis; white-space: nowrap; }

  .assistant-message {
    display: grid;
    gap: 0.45rem;
    align-self: flex-start;
    background: var(--color-elevated);
    box-shadow: inset 2px 0 0 var(--color-magenta), inset 0 0 0 1px var(--color-border-strong);
    clip-path: polygon(8px 0, 100% 0, 100% 100%, 8px 100%, 0 calc(100% - 8px), 0 8px);
  }

  .message-author {
    color: var(--color-magenta);
    font-family: var(--font-mono);
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.06em;
  }

  .conversation-empty {
    display: grid;
    max-width: 25rem;
    place-items: center;
    gap: 0.75rem;
    margin: auto;
    color: var(--color-muted);
    text-align: center;
  }
  .conversation-empty > :global(svg) { color: var(--color-cyan); opacity: 0.7; }
  .conversation-empty p { margin: 0; }

  .turn-status {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    margin: 0;
    color: var(--color-cyan);
    font-family: var(--font-mono);
    font-size: 0.68rem;
  }

  .composer {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: end;
    gap: 0.65rem;
    border-top: 1px solid var(--color-border);
    padding: 0.85rem;
    background: #050505;
  }

  .attachment-tray { display: flex; grid-column: 1 / -1; align-items: center; gap: 0.35rem; overflow-x: auto; padding-bottom: 0.2rem; color: var(--color-muted-2); font-family: var(--font-mono); font-size: 0.55rem; scrollbar-width: thin; }
  .attachment-tray > span { flex: none; color: var(--color-cyan); }
  .attachment-tray button { display: inline-flex; min-width: 0; flex: none; align-items: center; gap: 0.3rem; border: 1px solid color-mix(in oklab, var(--color-cyan) 30%, var(--color-border)); padding: 0.25rem 0.4rem; color: var(--color-fg); background: color-mix(in oklab, var(--color-cyan) 5%, #000); font: inherit; cursor: pointer; }
  .attachment-tray button > :global(svg) { color: var(--color-cyan); }
  .attachment-tray button span { color: var(--color-muted); font-size: 0.75rem; }
  .attachment-tray button:hover { border-color: var(--color-cyan); }
  .attachment-tray button:focus-visible { outline: 2px solid var(--color-cyan); outline-offset: 2px; }

  .composer-input { max-height: 12rem; min-height: 3rem; resize: vertical; line-height: 1.45; }

  .human-challenge {
    display: grid;
    gap: .65rem;
    padding: 1rem 1.1rem;
    background: color-mix(in oklab, #f2cf69 7%, #050505);
    box-shadow: inset 0 0 0 1px color-mix(in oklab, #f2cf69 42%, var(--color-border));
  }
  .human-challenge h3,
  .human-challenge p { margin: 0; }
  .human-challenge small { color: var(--color-muted); overflow-wrap: anywhere; }
  .challenge-options { display: grid; gap: .45rem; }
  .challenge-options label { display: flex; align-items: center; gap: .55rem; }
  .challenge-actions { display: flex; justify-content: flex-end; gap: .6rem; }
  .composer-icon { width: 2.9rem; min-height: 3rem; padding: 0; }
  .composer-action { min-height: 3rem; padding-inline: 1rem; font-size: 0.7rem; }

  @keyframes pulse { 50% { opacity: 0.35; } }

  @media (max-width: 1050px) {
    .chat-workspace { grid-template-columns: 1fr; }
    .control-rail { position: static; grid-template-columns: repeat(2, minmax(0, 1fr)); max-height: none; overflow: visible; }
    .brain-control { grid-row: span 2; }
  }

  @media (max-width: 720px) {
    .control-rail { grid-template-columns: 1fr; }
    .brain-control { grid-row: auto; }
    .conversation-header { grid-template-columns: auto minmax(0, 1fr); }
    .conversation-status { grid-column: 2; justify-self: start; }
    .message { max-width: 94%; }
  }

  @media (max-width: 520px) {
    .chat-page { padding-top: 1.5rem; }
    .page-state { flex-direction: column; }
    .control-heading { grid-template-columns: auto minmax(0, 1fr); }
    .brain-state { grid-column: 2; justify-self: start; text-align: left; }
    .access-actions { grid-template-columns: 1fr; }
    .conversation-thread { height: min(58vh, 36rem); min-height: 24rem; padding: 0.8rem; }
    .composer { grid-template-columns: minmax(0, 1fr) auto; }
    .composer-input { grid-column: 1 / -1; grid-row: 1; }
    .composer-icon { grid-column: 1; justify-self: start; }
    .composer-action { grid-column: 2; }
  }

  @media (forced-colors: active) {
    .chat-hero-icon,
    .control-icon,
    .conversation-avatar,
    .conversation-shell,
    .control-card,
    .message { border: 1px solid CanvasText; }
    .loading-pulse,
    .connection-chip i,
    .conversation-status i,
    .brain-state i { background: CanvasText; }
  }
</style>

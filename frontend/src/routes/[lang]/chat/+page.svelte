<script lang="ts">
  import { onDestroy, onMount, tick } from "svelte";
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import Seo from "$lib/components/Seo.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);

  const SEL_KEY = "shimpz_current_capsule";

  let phase = $state("checking"); // checking | login | none | ready
  let capsules = $state<any[]>([]);
  let selected = $state("");
  let brain = $state<any>(null); // {brain, title, configured, authenticated}
  let crew = $state<any[]>([]);
  let messages = $state<any[]>([]);
  let draft = $state("");
  let busy = $state(false);
  let status = $state(""); // the tool-status ticker while the brain works
  let uploading = $state(false);
  let thread = $state<HTMLElement | null>(null);
  let fileInput = $state<HTMLInputElement | null>(null);

  // markdown renderer — loaded client-side only (marked + DOMPurify), so SSR/prerender never touches
  // the browser build. Until it loads, replies render as safe escaped text.
  let renderMd = $state<(s: string) => string>((s) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c] as string));

  // The live bridge: one WebSocket per open capsule chat — the reply STREAMS in (text events), the
  // brain's mid-turn questions (shimpz-ask) arrive as pushes, tool activity ticks a status line.
  let ws = $state<WebSocket | null>(null);
  let wsReady = $state(false);

  async function refreshBrainStatus() {
    const cid = selected;
    if (!cid) return;
    const current = await fetch(`/api/capsules/${cid}/brain`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    if (current && selected === cid) brain = current;
  }

  function liveBrainMsg() {
    // the brain bubble currently being streamed into (create one if the last isn't it)
    let last = messages[messages.length - 1];
    if (!last || last.role !== "brain" || !last.streaming) {
      last = { role: "brain", text: "", streaming: true };
      messages.push(last);
    }
    return last;
  }

  function finishStreamingBrainMessage() {
    // A pushed question can sit after the live reply, so find the bubble instead of assuming it is last.
    for (let i = messages.length - 1; i >= 0; i--) {
      const message = messages[i];
      if (message?.role === "brain" && message.streaming) {
        message.streaming = false;
        return;
      }
    }
  }

  function chatErrorText(statusCode: unknown, detailValue: unknown) {
    const detail = typeof detailValue === "string" ? detailValue.trim() : "";
    const normalized = detail.toLowerCase();
    if (Number(statusCode) === 409) {
      if (normalized.includes("active chat turn") || normalized.includes("already has an active")) {
        return tr("chat_turn_active", lang);
      }
      if (normalized.includes("not authenticated") || normalized.includes("configure the brain")) {
        return tr("brain_wait", lang);
      }
    }
    return "✗ " + (detail || "error");
  }

  function connectWs() {
    ws?.close();
    wsReady = false;
    if (!selected) return;
    const proto = location.protocol === "https:" ? "wss://" : "ws://";
    const sock = new WebSocket(`${proto}${location.host}/api/capsules/${selected}/ws`);
    sock.onopen = () => (wsReady = true);
    sock.onclose = () => {
      if (ws !== sock) return;
      wsReady = false;
      ws = null;
      if (busy) {
        finishStreamingBrainMessage();
        busy = false;
        status = "";
        messages.push({ role: "system", tone: "error", text: tr("chat_disconnected", lang) });
        scrollDown(true);
      }
    };
    sock.onmessage = (ev) => {
      let m: any = {};
      try {
        m = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (m.type === "text") {
        // the growing answer — each event is the full text so far (mirrors the Telegram relay)
        liveBrainMsg().text = m.text || "";
      } else if (m.type === "tool") {
        status = "▸ " + (m.label || "");
      } else if (m.type === "done") {
        const b = liveBrainMsg();
        b.text = m.reply || b.text || "…";
        b.streaming = false;
        busy = false;
        status = "";
        void refreshBrainStatus();
      } else if (m.type === "stopped") {
        finishStreamingBrainMessage();
        busy = false;
        status = "";
      } else if (m.type === "error") {
        finishStreamingBrainMessage();
        busy = false;
        status = "";
        messages.push({ role: "system", tone: "error", text: chatErrorText(m.status, m.detail ?? m.error) });
      } else if (m.type === "ask") {
        messages.push({ role: "ask", rid: m.rid, text: m.text, options: m.options ?? [], answered: false, custom: "" });
      } else if (m.type === "answered" && m.answered) {
        const card = messages.find((x) => x.role === "ask" && x.rid === m.rid);
        if (card) card.answered = true;
      }
      // a fresh discrete message (a question, an error) may scroll smooth; a streaming delta must not
      scrollDown(m.type === "ask" || m.type === "error");
    };
    ws = sock;
  }

  function stopTurn() {
    if (wsReady && ws) ws.send(JSON.stringify({ type: "stop" }));
  }

  function answerAsk(card: any, answer: string) {
    if (!answer.trim() || card.answered || !wsReady) return;
    ws?.send(JSON.stringify({ type: "answer", rid: card.rid, answer: answer.trim() }));
    messages.push({ role: "captain", text: answer.trim() });
    stick = true;
    scrollDown(true);
  }

  // Brain OAuth configure flow (the admin panel's exact bridge, Captain-facing):
  // idle → starting (poll url) → url (Captain authorizes + pastes code) → checking → done/err
  let oauthPhase = $state("idle");
  let oauthUrl = $state("");
  let oauthCode = $state("");
  let oauthErr = $state("");
  let configureBusy = $state(false);
  let configureErr = $state("");

  async function applyAccountBrain() {
    if (!selected || configureBusy) return;
    configureBusy = true;
    configureErr = "";
    try {
      const r = await fetch(`/api/capsules/${selected}/brain/configure`, { method: "POST" }).catch(() => null);
      const d = await r?.json().catch(() => ({}));
      if (!r?.ok) {
        configureErr = d?.detail ?? d?.error ?? tr("brain_apply_failed", lang);
        return;
      }
      await loadCapsuleContext();
      if (!brain?.configured) configureErr = tr("brain_apply_failed", lang);
    } finally {
      configureBusy = false;
    }
  }

  async function startOauth() {
    oauthPhase = "starting";
    oauthUrl = "";
    oauthCode = "";
    await fetch(`/api/capsules/${selected}/brain/login/start`, { method: "POST" }).catch(() => null);
    for (let i = 0; i < 20 && oauthPhase === "starting"; i++) {
      await new Promise((done) => setTimeout(done, 1500));
      const d = (await fetch(`/api/capsules/${selected}/brain/login/url`).then((r) => (r.ok ? r.json() : {})).catch(() => ({}))) as { url?: string };
      if (d.url) {
        oauthUrl = d.url;
        oauthPhase = "url";
        return;
      }
    }
    if (oauthPhase === "starting") oauthPhase = "err";
  }

  async function submitOauthCode() {
    if (!oauthCode.trim()) return;
    oauthPhase = "checking";
    oauthErr = "";
    const r = await fetch(`/api/capsules/${selected}/brain/login/code`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: oauthCode.trim() }),
    }).catch(() => null);
    const d = await r?.json().catch(() => ({}));
    if (r?.ok && d?.ok) {
      let last: any = {};
      for (let i = 0; i < 10; i++) {
        await new Promise((done) => setTimeout(done, 1200));
        last = await fetch(`/api/capsules/${selected}/brain/login/status`).then((x) => (x.ok ? x.json() : {})).catch(() => ({}));
        if (last.loggedIn) break;
      }
      if (last.loggedIn) {
        oauthPhase = "done";
        await loadCapsuleContext(); // configuration becomes usable; a real successful turn verifies auth
      } else {
        oauthErr = last.last_error ?? ""; // the bridge's own verdict, e.g. "Login failed: …"
        oauthPhase = "err";
      }
    } else {
      oauthErr = d?.error ?? d?.detail ?? "";
      oauthPhase = "err";
    }
  }

  // Auto-follow the stream ONLY when the Captain is already at the bottom — never yank them back up
  // while they're reading history. During a stream we scroll with behavior:auto (smooth would restart
  // its animation every token and jank); discrete new messages may scroll smooth.
  let stick = $state(true);
  const escapeHtml = (s: string) => (s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c] as string);

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

  async function loadCapsuleContext() {
    brain = null;
    crew = [];
    if (!selected) return;
    localStorage.setItem(SEL_KEY, selected);
    const name = capsules.find((c) => c.id === selected)?.name ?? selected;
    localStorage.setItem(SEL_KEY + "_name", name);
    const [b, a] = await Promise.all([
      fetch(`/api/capsules/${selected}/brain`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetch(`/api/capsules/${selected}/apps`).then((r) => (r.ok ? r.json() : { apps: [] })).catch(() => ({ apps: [] })),
    ]);
    brain = b;
    crew = a.apps ?? [];
    connectWs();
  }

  async function boot() {
    const me = await (await fetch("/api/me")).json().catch(() => ({}));
    if (!me.authenticated) {
      phase = "login";
      return;
    }
    const r = await fetch("/api/capsules");
    capsules = r.ok ? ((await r.json()).capsules ?? []) : [];
    if (capsules.length === 0) {
      phase = "none";
      return;
    }
    const stored = localStorage.getItem(SEL_KEY) ?? "";
    selected = capsules.some((c) => c.id === stored) ? stored : capsules[0].id;
    await loadCapsuleContext();
    phase = "ready";
  }

  async function send() {
    const text = draft.trim();
    if (!text || busy || !selected || !brain?.configured) return;
    draft = "";
    busy = true;
    status = tr("chat_thinking", lang);
    messages.push({ role: "captain", text });
    stick = true; // sending re-engages auto-follow
    scrollDown(true);
    if (wsReady && ws) {
      ws.send(JSON.stringify({ type: "chat", message: text })); // reply STREAMS back as pushes
      return;
    }
    // fallback: socket down → the non-streaming POST
    try {
      const r = await fetch(`/api/capsules/${selected}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok) {
        messages.push({ role: "brain", text: d.reply || "…" });
        await refreshBrainStatus();
      } else {
        messages.push({ role: "system", tone: "error", text: chatErrorText(r.status, d.detail ?? d.error) });
      }
    } catch {
      messages.push({ role: "system", tone: "error", text: "✗ network error" });
    } finally {
      busy = false;
      status = "";
      scrollDown(true);
    }
  }

  async function upload(ev: Event) {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (!file || !selected || uploading || !brain?.configured) return;
    uploading = true;
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await fetch(`/api/capsules/${selected}/files`, { method: "POST", body: form });
      const d = await r.json().catch(() => ({}));
      messages.push(
        r.ok
          ? { role: "system", tone: "success", text: `${tr("chat_file_ok", lang)} ${d.path}` }
          : { role: "system", tone: "error", text: "✗ " + (d.error ?? d.detail ?? "upload error") },
      );
    } finally {
      uploading = false;
      if (fileInput) fileInput.value = "";
      stick = true;
      scrollDown(true);
    }
  }

  onMount(async () => {
    // markdown, browser-only: raw brain output is escaped first (marked won't emit HTML from us),
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
  onDestroy(() => ws?.close());
</script>

<Seo title={tr("chat_title", lang)} description={tr("chat_lead", lang)} {lang} />

<section class="wrap pt-10 pb-16">
  <h1 class="text-3xl font-extrabold tracking-tight">{tr("nav_chat", lang)}</h1>
  <p class="mt-2 text-sm dim">{tr("chat_lead", lang)}</p>

  {#if phase === "checking"}
    <p class="mt-8 dim">…</p>
  {:else if phase === "login"}
    <p class="mt-8"><a class="btn-primary" href={u.capsule(lang)}>{tr("chat_login", lang)}</a></p>
  {:else if phase === "none"}
    <p class="mt-8"><a class="btn-primary" href={u.capsule(lang)}>{tr("chat_no_capsule", lang)}</a></p>
  {:else}
    <div class="mt-6 flex flex-col gap-6 lg:flex-row">
      <aside class="order-2 lg:order-none lg:w-64 lg:shrink-0">
        <div class="space-y-4 lg:sticky lg:top-32">
          <div class="panel">
            <span class="kicker">{tr("my_capsules", lang)}</span>
            <select
              class="field field-sm mt-2"
              aria-label={tr("my_capsules", lang)}
              bind:value={selected}
              onchange={() => {
                oauthPhase = "idle";
                configureErr = "";
                loadCapsuleContext();
              }}>
              {#each capsules as c (c.id)}<option value={c.id}>{c.name || c.id}</option>{/each}
            </select>
            {#if brain}
              <p class="mt-3 flex items-center gap-2 text-xs dim">
                <span class="kicker !text-[10px]">{tr("brain_label", lang)}</span>
                <span>{brain.title}</span>
                <span
                  class="ml-auto size-2 rounded-full"
                  style="background:{brain.authenticated ? 'var(--color-primary)' : 'var(--color-magenta)'}"
                  role="img"
                  aria-label={brain.authenticated ? tr("brain_authenticated_verified", lang) : brain.configured ? tr("brain_verification_pending", lang) : tr("brain_not_configured", lang)}
                  title={brain.authenticated ? tr("brain_authenticated_verified", lang) : brain.configured ? tr("brain_verification_pending", lang) : tr("brain_not_configured", lang)}></span>
              </p>
            {/if}
          </div>
          <div class="panel">
            <span class="kicker">{tr("crew_title", lang)}</span>
            <div class="mt-2 space-y-1.5">
              {#each crew as a (a.app)}
                <p class="mono flex items-center gap-2 text-xs"><span style="color:var(--color-primary)">▸</span><span class="truncate">{a.app}</span><span class="ml-auto dim">{a.status}</span></p>
              {/each}
              {#if crew.length === 0}<p class="text-xs dim">{tr("crew_empty", lang)}</p>{/if}
            </div>
          </div>
        </div>
      </aside>

      <div class="order-1 flex min-w-0 flex-1 flex-col lg:order-none">
        {#if brain && !brain.configured}
          <div class="notice notice-error mb-4 space-y-3 px-4 py-3 text-sm">
            <p>{tr("brain_wait", lang)}</p>
            <div class="flex flex-wrap items-center gap-2">
              <a class="btn-primary !py-2 text-sm" href={u.account(lang)}>{tr("brain_account_cta", lang)} →</a>
              <button class="btn-ghost !py-2 text-sm" disabled={configureBusy} onclick={applyAccountBrain}>
                {configureBusy ? "…" : tr("brain_apply", lang)}
              </button>
            </div>
            {#if configureErr}<p class="text-xs" role="alert">{configureErr}</p>{/if}
            {#if brain.brain === "claude-code"}
              <p class="text-xs dim">{tr("brain_interactive_or", lang)}</p>
              {#if oauthPhase === "idle" || oauthPhase === "err"}
                {#if oauthPhase === "err"}
                  <p class="text-xs" role="alert">{tr("brain_code_err", lang)}{#if oauthErr}<span class="mono block mt-1 opacity-80">{oauthErr}</span>{/if}</p>
                {/if}
                <button class="btn-ghost !py-2 text-sm" onclick={startOauth}>{tr("brain_configure", lang)}</button>
              {:else if oauthPhase === "starting"}
                <p class="text-xs dim">{tr("brain_starting", lang)}</p>
              {:else if oauthPhase === "url"}
                <div class="flex flex-wrap items-center gap-2">
                  <a class="btn-primary !py-2 text-sm" href={oauthUrl} target="_blank" rel="noopener">{tr("brain_open_url", lang)} ↗</a>
                  <input class="field field-sm min-w-48 flex-1" placeholder={tr("brain_paste_code", lang)} bind:value={oauthCode} onkeydown={(e) => e.key === "Enter" && submitOauthCode()} />
                  <button class="btn-ghost !py-2 text-sm" disabled={!oauthCode.trim()} onclick={submitOauthCode}>{tr("brain_submit_code", lang)}</button>
                </div>
              {:else if oauthPhase === "checking"}
                <p class="text-xs dim">…</p>
              {/if}
            {/if}
          </div>
        {/if}
        {#if brain?.configured && !brain.authenticated}
          <div class="notice mb-4 px-4 py-3 text-sm dim">
            {tr("brain_verification_pending", lang)}
          </div>
        {/if}
        {#if oauthPhase === "done" && brain?.authenticated}
          <div class="notice notice-success mb-4 px-4 py-3 text-sm" role="status">
            {tr("brain_ok", lang)}
          </div>
        {/if}
        <div
          bind:this={thread}
          onscroll={onThreadScroll}
          role="log"
          aria-live="polite"
          aria-label={tr("chat_thread_label", lang)}
          aria-busy={busy}
          tabindex="-1"
          class="panel h-[52vh] space-y-3 overflow-y-auto">
          {#each messages as m, i (i)}
            {#if m.role === "captain"}
              <div class="bubble ml-auto max-w-[85%] px-4 py-2.5 text-sm" style="background:color-mix(in oklab, var(--color-primary) 16%, var(--color-elevated))">{m.text}</div>
            {:else if m.role === "brain"}
              <div class="md bubble-in max-w-[85%] bg-[var(--color-elevated)] px-4 py-2.5 text-sm" class:caret={m.streaming} class:whitespace-pre-wrap={m.streaming}>{@html m.streaming ? escapeHtml(m.text) : renderMd(m.text || "")}</div>
            {:else if m.role === "ask"}
              <div class="bubble-in max-w-[85%] space-y-2 px-4 py-3 text-sm" style="box-shadow:inset 0 0 0 1px color-mix(in oklab, var(--color-primary) 45%, var(--color-border));background:var(--color-elevated)" class:opacity-60={m.answered}>
                <p class="whitespace-pre-wrap"><span style="color:var(--color-primary)">?</span> {m.text}</p>
                {#if !m.answered}
                  <div class="flex flex-wrap gap-2">
                    {#each m.options as opt, oi (oi)}
                      <button class="btn-ghost min-h-11 !px-3 !py-1.5 text-xs" onclick={() => answerAsk(m, opt)}>
                        {#if oi === 0}
                          <svg class="size-3.5 shrink-0" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="miter">
                            <path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3Z" />
                          </svg>
                        {/if}
                        {opt}
                      </button>
                    {/each}
                  </div>
                  <div class="flex gap-2">
                    <input class="field field-sm min-h-11 min-w-0 flex-1 !text-xs" placeholder={tr("ask_custom", lang)} bind:value={m.custom} onkeydown={(e) => e.key === "Enter" && answerAsk(m, m.custom)} />
                    <button class="btn-ghost min-h-11 !px-3 !py-1.5 text-xs" disabled={!m.custom?.trim()} onclick={() => answerAsk(m, m.custom)}>{tr("chat_send", lang)}</button>
                  </div>
                {:else}
                  <p class="text-xs dim">{tr("ask_answered", lang)}</p>
                {/if}
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
          {#if busy && status}<p class="text-xs dim">{status}</p>{/if}
          {#if messages.length === 0 && !busy}<p class="text-sm dim">{tr("chat_empty", lang)}</p>{/if}
        </div>
        <div class="mt-3 flex items-end gap-2">
          <input bind:this={fileInput} type="file" class="hidden" onchange={upload} />
          <button class="btn-ghost min-h-11 min-w-11 !px-3" title={tr("chat_attach", lang)} aria-label={tr("chat_attach", lang)} disabled={uploading || !brain?.configured} onclick={() => fileInput?.click()}>
            {#if uploading}
              …
            {:else}
              <svg class="size-4" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="square" stroke-linejoin="miter">
                <path d="m8 12.5 6.7-6.7a3.2 3.2 0 0 1 4.5 4.5l-8.5 8.5a5 5 0 0 1-7.1-7.1l8-8" />
              </svg>
            {/if}
          </button>
          <textarea
            class="field field-area max-h-40 flex-1"
            placeholder={tr("chat_placeholder", lang)}
            aria-label={tr("chat_placeholder", lang)}
            disabled={!brain?.configured}
            bind:value={draft}
            onkeydown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), send())}></textarea>
          {#if busy}
            <button class="btn-danger !px-4" onclick={stopTurn}>■ {tr("chat_stop", lang)}</button>
          {:else}
            <button class="btn-primary" disabled={!draft.trim() || !brain?.configured} onclick={send}>{tr("chat_send", lang)}</button>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</section>

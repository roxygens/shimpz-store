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
  let brain = $state<any>(null); // {brain, title, authenticated}
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

  function liveBrainMsg() {
    // the brain bubble currently being streamed into (create one if the last isn't it)
    let last = messages[messages.length - 1];
    if (!last || last.role !== "brain" || !last.streaming) {
      last = { role: "brain", text: "", streaming: true };
      messages.push(last);
    }
    return last;
  }

  function connectWs() {
    ws?.close();
    wsReady = false;
    if (!selected) return;
    const proto = location.protocol === "https:" ? "wss://" : "ws://";
    const sock = new WebSocket(`${proto}${location.host}/api/capsules/${selected}/ws`);
    sock.onopen = () => (wsReady = true);
    sock.onclose = () => {
      if (ws === sock) wsReady = false;
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
      } else if (m.type === "stopped") {
        const b = messages[messages.length - 1];
        if (b?.streaming) b.streaming = false;
        busy = false;
        status = "";
      } else if (m.type === "error") {
        busy = false;
        status = "";
        messages.push({ role: "system", text: m.status === 409 ? tr("brain_wait", lang) : "✗ " + (m.error ?? m.detail ?? "error") });
      } else if (m.type === "ask") {
        messages.push({ role: "ask", rid: m.rid, text: m.text, options: m.options ?? [], answered: false, custom: "" });
      } else if (m.type === "answered" && m.answered) {
        const card = messages.find((x) => x.role === "ask" && x.rid === m.rid);
        if (card) card.answered = true;
      }
      scrollDown();
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
    scrollDown();
  }

  // Brain OAuth configure flow (the admin panel's exact bridge, Captain-facing):
  // idle → starting (poll url) → url (Captain authorizes + pastes code) → checking → done/err
  let oauthPhase = $state("idle");
  let oauthUrl = $state("");
  let oauthCode = $state("");
  let oauthErr = $state("");

  async function startOauth() {
    oauthPhase = "starting";
    oauthUrl = "";
    oauthCode = "";
    await fetch(`/api/capsules/${selected}/brain/login/start`, { method: "POST" }).catch(() => null);
    for (let i = 0; i < 20 && oauthPhase === "starting"; i++) {
      await new Promise((done) => setTimeout(done, 1500));
      const d = await fetch(`/api/capsules/${selected}/brain/login/url`).then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
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
        await loadCapsuleContext(); // the banner clears itself — brain.authenticated flips
      } else {
        oauthErr = last.last_error ?? ""; // the bridge's own verdict, e.g. "Login failed: …"
        oauthPhase = "err";
      }
    } else {
      oauthErr = d?.error ?? d?.detail ?? "";
      oauthPhase = "err";
    }
  }

  async function scrollDown() {
    await tick();
    thread?.scrollTo({ top: thread.scrollHeight, behavior: "smooth" });
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
    if (!text || busy || !selected) return;
    draft = "";
    busy = true;
    status = tr("chat_thinking", lang);
    messages.push({ role: "captain", text });
    scrollDown();
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
      if (r.ok) messages.push({ role: "brain", text: d.reply || "…" });
      else if (r.status === 409) messages.push({ role: "system", text: tr("brain_wait", lang) });
      else messages.push({ role: "system", text: "✗ " + (d.error ?? d.detail ?? "error") });
    } catch {
      messages.push({ role: "system", text: "✗ network error" });
    } finally {
      busy = false;
      status = "";
      scrollDown();
    }
  }

  async function upload(ev: Event) {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (!file || !selected || uploading) return;
    uploading = true;
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await fetch(`/api/capsules/${selected}/files`, { method: "POST", body: form });
      const d = await r.json().catch(() => ({}));
      messages.push(
        r.ok
          ? { role: "system", text: `${tr("chat_file_ok", lang)} ${d.path}` }
          : { role: "system", text: "✗ " + (d.error ?? d.detail ?? "upload error") },
      );
    } finally {
      uploading = false;
      if (fileInput) fileInput.value = "";
      scrollDown();
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
      <aside class="lg:w-64 lg:shrink-0">
        <div class="space-y-4 lg:sticky lg:top-24">
          <div class="panel">
            <span class="kicker">{tr("my_capsules", lang)}</span>
            <select
              class="field field-sm mt-2"
              bind:value={selected}
              onchange={() => {
                oauthPhase = "idle";
                loadCapsuleContext();
              }}>
              {#each capsules as c (c.id)}<option value={c.id}>{c.name || c.id}</option>{/each}
            </select>
            {#if brain}
              <p class="mt-3 flex items-center gap-2 text-xs dim">
                <span class="kicker !text-[10px]">{tr("brain_label", lang)}</span>
                <span>{brain.title}</span>
                <span class="ml-auto size-2 rounded-full" style="background:{brain.authenticated ? 'var(--color-primary)' : 'var(--color-magenta)'}"></span>
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

      <div class="flex min-w-0 flex-1 flex-col">
        {#if brain && !brain.authenticated}
          <div class="mb-4 space-y-3 rounded-lg border px-4 py-3 text-sm" style="border-color:color-mix(in oklab, var(--color-magenta) 40%, var(--color-border))">
            <p style="color:var(--color-magenta)">{tr("brain_wait", lang)}</p>
            {#if oauthPhase === "idle" || oauthPhase === "err"}
              {#if oauthPhase === "err"}
                <p class="text-xs" style="color:var(--color-magenta)">{tr("brain_code_err", lang)}{#if oauthErr}<span class="mono block mt-1 opacity-80">{oauthErr}</span>{/if}</p>
              {/if}
              <button class="btn-primary !py-2 text-sm" onclick={startOauth}>{tr("brain_configure", lang)}</button>
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
          </div>
        {/if}
        {#if oauthPhase === "done" && brain?.authenticated}
          <div class="mb-4 rounded-lg border px-4 py-3 text-sm" style="border-color:color-mix(in oklab, var(--color-primary) 40%, var(--color-border));color:var(--color-primary)">
            {tr("brain_ok", lang)}
          </div>
        {/if}
        <div bind:this={thread} class="panel h-[52vh] space-y-3 overflow-y-auto">
          {#each messages as m, i (i)}
            {#if m.role === "captain"}
              <div class="ml-auto max-w-[85%] rounded-xl px-4 py-2.5 text-sm" style="background:color-mix(in oklab, var(--color-primary) 16%, var(--color-elevated))">{m.text}</div>
            {:else if m.role === "brain"}
              <div class="md max-w-[85%] rounded-xl bg-[var(--color-elevated)] px-4 py-2.5 text-sm" class:caret={m.streaming}>{@html renderMd(m.text || "")}</div>
            {:else if m.role === "ask"}
              <div class="max-w-[85%] space-y-2 rounded-xl border px-4 py-3 text-sm" style="border-color:color-mix(in oklab, var(--color-primary) 45%, var(--color-border));background:var(--color-elevated)" class:opacity-60={m.answered}>
                <p class="whitespace-pre-wrap"><span style="color:var(--color-primary)">?</span> {m.text}</p>
                {#if !m.answered}
                  <div class="flex flex-wrap gap-2">
                    {#each m.options as opt, oi (oi)}
                      <button class="btn-ghost !px-3 !py-1.5 text-xs" onclick={() => answerAsk(m, opt)}>{oi === 0 ? "⭐ " : ""}{opt}</button>
                    {/each}
                  </div>
                  <div class="flex gap-2">
                    <input class="field field-sm min-w-0 flex-1 !text-xs" placeholder={tr("ask_custom", lang)} bind:value={m.custom} onkeydown={(e) => e.key === "Enter" && answerAsk(m, m.custom)} />
                    <button class="btn-ghost !px-3 !py-1.5 text-xs" disabled={!m.custom?.trim()} onclick={() => answerAsk(m, m.custom)}>{tr("chat_send", lang)}</button>
                  </div>
                {:else}
                  <p class="text-xs dim">{tr("ask_answered", lang)}</p>
                {/if}
              </div>
            {:else}
              <p class="text-center text-xs dim">{m.text}</p>
            {/if}
          {/each}
          {#if busy && status}<p class="text-xs dim">{status}</p>{/if}
          {#if messages.length === 0 && !busy}<p class="text-sm dim">{tr("chat_empty", lang)}</p>{/if}
        </div>
        <div class="mt-3 flex items-end gap-2">
          <input bind:this={fileInput} type="file" class="hidden" onchange={upload} />
          <button class="btn-ghost !px-3" title={tr("chat_attach", lang)} disabled={uploading} onclick={() => fileInput?.click()}>{uploading ? "…" : "📎"}</button>
          <textarea
            class="field field-area max-h-40 flex-1"
            placeholder={tr("chat_placeholder", lang)}
            bind:value={draft}
            onkeydown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), send())}></textarea>
          {#if busy}
            <button class="btn-ghost !px-4" style="color:var(--color-magenta);box-shadow:inset 0 0 0 1px color-mix(in oklab, var(--color-magenta) 55%, transparent)" onclick={stopTurn}>■ {tr("chat_stop", lang)}</button>
          {:else}
            <button class="btn-primary" disabled={!draft.trim()} onclick={send}>{tr("chat_send", lang)}</button>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</section>

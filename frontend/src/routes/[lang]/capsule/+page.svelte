<script lang="ts">
  import { onMount } from "svelte";
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import Seo from "$lib/components/Seo.svelte";
  import Breadcrumbs from "$lib/components/Breadcrumbs.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);

  let phase = $state("checking"); // checking | auth | ready
  let mode = $state("login"); // login | signup
  let username = $state("");
  let password = $state("");
  let capName = $state("");
  let brain = $state("claude-code");
  let capsules = $state<any[]>([]);
  let selected = $state("");
  let apps = $state<any[]>([]);
  let error = $state("");
  let busy = $state(false);

  const SEL_KEY = "shimpz_current_capsule";

  async function refreshApps() {
    if (!selected) {
      apps = [];
      return;
    }
    const r = await fetch(`/api/capsules/${selected}/apps`);
    apps = r.ok ? ((await r.json()).apps ?? []) : [];
  }

  async function refresh() {
    const r = await fetch("/api/capsules");
    if (r.ok) {
      capsules = (await r.json()).capsules ?? [];
      if (!selected && capsules[0]) select(capsules[0].id); // persist too — the app page reads it
    }
    await refreshApps();
  }

  async function uninstallApp(appId: string) {
    if (!selected || busy) return;
    busy = true;
    try {
      await fetch(`/api/capsules/${selected}/apps/${appId}`, { method: "DELETE" });
      await refreshApps();
    } finally {
      busy = false;
    }
  }

  async function boot() {
    try {
      const me = await (await fetch("/api/me")).json();
      if (me.authenticated) {
        selected = localStorage.getItem(SEL_KEY) ?? "";
        await refresh();
        phase = "ready";
      } else {
        phase = "auth";
      }
    } catch {
      phase = "auth";
    }
  }

  async function submitAuth() {
    if (!username.trim() || !password || busy) return;
    busy = true;
    error = "";
    try {
      const r = await fetch(mode === "signup" ? "/api/signup" : "/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      if (r.ok) {
        password = "";
        await refresh();
        phase = "ready";
      } else {
        const body = await r.json().catch(() => ({}));
        error = body.detail ?? body.error ?? "failed";
      }
    } catch (e) {
      error = String(e);
    } finally {
      busy = false;
    }
  }

  async function logout() {
    await fetch("/api/logout", { method: "POST" });
    capsules = [];
    selected = "";
    phase = "auth";
  }

  async function createCapsule() {
    if (!capName.trim() || busy) return;
    busy = true;
    error = "";
    try {
      const r = await fetch("/api/capsules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: capName.trim(), brain }),
      });
      if (r.ok) {
        capName = "";
        await refresh();
      } else {
        error = (await r.json().catch(() => ({}))).detail ?? "create failed";
      }
    } catch (e) {
      error = String(e);
    } finally {
      busy = false;
    }
  }

  async function destroyCapsule(id: string) {
    if (!confirm(`Destroy Capsule "${id}"? This permanently wipes its data, database and network.`)) return;
    busy = true;
    error = "";
    try {
      await fetch(`/api/capsules/${id}`, { method: "DELETE" });
      if (selected === id) select("");
      await refresh();
    } finally {
      busy = false;
    }
  }

  function select(id: string) {
    selected = id;
    if (id) {
      localStorage.setItem(SEL_KEY, id);
      const name = capsules.find((c) => c.id === id)?.name ?? id;
      localStorage.setItem(SEL_KEY + "_name", name); // the app page shows WHERE Install will land
    } else {
      localStorage.removeItem(SEL_KEY);
      localStorage.removeItem(SEL_KEY + "_name");
    }
    refreshApps();
  }

  onMount(boot);
</script>

<Seo title={tr("capsule_title", lang)} description={tr("capsule_lead", lang)} {lang} />

<section class="wrap pt-10 pb-8">
  <Breadcrumbs items={[{ label: tr("home", lang), href: u.home(lang) }, { label: tr("create_capsule", lang) }]} />
  <h1 class="mt-6 max-w-3xl text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
    {phase === "ready" ? tr("my_capsules", lang) : tr("create_capsule", lang)}
  </h1>

  {#if phase === "checking"}
    <p class="mt-6 dim">…</p>
  {:else if phase === "auth"}
    <p class="mt-5 max-w-2xl text-lg leading-relaxed dim">{tr("capsule_lead", lang)}</p>
    <div class="panel mt-8 max-w-md space-y-4">
      <div class="flex gap-2 text-sm">
        <button class:btn-primary={mode === "login"} class:btn-ghost={mode !== "login"} onclick={() => (mode = "login")}>{tr("log_in", lang)}</button>
        <button class:btn-primary={mode === "signup"} class:btn-ghost={mode !== "signup"} onclick={() => (mode = "signup")}>{tr("sign_up", lang)}</button>
      </div>
      <input class="field" placeholder={tr("username", lang)} bind:value={username} />
      <input class="field" type="password" placeholder={tr("password", lang)} bind:value={password} onkeydown={(e) => e.key === "Enter" && submitAuth()} />
      <button class="btn-primary w-full justify-center" disabled={busy} onclick={submitAuth}>{mode === "signup" ? tr("sign_up", lang) : tr("log_in", lang)}</button>
      {#if error}<p class="text-sm" style="color:var(--color-magenta)">{error}</p>{/if}
    </div>
  {:else}
    <div class="mt-4 flex items-center gap-4 text-sm dim">
      <span>{capsules.length} {tr("my_capsules", lang)}</span>
      <button class="transition hover:text-[var(--color-fg)]" onclick={logout}>{tr("log_out", lang)} →</button>
    </div>

    <div class="panel mt-6 max-w-xl space-y-3">
      <span class="kicker">{tr("capsule_name_label", lang)}</span>
      <div class="flex gap-2">
        <input class="field flex-1" placeholder={tr("capsule_name_ph", lang)} bind:value={capName} onkeydown={(e) => e.key === "Enter" && createCapsule()} />
        <button class="btn-primary" disabled={busy || !capName.trim()} onclick={createCapsule}>{tr("capsule_submit", lang)}</button>
      </div>
      <label class="flex items-center gap-3 text-sm dim">
        <span class="kicker !text-[10px]">{tr("brain_label", lang)}</span>
        <select class="field field-sm w-auto" bind:value={brain}>
          <option value="claude-code">Claude Code</option>
        </select>
      </label>
    </div>
    {#if error}<p class="mt-3 text-sm" style="color:var(--color-magenta)">{error}</p>{/if}

    <div class="mt-6 space-y-3">
      {#each capsules as c (c.id)}
        <div class="card flex w-full items-center gap-4" class:ring={selected === c.id}>
          <button class="flex min-w-0 flex-1 items-center gap-4 text-left" onclick={() => select(c.id)}>
            <span class="app-icon grid place-items-center" style="--g1:#00f0ff;--g2:#ff2a6d;width:34px;height:34px;font-size:16px">◆</span>
            <span class="min-w-0 flex-1">
              <span class="block font-semibold">{c.name || c.id}</span>
              <span class="mono block truncate text-xs dim">{c.id} · {c.status} · {tr("brain_label", lang)}: {c.brain ?? "claude-code"}</span>
            </span>
            {#if selected === c.id}<span class="badge">{tr("current", lang)}</span>{/if}
          </button>
          <a class="btn-ghost !px-3 !py-1 text-xs" href={u.chat(lang)} onclick={() => select(c.id)}>{tr("nav_chat", lang)}</a>
          <button class="btn-ghost !px-3 !py-1 text-xs" onclick={() => destroyCapsule(c.id)}>{tr("destroy", lang)}</button>
        </div>
      {/each}
      {#if capsules.length === 0}<p class="dim">{tr("no_capsules", lang)}</p>{/if}
    </div>

    {#if selected}
      <div class="panel mt-8 max-w-xl">
        <span class="kicker">{tr("installed_apps", lang)}</span>
        <div class="mt-3 space-y-2">
          {#each apps as a (a.app)}
            <div class="flex items-center gap-3 text-sm">
              <span class="mono min-w-0 flex-1 truncate">{a.app}</span>
              <span class="badge">{a.status}</span>
              <button class="btn-ghost !px-3 !py-1 text-xs" disabled={busy} onclick={() => uninstallApp(a.app)}>{tr("uninstall", lang)}</button>
            </div>
          {/each}
          {#if apps.length === 0}<p class="text-sm dim">{tr("no_apps", lang)}</p>{/if}
        </div>
      </div>
    {/if}
  {/if}
</section>

<style>
  .ring {
    box-shadow: 0 0 0 1px var(--color-primary);
  }
</style>

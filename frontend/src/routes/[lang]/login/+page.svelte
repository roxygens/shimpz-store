<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import type { Locale } from "$lib/catalog";
  import { tr } from "$lib/i18n";
  import { u } from "$lib/url";
  import Seo from "$lib/components/Seo.svelte";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);

  let mode = $state<"login" | "signup">("login");
  let username = $state("");
  let password = $state("");
  let showPw = $state(false);
  let busy = $state(false);
  let error = $state("");

  onMount(async () => {
    const me = await fetch("/api/me").then((r) => r.json()).catch(() => ({}));
    if (me.authenticated) goto(u.capsule(lang)); // already signed in → My Capsules
  });

  function switchMode(m: "login" | "signup") {
    mode = m;
    error = "";
  }

  async function submit() {
    if (!username.trim() || !password || busy) return;
    busy = true;
    error = "";
    try {
      const body: Record<string, string> = { username: username.trim(), password };
      const r = await fetch(mode === "signup" ? "/api/signup" : "/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (r.ok) {
        goto(u.capsule(lang));
      } else {
        const d = await r.json().catch(() => ({}));
        error = d.detail ?? d.error ?? "failed";
      }
    } catch (e) {
      error = String(e);
    } finally {
      busy = false;
    }
  }
</script>

<Seo title={`${tr(mode === "signup" ? "signup_welcome" : "login_welcome", lang)} · Shimpz`} description={tr("login_lead", lang)} {lang} />

<section class="wrap flex min-h-[calc(100dvh-15rem)] items-center justify-center py-12">
  <div class="w-full max-w-sm">
    <div class="mb-6 text-center">
      <div class="app-icon mx-auto mb-4 grid size-12 place-items-center" style="--g1:var(--color-cyan);--g2:var(--color-magenta);font-size:22px">◆</div>
      <h1 class="mono text-2xl font-extrabold tracking-tight">{tr(mode === "signup" ? "signup_welcome" : "login_welcome", lang)}</h1>
      <p class="mt-2 text-sm leading-relaxed dim">{tr(mode === "signup" ? "signup_lead" : "login_lead", lang)}</p>
    </div>

    <div class="panel space-y-4">
      <div class="grid grid-cols-2 gap-1 rounded-lg p-1" style="box-shadow:inset 0 0 0 1px var(--color-border)">
        <button class="rounded-md py-1.5 text-sm font-semibold transition" style={mode === "login" ? "background:var(--color-elevated);color:var(--color-fg)" : "color:var(--color-muted)"} onclick={() => switchMode("login")}>{tr("log_in", lang)}</button>
        <button class="rounded-md py-1.5 text-sm font-semibold transition" style={mode === "signup" ? "background:var(--color-elevated);color:var(--color-fg)" : "color:var(--color-muted)"} onclick={() => switchMode("signup")}>{tr("sign_up", lang)}</button>
      </div>

      <label class="block">
        <span class="kicker !text-[10px]">{tr("username", lang)}</span>
        <input class="field mt-1.5" autocomplete="username" bind:value={username} onkeydown={(e) => e.key === "Enter" && submit()} />
      </label>

      <label class="block">
        <span class="kicker !text-[10px]">{tr("password", lang)}</span>
        <div class="relative mt-1.5">
          {#if showPw}
            <input class="field !pr-16" type="text" autocomplete={mode === "signup" ? "new-password" : "current-password"} bind:value={password} onkeydown={(e) => e.key === "Enter" && submit()} />
          {:else}
            <input class="field !pr-16" type="password" autocomplete={mode === "signup" ? "new-password" : "current-password"} bind:value={password} onkeydown={(e) => e.key === "Enter" && submit()} />
          {/if}
          <button type="button" class="absolute right-3 top-1/2 -translate-y-1/2 text-xs uppercase tracking-wide dim transition hover:text-[var(--color-fg)]" onclick={() => (showPw = !showPw)}>{showPw ? tr("password_hide", lang) : tr("password_show", lang)}</button>
        </div>
      </label>

      {#if error}<p class="text-sm" style="color:var(--color-magenta)">{error}</p>{/if}

      <button class="btn-primary w-full justify-center" disabled={busy || !username.trim() || !password} onclick={submit}>
        {busy ? "…" : tr(mode === "signup" ? "sign_up" : "log_in", lang)}
      </button>
    </div>

    <p class="mt-5 text-center text-sm dim">
      <button class="underline decoration-dotted underline-offset-2 transition hover:text-[var(--color-fg)]" onclick={() => switchMode(mode === "login" ? "signup" : "login")}>
        {tr(mode === "login" ? "to_signup" : "to_login", lang)}
      </button>
    </p>
  </div>
</section>

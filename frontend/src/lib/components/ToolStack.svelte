<script lang="ts">
  import type { Locale } from "$lib/catalog";

  let { lang }: { lang: Locale } = $props();

  const copy = $derived(lang === "pt" ? {
    kicker: "Um Time no lugar de uma pilha",
    title: "Menos ferramentas. Mais trabalho concluído.",
    body: "Lovable cria interfaces. n8n, Make e Zapier conectam fluxos. Supabase cuida da base. Eu reúno essas partes em um Time que entende o pedido, escolhe os Assistants e entrega o resultado.",
    note: "Não sou uma cópia dessas ferramentas nem prometo substituir cada recurso isolado. Substituo a necessidade de você montar e coordenar essa pilha para delegar um resultado.",
    result: "Meu Time executa",
    resultDetail: "Um pedido. Um resultado.",
    trademark: "Lovable, n8n, Make, Supabase e Zapier são marcas de seus respectivos proprietários. Comparação de categoria; sem afiliação.",
    tools: [
      ["Lovable", "Criar", "/brand/competitors/lovable.svg"],
      ["n8n", "Automatizar", "/brand/competitors/n8n.svg"],
      ["Make", "Orquestrar", "/brand/competitors/make.svg"],
      ["Supabase", "Dados", "/brand/competitors/supabase.svg"],
      ["Zapier", "Conectar", "/brand/competitors/zapier.svg"],
    ],
  } : {
    kicker: "One Team instead of a tool stack",
    title: "Fewer tools. More finished work.",
    body: "Lovable builds interfaces. n8n, Make, and Zapier connect workflows. Supabase handles the backend. I bring those parts together in a Team that understands the request, chooses the Assistants, and delivers the result.",
    note: "I am not a copy of these tools and do not claim feature-for-feature parity. I replace the need for you to assemble and coordinate the stack when you want to delegate an outcome.",
    result: "My Team executes",
    resultDetail: "One request. One result.",
    trademark: "Lovable, n8n, Make, Supabase, and Zapier are trademarks of their respective owners. Category comparison; no affiliation.",
    tools: [
      ["Lovable", "Build", "/brand/competitors/lovable.svg"],
      ["n8n", "Automate", "/brand/competitors/n8n.svg"],
      ["Make", "Orchestrate", "/brand/competitors/make.svg"],
      ["Supabase", "Data", "/brand/competitors/supabase.svg"],
      ["Zapier", "Connect", "/brand/competitors/zapier.svg"],
    ],
  });
</script>

<div class="stack-copy">
  <p class="kicker">{copy.kicker}</p>
  <h2>{copy.title}</h2>
  <p class="body">{copy.body}</p>
  <p class="note">{copy.note}</p>
</div>

<div class="stack-map" aria-label={copy.title}>
  <ul class="tool-list">
    {#each copy.tools as tool (tool[0])}
      <li>
        <span class="logo"><img src={tool[2]} alt="" width="28" height="28" /></span>
        <span><strong>{tool[0]}</strong><small>{tool[1]}</small></span>
        <i aria-hidden="true">→</i>
      </li>
    {/each}
  </ul>
  <div class="team-result">
    <span class="brain" aria-hidden="true">S</span>
    <span><strong>Shimpz</strong><small>{copy.result}</small></span>
    <b>{copy.resultDetail}</b>
  </div>
</div>

<p class="trademark">{copy.trademark}</p>

<style>
  .stack-copy { max-width: 54rem; }
  .kicker {
    margin: 0 0 1rem;
    color: var(--color-cyan);
    font-family: var(--font-mono);
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  h2 { margin: 0; font-size: clamp(2.25rem, 5vw, 4.8rem); line-height: 1; letter-spacing: -0.065em; }
  .body { max-width: 51rem; margin: 1.4rem 0 0; color: #d4d4d8; font-size: clamp(1rem, 1.4vw, 1.12rem); line-height: 1.7; }
  .note { max-width: 49rem; margin: 0.75rem 0 0; color: var(--color-muted); font-size: 0.85rem; line-height: 1.6; }
  .stack-map { display: grid; grid-template-columns: minmax(0, 1fr) minmax(15rem, 0.55fr); gap: clamp(1rem, 4vw, 3rem); align-items: stretch; margin-top: 2.5rem; }
  .tool-list { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); margin: 0; padding: 0; gap: 0.55rem; list-style: none; }
  .tool-list li {
    position: relative;
    display: grid;
    min-width: 0;
    grid-template-columns: 2.4rem minmax(0, 1fr);
    align-items: center;
    gap: 0.65rem;
    padding: 0.85rem;
    background: #080808;
    box-shadow: inset 0 0 0 1px var(--color-border);
    clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px);
  }
  .tool-list li::after { position: absolute; inset: 0 auto 0 0; width: 2px; background: var(--tool-color, var(--color-cyan)); content: ""; opacity: 0.8; }
  .tool-list li:nth-child(2) { --tool-color: #ea4b71; }
  .tool-list li:nth-child(3) { --tool-color: #8d45dd; }
  .tool-list li:nth-child(4) { --tool-color: #3fcf8e; }
  .tool-list li:nth-child(5) { --tool-color: #ff4f00; }
  .logo { display: grid; width: 2.35rem; height: 2.35rem; place-items: center; background: #fff; clip-path: polygon(6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%, 0 6px); }
  .logo img { width: 1.6rem; height: 1.6rem; object-fit: contain; }
  .tool-list strong, .tool-list small, .team-result strong, .team-result small { display: block; }
  .tool-list strong { overflow: hidden; font-size: 0.78rem; text-overflow: ellipsis; }
  .tool-list small { margin-top: 0.16rem; color: var(--color-muted-2); font-family: var(--font-mono); font-size: 0.55rem; text-transform: uppercase; }
  .tool-list i { display: none; }
  .team-result {
    position: relative;
    display: grid;
    grid-template-columns: 3rem 1fr;
    align-content: center;
    gap: 0.8rem;
    padding: 1.2rem;
    background: linear-gradient(145deg, rgba(0, 240, 255, 0.1), rgba(255, 45, 255, 0.05) 70%), #050505;
    box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--color-cyan) 55%, var(--color-border));
    clip-path: polygon(12px 0, 100% 0, 100% calc(100% - 12px), calc(100% - 12px) 100%, 0 100%, 0 12px);
  }
  .team-result::before { position: absolute; top: 50%; left: calc(clamp(1rem, 4vw, 3rem) * -1); width: clamp(1rem, 4vw, 3rem); height: 1px; background: linear-gradient(90deg, var(--color-border), var(--color-cyan)); content: ""; }
  .brain { display: grid; width: 3rem; height: 3rem; place-items: center; background: linear-gradient(135deg, var(--color-cyan), var(--color-magenta)); color: #02060a; font-family: var(--font-mono); font-weight: 800; clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px); }
  .team-result strong { font-family: var(--font-mono); font-size: 1rem; }
  .team-result small { margin-top: 0.2rem; color: var(--color-cyan); font-family: var(--font-mono); font-size: 0.62rem; text-transform: uppercase; }
  .team-result b { grid-column: 1 / -1; padding-top: 0.85rem; border-top: 1px solid var(--color-border); color: var(--color-green); font-size: 0.82rem; }
  .trademark { margin: 1rem 0 0; color: var(--color-muted-2); font-size: 0.62rem; line-height: 1.5; }
  @media (max-width: 960px) {
    .stack-map { grid-template-columns: 1fr; }
    .tool-list { grid-template-columns: repeat(5, minmax(8rem, 1fr)); overflow-x: auto; padding-bottom: 0.4rem; }
    .team-result::before { display: none; }
  }
  @media (max-width: 560px) {
    .tool-list { grid-template-columns: 1fr; overflow: visible; }
    .tool-list li { grid-template-columns: 2.4rem 1fr auto; }
    .tool-list i { display: block; color: var(--color-cyan); font-style: normal; }
  }
</style>

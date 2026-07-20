<script lang="ts">
  import type { Locale } from "$lib/catalog";
  import HomeHeader from "$lib/components/HomeHeader.svelte";
  import Seo from "$lib/components/Seo.svelte";
  import ToolStack from "$lib/components/ToolStack.svelte";
  import { u } from "$lib/url";

  let { data } = $props();
  const lang = $derived(data.lang as Locale);

  const content = $derived(lang === "pt" ? {
    seoTitle: "Shimpz — Você me diz o que precisa. Meu Time faz o trabalho.",
    seoDescription: "Crie sua conta, escolha Assistants especializados e deixe o Shimpz organizar o trabalho para você.",
    eyebrow: "Seu Time digital, pronto para trabalhar",
    title: "Olá, eu sou o Shimpz.",
    promise: "Você me diz o que precisa. Meu Time faz o trabalho.",
    description: "Sou formado por aplicativos especializados, que chamamos de Assistants. Meu cérebro entende seu pedido, escolhe os Assistants certos e coloca todos para trabalhar juntos.",
    support: "Você não precisa abrir várias ferramentas ou organizar cada etapa. Basta me dizer o resultado que deseja.",
    primaryCta: "Começar agora",
    secondaryCta: "Veja como eu trabalho",
    microcopy: "Crie sua conta Shimpz e comece em poucos passos.",
    liveExample: "Uma tarefa, um Time",
    task: "Analise os resultados e prepare um resumo para mim.",
    brain: "Entendi o resultado",
    assistantOne: "Assistant pesquisa",
    assistantTwo: "Assistant analisa",
    complete: "Resumo pronto",
    demoKicker: "Demonstração prática",
    demoTitle: "Um pedido. Vários Assistants trabalhando juntos.",
    user: "Você",
    userMessage: "Veja como estão meus anúncios e envie um resumo no WhatsApp.",
    shimpzMessageOne: "Entendi. Vou combinar meus Assistants de anúncios, gestão e WhatsApp.",
    shimpzMessageTwo: "Um busca os resultados, outro analisa e outro envia o resumo para você.",
    flow: ["Seu pedido", "Eu escolho os Assistants", "Meu Time executa", "Você recebe o resultado"],
    howKicker: "Como funciona",
    howTitle: "Comece com um pedido.",
    steps: [
      ["1. Entre", "Crie ou acesse sua conta Shimpz para começar."],
      ["2. Escolha", "Selecione um Assistant ou um Time para o trabalho que deseja delegar."],
      ["3. Peça", "Explique o resultado que deseja e acompanhe meu Time trabalhando."],
    ],
    assistantsKicker: "Assistants e Times",
    assistantsTitle: "Cada Assistant cuida de uma parte. Meu Time cuida do resultado.",
    assistantsBodyOne: "Um Assistant pode analisar anúncios. Outro pode organizar informações. Outro pode criar documentos ou enviar mensagens.",
    assistantsBodyTwo: "Eu escolho quais Assistants devem trabalhar juntos em cada pedido.",
    availableNow: "Disponível agora",
    assistantName: "Shimpz Assistant",
    assistantResult: "Consulta perfis e a conta conectada no X, publica ou exclui Posts com sua aprovação e gerencia uploads de teste no Mux.",
    assistantSafety: "Acessa somente api.x.com e api.mux.com. Ações importantes pedem aprovação.",
    useAssistant: "Usar este Assistant",
    addAssistant: "Adicionar ao meu Time",
    teamsLabel: "Seu espaço de trabalho",
    teamName: "Meu Time",
    teamResult: "Reúna os Assistants que você escolher e converse com todos em um só lugar.",
    teamReality: "Você cria e nomeia seu próprio Time. Não há Times prontos no catálogo hoje.",
    chooseTeam: "Escolher este Time",
    routinesKicker: "Rotinas",
    routinesTitle: "Peça uma vez. Eu continuo cuidando.",
    routinesBody: "Você poderá pedir para repetir um trabalho nos dias e horários que escolher quando um Assistant oferecer essa rotina.",
    routinesExample: "“Todas as manhãs, analise meus anúncios e envie um resumo no WhatsApp.”",
    routinesStatus: "Ainda não disponível no Assistant público atual.",
    securityKicker: "Segurança",
    securityTitle: "Eu trabalho por você. O controle continua sendo seu.",
    securityPoints: [
      "Você escolhe quais contas conectar.",
      "Cada Assistant recebe somente o acesso necessário.",
      "Ações importantes podem pedir sua confirmação.",
      "Você pode remover acessos e Assistants.",
    ],
    securityClosing: "Meu cérebro coordena o trabalho. Meus aplicativos executam dentro dos limites que você autorizou.",
    approval: "Aprovação necessária",
    approvalAction: "Publicar Post no X",
    approve: "Aprovar",
    reject: "Não autorizar",
    finalTitle: "Qual trabalho você quer tirar da sua lista?",
    finalBody: "Entre na sua conta Shimpz, escolha seus Assistants e me diga o resultado que deseja.",
    finalMicrocopy: "Leva apenas alguns passos para começar.",
  } : {
    seoTitle: "Shimpz — You tell me what you need. My Team gets the work done.",
    seoDescription: "Create your account, choose specialized Assistants, and let Shimpz organize the work for you.",
    eyebrow: "Your digital Team, ready to work",
    title: "Hi, I’m Shimpz.",
    promise: "You tell me what you need. My Team gets the work done.",
    description: "I’m made of specialized apps called Assistants. My brain understands your request, chooses the right Assistants, and puts them to work together.",
    support: "You do not need to open several tools or manage every step. Just tell me the result you want.",
    primaryCta: "Get started",
    secondaryCta: "See how I work",
    microcopy: "Create your Shimpz account and get started in a few steps.",
    liveExample: "One task, one Team",
    task: "Review the results and prepare a summary for me.",
    brain: "Request understood",
    assistantOne: "Assistant researches",
    assistantTwo: "Assistant reviews",
    complete: "Summary ready",
    demoKicker: "Practical demonstration",
    demoTitle: "One request. Several Assistants working together.",
    user: "You",
    userMessage: "Check how my ads are performing and send me a summary on WhatsApp.",
    shimpzMessageOne: "Got it. I’ll combine my advertising, management, and WhatsApp Assistants.",
    shimpzMessageTwo: "One collects the results, another reviews them, and another sends you the summary.",
    flow: ["Your request", "I choose the Assistants", "My Team gets to work", "You receive the result"],
    howKicker: "How it works",
    howTitle: "Start with a request.",
    steps: [
      ["1. Sign in", "Create or access your Shimpz account to get started."],
      ["2. Choose", "Select an Assistant or Team for the work you want to delegate."],
      ["3. Ask", "Explain the result you want and follow my Team as it works."],
    ],
    assistantsKicker: "Assistants and Teams",
    assistantsTitle: "Each Assistant handles a part. My Team handles the result.",
    assistantsBodyOne: "One Assistant can review ads. Another can organize information. Another can create documents or send messages.",
    assistantsBodyTwo: "I choose which Assistants should work together on each request.",
    availableNow: "Available now",
    assistantName: "Shimpz Assistant",
    assistantResult: "Looks up profiles and the connected X account, creates or deletes Posts with your approval, and manages test uploads in Mux.",
    assistantSafety: "It can reach only api.x.com and api.mux.com. Important actions require approval.",
    useAssistant: "Use this Assistant",
    addAssistant: "Add to my Team",
    teamsLabel: "Your workspace",
    teamName: "My Team",
    teamResult: "Bring together the Assistants you choose and talk to all of them in one place.",
    teamReality: "You create and name your own Team. There are no ready-made Teams in the catalog today.",
    chooseTeam: "Choose this Team",
    routinesKicker: "Routines",
    routinesTitle: "Ask once. I keep taking care of it.",
    routinesBody: "You will be able to repeat a job on the days and times you choose when an Assistant offers that routine.",
    routinesExample: "“Every morning, check my ads and send me a summary on WhatsApp.”",
    routinesStatus: "Not yet available in the current public Assistant.",
    securityKicker: "Security",
    securityTitle: "I work for you. You stay in control.",
    securityPoints: [
      "You choose which accounts to connect.",
      "Each Assistant receives only the access it needs.",
      "Important actions may ask for your confirmation.",
      "You can remove access and Assistants.",
    ],
    securityClosing: "My brain coordinates the work. My apps complete it within the limits you approved.",
    approval: "Approval required",
    approvalAction: "Publish Post on X",
    approve: "Approve",
    reject: "Do not allow",
    finalTitle: "What work do you want to take off your list?",
    finalBody: "Sign in to your Shimpz account, choose your Assistants, and tell me the result you want.",
    finalMicrocopy: "It only takes a few steps to get started.",
  });
</script>

<Seo title={content.seoTitle} description={content.seoDescription} {lang} />
<HomeHeader {lang} />

<section class="hero wrap" aria-labelledby="hero-title">
  <div class="hero-copy">
    <p class="eyebrow"><span aria-hidden="true"></span>{content.eyebrow}</p>
    <h1 id="hero-title">{content.title}</h1>
    <p class="promise">{content.promise}</p>
    <p class="description">{content.description}</p>
    <p class="support">{content.support}</p>
    <div class="hero-actions">
      <a class="primary-cta" href={u.login(lang)}>{content.primaryCta}</a>
      <a class="secondary-cta" href="#demo">{content.secondaryCta}<span aria-hidden="true">↓</span></a>
    </div>
    <p class="microcopy">{content.microcopy}</p>
  </div>

  <div class="work-card" aria-label={content.liveExample}>
    <div class="work-card-head">
      <span>{content.liveExample}</span>
      <i aria-hidden="true"></i>
    </div>
    <p class="request"><span aria-hidden="true">“</span>{content.task}</p>
    <ol>
      <li class="done"><i aria-hidden="true">✓</i><span>{content.brain}</span><small>Shimpz</small></li>
      <li class="working"><i aria-hidden="true"></i><span>{content.assistantOne}</span><small>Assistant 01</small></li>
      <li class="working"><i aria-hidden="true"></i><span>{content.assistantTwo}</span><small>Assistant 02</small></li>
      <li class="result"><i aria-hidden="true">✓</i><span>{content.complete}</span><small>PDF</small></li>
    </ol>
  </div>
</section>

<section id="demo" class="section demo" aria-labelledby="demo-title">
  <div class="wrap">
    <div class="section-heading centered">
      <p class="kicker">{content.demoKicker}</p>
      <h2 id="demo-title">{content.demoTitle}</h2>
    </div>

    <div class="demo-grid">
      <div class="conversation">
        <div class="message user-message">
          <span>{content.user}</span>
          <p>{content.userMessage}</p>
        </div>
        <div class="message shimpz-message">
          <span>Shimpz</span>
          <p>{content.shimpzMessageOne}</p>
          <p>{content.shimpzMessageTwo}</p>
        </div>
      </div>

      <ol class="request-flow">
        {#each content.flow as item, index (item)}
          <li>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{item}</strong>
          </li>
        {/each}
      </ol>
    </div>

    <div class="stack-block">
      <ToolStack {lang} />
    </div>
  </div>
</section>

<section id="how-it-works" class="section how wrap" aria-labelledby="how-title">
  <div class="section-heading">
    <p class="kicker">{content.howKicker}</p>
    <h2 id="how-title">{content.howTitle}</h2>
  </div>
  <ol class="steps">
    {#each content.steps as step (step[0])}
      <li><h3>{step[0]}</h3><p>{step[1]}</p></li>
    {/each}
  </ol>
</section>

<section id="assistants" class="section assistants" aria-labelledby="assistants-title">
  <div class="wrap">
    <div class="section-heading wide">
      <p class="kicker">{content.assistantsKicker}</p>
      <h2 id="assistants-title">{content.assistantsTitle}</h2>
      <div><p>{content.assistantsBodyOne}</p><p>{content.assistantsBodyTwo}</p></div>
    </div>

    <div class="catalog-grid">
      <article class="product-card">
        <span class="availability"><i aria-hidden="true"></i>{content.availableNow}</span>
        <div class="product-icon" aria-hidden="true">S</div>
        <h3>{content.assistantName}</h3>
        <p>{content.assistantResult}</p>
        <small>{content.assistantSafety}</small>
        <div class="card-actions">
          <a class="card-primary" href={u.assistants(lang)}>{content.useAssistant}</a>
          <a class="card-secondary" href={`${u.assistants(lang)}?assistant=shimpz-assistant`}>{content.addAssistant}</a>
        </div>
      </article>

      <article id="teams" class="product-card team-card">
        <span class="availability">{content.teamsLabel}</span>
        <div class="team-icons" aria-hidden="true"><i>S</i><i>+</i><i>✓</i></div>
        <h3>{content.teamName}</h3>
        <p>{content.teamResult}</p>
        <small>{content.teamReality}</small>
        <div class="card-actions">
          <a class="card-primary" href={u.team(lang)}>{content.chooseTeam}</a>
        </div>
      </article>
    </div>
  </div>
</section>

<section class="section routines wrap" aria-labelledby="routines-title">
  <div class="routine-copy">
    <p class="kicker">{content.routinesKicker}</p>
    <h2 id="routines-title">{content.routinesTitle}</h2>
    <p>{content.routinesBody}</p>
    <blockquote>{content.routinesExample}</blockquote>
    <span class="status-badge">{content.routinesStatus}</span>
  </div>
  <div class="routine-visual" aria-hidden="true">
    <div class="schedule-head"><span>08:00</span><i></i><i></i><i></i><i></i><i></i></div>
    <div class="schedule-task"><i>↻</i><div><strong>{lang === "pt" ? "Resumo dos anúncios" : "Ads summary"}</strong><small>{lang === "pt" ? "Todos os dias" : "Every day"}</small></div></div>
    <div class="notification"><i>✓</i><div><strong>WhatsApp</strong><small>{lang === "pt" ? "Resumo entregue" : "Summary delivered"}</small></div></div>
  </div>
</section>

<section class="section security" aria-labelledby="security-title">
  <div class="wrap security-grid">
    <div>
      <p class="kicker">{content.securityKicker}</p>
      <h2 id="security-title">{content.securityTitle}</h2>
      <ul>
        {#each content.securityPoints as point (point)}<li><i aria-hidden="true">✓</i>{point}</li>{/each}
      </ul>
      <p class="security-closing">{content.securityClosing}</p>
    </div>
    <div class="approval-card">
      <span>{content.approval}</span>
      <strong>{content.approvalAction}</strong>
      <div class="permission"><i aria-hidden="true">S</i><p><b>Shimpz Assistant</b><small>{lang === "pt" ? "Solicita uma ação importante" : "Requests an important action"}</small></p></div>
      <div class="approval-actions"><button type="button">{content.approve}</button><button type="button">{content.reject}</button></div>
    </div>
  </div>
</section>

<section class="section final-cta wrap" aria-labelledby="final-title">
  <p class="kicker">Shimpz</p>
  <h2 id="final-title">{content.finalTitle}</h2>
  <p>{content.finalBody}</p>
  <a class="primary-cta" href={u.login(lang)}>{content.primaryCta}</a>
  <small>{content.finalMicrocopy}</small>
</section>

<style>
  :global(html) { scroll-behavior: smooth; }
  .section { padding-block: clamp(5rem, 10vw, 8rem); }
  .hero {
    display: grid;
    min-height: min(800px, calc(100dvh - 4.75rem));
    grid-template-columns: minmax(0, 1.05fr) minmax(25rem, 0.8fr);
    align-items: center;
    gap: clamp(3rem, 8vw, 7rem);
    padding-block: clamp(4rem, 9vw, 7.5rem);
  }
  .eyebrow, .kicker {
    margin: 0 0 1rem;
    color: var(--color-cyan);
    font-family: var(--font-mono);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  .eyebrow { display: flex; align-items: center; gap: 0.65rem; }
  .eyebrow span { width: 0.5rem; height: 0.5rem; border-radius: 50%; background: var(--color-green); box-shadow: 0 0 12px var(--color-green); }
  h1 { margin: 0; font-size: clamp(3rem, 6.2vw, 6.2rem); line-height: 0.98; letter-spacing: -0.075em; }
  .promise { max-width: 22ch; margin: 1.6rem 0 0; font-size: clamp(1.35rem, 2.5vw, 2rem); font-weight: 700; line-height: 1.25; letter-spacing: -0.035em; }
  .description { max-width: 43rem; margin: 1.4rem 0 0; color: #d4d4d8; font-size: clamp(1rem, 1.3vw, 1.12rem); line-height: 1.7; }
  .support { max-width: 41rem; margin: 0.8rem 0 0; color: var(--color-muted); line-height: 1.7; }
  .hero-actions { display: flex; flex-wrap: wrap; gap: 0.8rem; margin-top: 2rem; }
  .primary-cta, .secondary-cta, .card-primary, .card-secondary {
    display: inline-flex; min-height: 3.25rem; align-items: center; justify-content: center; gap: 0.7rem; padding: 0.8rem 1.25rem; border-radius: 0.65rem; font-weight: 750; transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
  }
  .primary-cta { background: #fff; color: #171717; box-shadow: 0 12px 32px rgba(255,255,255,0.13); }
  .primary-cta:hover { transform: translateY(-2px); box-shadow: 0 16px 38px rgba(255,255,255,0.2); }
  .secondary-cta { border: 1px solid var(--color-border-strong); color: var(--color-fg); background: var(--color-card); }
  .secondary-cta:hover { border-color: var(--color-cyan); }
  .microcopy { margin: 0.8rem 0 0; color: var(--color-muted-2); font-size: 0.8rem; }
  .work-card { position: relative; overflow: hidden; border: 1px solid var(--color-border-strong); border-radius: 1.2rem; background: linear-gradient(145deg, #111, #050505); box-shadow: 0 34px 90px rgba(0,0,0,.6); }
  .work-card::before { position: absolute; inset: 0 0 auto; height: 1px; background: linear-gradient(90deg, transparent, var(--color-cyan), transparent); content: ""; }
  .work-card-head { display: flex; align-items: center; justify-content: space-between; padding: 1.1rem 1.25rem; border-bottom: 1px solid var(--color-border); color: var(--color-muted); font-family: var(--font-mono); font-size: 0.68rem; text-transform: uppercase; letter-spacing: .1em; }
  .work-card-head i { width: .48rem; height: .48rem; border-radius: 50%; background: var(--color-green); box-shadow: 0 0 10px var(--color-green); }
  .request { margin: 1.25rem; padding: 1rem; border: 1px solid #273036; border-radius: .8rem; background: #0b1114; color: #e8fafb; font-size: .95rem; line-height: 1.5; }
  .request span { color: var(--color-cyan); font-size: 1.4rem; }
  .work-card ol { margin: 0; padding: 0 1.25rem 1.25rem; list-style: none; }
  .work-card li { display: grid; grid-template-columns: 1.8rem 1fr auto; align-items: center; gap: .7rem; padding: .8rem 0; border-bottom: 1px solid var(--color-border); font-size: .86rem; }
  .work-card li:last-child { border: 0; }
  .work-card li > i { display: grid; width: 1.6rem; height: 1.6rem; place-items: center; border: 1px solid var(--color-border-strong); border-radius: 50%; color: var(--color-green); font-style: normal; font-size: .7rem; }
  .work-card li.working > i { border-top-color: var(--color-cyan); }
  .work-card li small { color: var(--color-muted-2); font-family: var(--font-mono); font-size: .58rem; text-transform: uppercase; }
  .work-card li.result { color: var(--color-green); }
  h2 { margin: 0; font-size: clamp(2.2rem, 4.7vw, 4.5rem); line-height: 1.05; letter-spacing: -0.065em; }
  .section-heading { max-width: 45rem; }
  .section-heading.centered { margin-inline: auto; text-align: center; }
  .demo { border-block: 1px solid var(--color-border); background: #050505; }
  .demo-grid { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(19rem, .85fr); gap: clamp(2rem, 6vw, 5rem); align-items: center; margin-top: clamp(3rem, 7vw, 5rem); }
  .stack-block { margin-top: clamp(5rem, 10vw, 8rem); padding-top: clamp(4rem, 8vw, 6rem); border-top: 1px solid var(--color-border); }
  .conversation { display: flex; flex-direction: column; gap: 1rem; }
  .message { max-width: 88%; padding: 1.15rem 1.25rem; border-radius: 1rem; }
  .message > span { font-family: var(--font-mono); font-size: .65rem; font-weight: 700; text-transform: uppercase; letter-spacing: .1em; }
  .message p { margin: .45rem 0 0; line-height: 1.6; }
  .user-message { align-self: flex-end; border-bottom-right-radius: .2rem; background: #e7fafd; color: #061315; }
  .user-message > span { color: #167680; }
  .shimpz-message { border: 1px solid #29464a; border-bottom-left-radius: .2rem; background: #081214; }
  .shimpz-message > span { color: var(--color-cyan); }
  .request-flow { margin: 0; padding: 0; list-style: none; }
  .request-flow li { position: relative; display: grid; grid-template-columns: 2.5rem 1fr; align-items: center; gap: 1rem; min-height: 4.3rem; }
  .request-flow li:not(:last-child)::after { position: absolute; top: 3.2rem; bottom: -.8rem; left: 1.17rem; width: 1px; background: linear-gradient(var(--color-cyan), var(--color-border)); content: ""; }
  .request-flow span { display: grid; width: 2.4rem; height: 2.4rem; place-items: center; border: 1px solid var(--color-cyan); border-radius: 50%; color: var(--color-cyan); font-family: var(--font-mono); font-size: .65rem; }
  .request-flow strong { font-size: 1rem; }
  .how { display: grid; grid-template-columns: minmax(18rem,.8fr) minmax(0,1.2fr); gap: clamp(3rem,9vw,8rem); }
  .steps { display: grid; margin: 0; padding: 0; gap: .8rem; list-style: none; }
  .steps li { padding: 1.4rem 1.5rem; border: 1px solid var(--color-border); border-radius: .85rem; background: var(--color-card); }
  .steps h3 { margin: 0; font-size: 1.25rem; }
  .steps p { margin: .45rem 0 0; color: var(--color-muted); }
  .assistants { border-block: 1px solid var(--color-border); background: radial-gradient(circle at 20% 0%, rgba(0,240,255,.07), transparent 30%), #050505; }
  .section-heading.wide { display: grid; max-width: none; grid-template-columns: minmax(0,1.15fr) minmax(18rem,.65fr); gap: 1rem clamp(3rem,9vw,8rem); }
  .section-heading.wide .kicker { grid-column: 1 / -1; }
  .section-heading.wide div p { margin: 0 0 .8rem; color: var(--color-muted); }
  .catalog-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 1rem; margin-top: clamp(3rem,6vw,5rem); }
  .product-card { display: flex; min-height: 29rem; flex-direction: column; padding: clamp(1.5rem,3vw,2.2rem); border: 1px solid var(--color-border-strong); border-radius: 1.1rem; background: #090909; }
  .availability { display: inline-flex; align-items: center; align-self: flex-start; gap: .5rem; color: var(--color-muted); font-family: var(--font-mono); font-size: .65rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
  .availability i { width: .45rem; height: .45rem; border-radius: 50%; background: var(--color-green); box-shadow: 0 0 8px var(--color-green); }
  .product-icon { display: grid; width: 4rem; height: 4rem; margin-top: 2.2rem; place-items: center; border-radius: 1.1rem; background: linear-gradient(145deg,var(--color-cyan),#1872ff); color: #001114; font-family: var(--font-mono); font-size: 1.6rem; font-weight: 800; }
  .team-icons { display: flex; margin-top: 2.2rem; }
  .team-icons i { display: grid; width: 3.1rem; height: 3.1rem; margin-right: -.5rem; place-items: center; border: 3px solid #090909; border-radius: 50%; background: #202024; color: var(--color-fg); font-family: var(--font-mono); font-style: normal; font-weight: 700; }
  .team-icons i:nth-child(2) { background: #18383b; color: var(--color-cyan); }
  .team-icons i:nth-child(3) { background: #163428; color: var(--color-green); }
  .product-card h3 { margin: 1.5rem 0 0; font-size: 1.75rem; }
  .product-card > p { margin: .8rem 0 0; line-height: 1.65; }
  .product-card > small { display: block; margin: .8rem 0 0; color: var(--color-muted); line-height: 1.6; }
  .card-actions { display: flex; flex-wrap: wrap; gap: .65rem; margin-top: auto; padding-top: 1.8rem; }
  .card-primary { background: var(--color-cyan); color: var(--color-accent-ink); }
  .card-secondary { border: 1px solid var(--color-border-strong); color: var(--color-fg); }
  .routines { display: grid; grid-template-columns: minmax(0,.9fr) minmax(20rem,.7fr); gap: clamp(3rem,10vw,9rem); align-items: center; }
  .routine-copy > p:not(.kicker) { color: var(--color-muted); font-size: 1.05rem; }
  blockquote { margin: 1.5rem 0; padding-left: 1.2rem; border-left: 2px solid var(--color-cyan); color: #e5e5e5; font-size: 1.1rem; font-weight: 600; }
  .status-badge { display: inline-flex; padding: .45rem .7rem; border: 1px solid #5c4b1d; border-radius: 999px; background: #171307; color: #f2cf69; font-size: .75rem; }
  .routine-visual { padding: 1.2rem; border: 1px solid var(--color-border-strong); border-radius: 1rem; background: #080808; }
  .schedule-head { display: grid; grid-template-columns: 1fr repeat(5,1.5rem); align-items: center; gap: .45rem; padding-bottom: 1rem; border-bottom: 1px solid var(--color-border); color: var(--color-muted); font-family: var(--font-mono); font-size: .7rem; }
  .schedule-head i { width: .55rem; height: .55rem; justify-self: center; border-radius: 50%; background: #2a2a2a; }
  .schedule-head i:first-of-type { background: var(--color-cyan); box-shadow: 0 0 8px var(--color-cyan); }
  .schedule-task, .notification, .permission { display: flex; align-items: center; gap: .9rem; }
  .schedule-task { margin-top: 1rem; padding: 1rem; border-radius: .75rem; background: #101416; }
  .schedule-task > i, .notification > i, .permission > i { display: grid; width: 2.4rem; height: 2.4rem; flex: none; place-items: center; border-radius: .65rem; background: #16383c; color: var(--color-cyan); font-style: normal; }
  .schedule-task strong, .schedule-task small, .notification strong, .notification small { display: block; }
  .schedule-task small, .notification small { color: var(--color-muted); }
  .notification { width: 92%; margin: 1rem 0 0 auto; padding: .9rem; border: 1px solid #24583f; border-radius: .75rem; background: #0d1a13; }
  .notification > i { background: #153d29; color: var(--color-green); }
  .security { border-block: 1px solid var(--color-border); background: #050505; }
  .security-grid { display: grid; grid-template-columns: minmax(0,1.05fr) minmax(20rem,.65fr); gap: clamp(3rem,10vw,8rem); align-items: center; }
  .security ul { display: grid; margin: 2rem 0 0; padding: 0; gap: .85rem; list-style: none; }
  .security li { display: flex; align-items: center; gap: .8rem; color: #d4d4d8; }
  .security li i { display: grid; width: 1.35rem; height: 1.35rem; flex: none; place-items: center; border-radius: 50%; background: #153d29; color: var(--color-green); font-style: normal; font-size: .7rem; }
  .security-closing { max-width: 42rem; margin: 2rem 0 0; color: var(--color-muted); line-height: 1.7; }
  .approval-card { padding: 1.5rem; border: 1px solid var(--color-border-strong); border-radius: 1rem; background: #0a0a0a; box-shadow: 0 24px 70px rgba(0,0,0,.5); }
  .approval-card > span { color: #f2cf69; font-family: var(--font-mono); font-size: .65rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
  .approval-card > strong { display: block; margin-top: .6rem; font-size: 1.35rem; }
  .permission { margin-top: 1.5rem; padding-block: 1rem; border-block: 1px solid var(--color-border); }
  .permission p { margin: 0; }
  .permission b, .permission small { display: block; }
  .permission small { color: var(--color-muted); }
  .approval-actions { display: grid; grid-template-columns: 1fr 1fr; gap: .6rem; margin-top: 1rem; }
  .approval-actions button { min-height: 2.8rem; border: 0; border-radius: .6rem; background: var(--color-cyan); color: var(--color-accent-ink); font-weight: 700; }
  .approval-actions button:last-child { border: 1px solid var(--color-border-strong); background: transparent; color: var(--color-muted); }
  .final-cta { text-align: center; }
  .final-cta h2 { max-width: 17ch; margin-inline: auto; }
  .final-cta > p:not(.kicker) { max-width: 42rem; margin: 1.3rem auto 2rem; color: var(--color-muted); font-size: 1.05rem; }
  .final-cta small { display: block; margin-top: .9rem; color: var(--color-muted-2); }
  @media (max-width: 900px) {
    .hero, .demo-grid, .how, .routines, .security-grid { grid-template-columns: 1fr; }
    .hero { min-height: auto; }
    .work-card { max-width: 35rem; }
    .section-heading.wide { grid-template-columns: 1fr; }
    .section-heading.wide .kicker { grid-column: 1; }
  }
  @media (max-width: 700px) {
    .catalog-grid { grid-template-columns: 1fr; }
    .product-card { min-height: 0; }
    .hero { padding-top: 3.5rem; }
    .section { padding-block: 4.5rem; }
  }
  @media (max-width: 480px) {
    .hero-actions, .card-actions { align-items: stretch; flex-direction: column; }
    .primary-cta, .secondary-cta, .card-primary, .card-secondary { width: 100%; }
    .message { max-width: 96%; }
    .approval-actions { grid-template-columns: 1fr; }
  }
  @media (prefers-reduced-motion: reduce) {
    :global(html) { scroll-behavior: auto; }
    .primary-cta, .secondary-cta, .card-primary, .card-secondary { transition: none; }
  }
</style>

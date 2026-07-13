// The Shimpz marketplace catalog — the single source of truth the storefront prerenders from.
// Two first-class kinds, kept cleanly separate:
//   • Driver  — a platform CAPABILITY an app can be granted (the audited credential-broker sidecars:
//               Cloudflare, Postgres, the bus, OpenAI, ShimpzPay …). Apps request these as PERMISSIONS.
//   • App     — an installable product. It declares the drivers it needs (permissions) and the other
//               apps it depends on. Its `spec` is written to be read by a human, not parsed.
// MVP seed (in-code); the DB-backed, publisher-owned catalog is a later layer behind the same surface.

export const LOCALES = ["en", "pt"] as const;
export type Locale = (typeof LOCALES)[number];
export type I18n = Record<Locale, string>;
export const t = (v: I18n, l: Locale): string => v[l] ?? v.en;

// ── Drivers (platform capabilities / permissions) ───────────────────────────────────────────────
export type DriverCategory =
  | "Hosting" | "Data" | "Integration" | "AI" | "Payments" | "Network" | "Dev" | "Automation";

export interface Driver {
  id: string;
  name: string; // brand/technical name — not translated
  category: DriverCategory;
  icon: string; // emoji, self-contained (no external asset)
  brand?: string; // official BRAND COLOR (recognition) for third-party drivers — not a reproduced logo
  summary: I18n; // one line, human-readable
  blurb: I18n; // a paragraph
  grants: I18n[]; // exactly what holding this permission lets an app do
}

export const DRIVERS: Driver[] = [
  {
    id: "cloudflare", name: "Cloudflare", category: "Hosting", icon: "☁️", brand: "#F38020",
    summary: { en: "Publish an app to your own domain.", pt: "Publica um app no seu próprio domínio." },
    blurb: {
      en: "Gives an app a public front door: DNS, a Cloudflare Tunnel and Zero-Trust access — all scoped to its own <slug>.grid.shimpz.com and nothing else.",
      pt: "Dá a um app uma porta pública: DNS, um Cloudflare Tunnel e acesso Zero-Trust — tudo restrito ao seu próprio <slug>.grid.shimpz.com e nada além.",
    },
    grants: [
      { en: "Create a proxied DNS record for its own subdomain", pt: "Criar um registro DNS proxied do próprio subdomínio" },
      { en: "Add a tunnel ingress rule (never rewrite others)", pt: "Adicionar uma regra de ingress no túnel (nunca reescrever outras)" },
    ],
  },
  {
    id: "postgres", name: "Postgres", category: "Data", icon: "🐘", brand: "#336791",
    summary: { en: "An isolated database, one per app.", pt: "Um banco isolado, um por app." },
    blurb: {
      en: "Each app gets its OWN least-privilege Postgres database (proj_<name>) — it can never see another app's data, and never the platform's.",
      pt: "Cada app ganha seu PRÓPRIO banco Postgres de menor privilégio (proj_<name>) — nunca enxerga os dados de outro app, nem os da plataforma.",
    },
    grants: [{ en: "Read/write only its own database", pt: "Ler/escrever apenas no próprio banco" }],
  },
  {
    id: "bus", name: "Event Bus", category: "Integration", icon: "🐼", brand: "#E4462B",
    summary: { en: "Async events, queues and retries.", pt: "Eventos async, filas e retries." },
    blurb: {
      en: "Publish and consume events across apps with at-least-once delivery, a dead-letter queue and retries — the backbone for anything that reacts to something else.",
      pt: "Publica e consome eventos entre apps com entrega at-least-once, dead-letter queue e retries — a espinha dorsal de tudo que reage a algo.",
    },
    grants: [
      { en: "Publish to its own <name>.* topics", pt: "Publicar nos próprios tópicos <name>.*" },
      { en: "Consume topics it is explicitly granted", pt: "Consumir tópicos que recebeu grant explícito" },
    ],
  },
  {
    id: "storage", name: "Object Storage", category: "Data", icon: "📦", brand: "#F6821F",
    summary: { en: "Store files and share links.", pt: "Guarda arquivos e compartilha links." },
    blurb: {
      en: "Upload artifacts (PDFs, images, exports) to Cloudflare R2 and hand back signed links — durable, cheap, and off the app's own disk.",
      pt: "Sobe artefatos (PDFs, imagens, exports) no Cloudflare R2 e devolve links assinados — durável, barato e fora do disco do app.",
    },
    grants: [{ en: "Put/get objects under its own prefix", pt: "Put/get de objetos sob o próprio prefixo" }],
  },
  {
    id: "openai", name: "OpenAI", category: "AI", icon: "🧠", brand: "#10A37F",
    summary: { en: "Language, images and voice.", pt: "Linguagem, imagens e voz." },
    blurb: {
      en: "Generate copy, images and speech through the platform's audited OpenAI sidecar — the app never holds the key.",
      pt: "Gera texto, imagens e fala pelo sidecar OpenAI auditado da plataforma — o app nunca segura a chave.",
    },
    grants: [{ en: "Call the allow-listed models only", pt: "Chamar apenas os modelos allow-listed" }],
  },
  {
    id: "pay", name: "ShimpzPay", category: "Payments", icon: "💳",
    summary: { en: "Charge customers, handle billing.", pt: "Cobra clientes, cuida do billing." },
    blurb: {
      en: "Take payments through ShimpzPay — the one billing rail. Charges are audited and the take-rate is handled for you.",
      pt: "Recebe pagamentos pelo ShimpzPay — o único trilho de billing. As cobranças são auditadas e o take-rate é resolvido pra você.",
    },
    grants: [{ en: "Create charge intents for its own customers", pt: "Criar intenções de cobrança dos próprios clientes" }],
  },
  {
    id: "proxy", name: "Residential Proxy", category: "Network", icon: "🛰️",
    summary: { en: "Browse from a residential IP.", pt: "Navega de um IP residencial." },
    blurb: {
      en: "Route the browser through a residential ISP IP so automated sessions look human and stay logged in.",
      pt: "Roteia o navegador por um IP residencial de ISP pra sessões automatizadas parecerem humanas e continuarem logadas.",
    },
    grants: [{ en: "Use the shared residential egress", pt: "Usar o egress residencial compartilhado" }],
  },
  {
    id: "github", name: "GitHub", category: "Dev", icon: "🐙", brand: "#2B3137",
    summary: { en: "Push and manage repositories.", pt: "Faz push e gerencia repositórios." },
    blurb: {
      en: "Read and push to GitHub repositories through a narrow, audited surface — no broad token in the app.",
      pt: "Lê e faz push em repositórios do GitHub por uma superfície estreita e auditada — sem token amplo no app.",
    },
    grants: [{ en: "Push to the repos it is scoped to", pt: "Push nos repos aos quais tem escopo" }],
  },
  {
    id: "browser", name: "Undetectable Browser", category: "Automation", icon: "🕶️",
    summary: { en: "Drive a real Chrome, undetectably.", pt: "Dirige um Chrome real, indetectável." },
    blurb: {
      en: "Operate a real, headful Chrome via CDP with human input — logs into sites and stays logged in, isolated from the app's credentials.",
      pt: "Opera um Chrome real e headful via CDP com input humano — loga em sites e continua logado, isolado das credenciais do app.",
    },
    grants: [{ en: "Drive the shared browser via its audited API", pt: "Dirigir o browser compartilhado pela API auditada" }],
  },
];

export const DRIVER_BY_ID = new Map(DRIVERS.map((d) => [d.id, d]));

// ── Apps (installable products) ─────────────────────────────────────────────────────────────────
export type AppCategory = "Marketing" | "Content" | "Commerce" | "Automation" | "AI";
export const APP_CATEGORIES: AppCategory[] = ["Marketing", "Content", "Commerce", "Automation", "AI"];

export interface App {
  id: string;
  name: string;
  category: AppCategory;
  icon: string;
  tagline: I18n; // one line
  spec: I18n; // the human-readable description: what it does, plainly
  permissions: string[]; // driver ids it needs
  dependsOn: string[]; // app ids it needs installed
  publisher: string;
  price: I18n;
  available: boolean; // true = a REAL deployable artifact exists in the capsule-driver marketplace registry
}

export const APPS: App[] = [
  {
    id: "notification-center", name: "Notification Center", category: "Automation", icon: "🔔",
    tagline: { en: "Approvals, alerts and reports on Telegram.", pt: "Aprovações, alertas e relatórios no Telegram." },
    spec: {
      en: "The one place your apps ask for approval, report results and alert you — with buttons and voice, and it survives restarts.",
      pt: "O lugar único onde seus apps pedem aprovação, reportam resultados e te alertam — com botões e voz, e sobrevive a restart.",
    },
    permissions: ["bus"], dependsOn: [], publisher: "Shimpz",
    price: { en: "Free", pt: "Grátis" }, available: true,
  },
];

export const APP_BY_ID = new Map(APPS.map((a) => [a.id, a]));

// ── slugs & relations (composite English URLs + internal link building) ─────────────────────────
export const catSlug = (c: string): string => c.toLowerCase().replace(/\s+/g, "-");
export const appsInCategory = (c: AppCategory): App[] => APPS.filter((a) => a.category === c);
export const usedCategories = (): AppCategory[] => APP_CATEGORIES.filter((c) => appsInCategory(c).length > 0);
export const appsUsingDriver = (id: string): App[] => APPS.filter((a) => a.permissions.includes(id));
export const dependentsOf = (id: string): App[] => APPS.filter((a) => a.dependsOn.includes(id));
export const relatedApps = (a: App): App[] =>
  APPS.filter((x) => x.id !== a.id && x.category === a.category).slice(0, 3);

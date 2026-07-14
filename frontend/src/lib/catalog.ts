// The Shimpz capability catalog is the source of truth for public driver documentation. The App
// shape at the end of this file is a separate, neutral deployment-policy inventory contract. It is
// not consumed by rendered frontend code and does not describe or publish products.

export const LOCALES = ["en", "pt"] as const;
export type Locale = (typeof LOCALES)[number];
export type I18n = Record<Locale, string>;
export const t = (v: I18n, l: Locale): string => v[l] ?? v.en;

// ── Drivers (audited platform capability inventory) ─────────────────────────────────────────────
export type DriverCategory =
  | "Hosting" | "Data" | "Integration" | "AI" | "Network" | "Dev" | "Automation";

export interface Driver {
  id: string;
  name: string; // brand/technical name — not translated
  category: DriverCategory;
  icon: string; // emoji, self-contained (no external asset)
  brand?: string; // official BRAND COLOR (recognition) for third-party drivers — not a reproduced logo
  summary: I18n; // one line, human-readable
  blurb: I18n; // a paragraph
  features: I18n[]; // the COMPLETE list of shipping operations for this platform component
  boundaries: I18n[]; // who can call it and the limits of that access; never an implied App grant
  creator?: string; // Creator handle — defaults to the platform owner (see DEFAULT_CREATOR)
}

export const DRIVERS: Driver[] = [
  {
    id: "cloudflare", name: "Cloudflare", category: "Hosting", icon: "☁️", brand: "#F38020",
    summary: { en: "Publish an operator-managed app to its own domain.", pt: "Publica um app gerenciado pelo operador no próprio domínio." },
    blurb: {
      en: "The platform Brain's deployment tooling creates DNS, a Cloudflare Tunnel route and Zero-Trust access for an operator-managed app, scoped to its own <slug>.grid.shimpz.com.",
      pt: "As ferramentas de deploy do Cérebro da plataforma criam DNS, rota no Cloudflare Tunnel e acesso Zero-Trust para um app gerenciado pelo operador, restritos ao próprio <slug>.grid.shimpz.com.",
    },
    features: [
      { en: "Publish an app to its own subdomain (<slug>.grid.shimpz.com)", pt: "Publica um app no próprio subdomínio (<slug>.grid.shimpz.com)" },
      { en: "Create and update proxied DNS records", pt: "Cria e atualiza registros DNS proxied" },
      { en: "Add a Cloudflare Tunnel ingress route to the app", pt: "Adiciona uma rota de ingress no Cloudflare Tunnel para o app" },
      { en: "Gate the domain behind Zero-Trust Access (allow-list + one-time PIN)", pt: "Protege o domínio com Zero-Trust Access (allow-list + PIN de uso único)" },
      { en: "Automatic TLS at the edge — no certificates to manage", pt: "TLS automático na borda — sem certificados pra gerenciar" },
      { en: "Clean teardown — the route and DNS are removed on uninstall", pt: "Desmonte limpo — a rota e o DNS são removidos ao desinstalar" },
    ],
    boundaries: [
      { en: "Called by the platform Brain's deployment tooling; Apps never receive Cloudflare credentials", pt: "Chamado pelas ferramentas de deploy do Cérebro da plataforma; Apps nunca recebem credenciais Cloudflare" },
      { en: "May create its own proxied DNS record and append its own tunnel route", pt: "Pode criar o próprio registro DNS proxied e acrescentar a própria rota no túnel" },
    ],
  },
  {
    id: "postgres", name: "Postgres", category: "Data", icon: "🐘", brand: "#336791",
    summary: { en: "An isolated database, one per app.", pt: "Um banco isolado, um por app." },
    blurb: {
      en: "Each app gets its OWN least-privilege Postgres database (proj_<name>) — it can never see another app's data, and never the platform's.",
      pt: "Cada app ganha seu PRÓPRIO banco Postgres de menor privilégio (proj_<name>) — nunca enxerga os dados de outro app, nem os da plataforma.",
    },
    features: [
      { en: "A dedicated database (proj_<name>), provisioned on install", pt: "Um banco dedicado (proj_<name>), provisionado na instalação" },
      { en: "A least-privilege role scoped to that database only", pt: "Um papel de menor privilégio restrito só àquele banco" },
      { en: "Full read/write, schema and migrations within its own database", pt: "Leitura/escrita completa, schema e migrações no próprio banco" },
      { en: "Connection string injected as env — the app never holds admin credentials", pt: "String de conexão injetada como env — o app nunca segura credenciais de admin" },
      { en: "Fully isolated — never sees another app's data, nor the platform's", pt: "Totalmente isolado — nunca vê os dados de outro app, nem os da plataforma" },
      { en: "Dropped cleanly on uninstall", pt: "Removido de forma limpa ao desinstalar" },
    ],
    boundaries: [
      { en: "An App receives only its database-specific connection string", pt: "Um App recebe apenas a string de conexão específica do seu banco" },
      { en: "No platform or Postgres administrator credential enters the App", pt: "Nenhuma credencial da plataforma ou de administrador Postgres entra no App" },
    ],
  },
  {
    id: "bus", name: "Event Bus", category: "Integration", icon: "🐼", brand: "#E4462B",
    summary: { en: "Async events, queues and retries.", pt: "Eventos async, filas e retries." },
    blurb: {
      en: "Publish and consume events across apps with at-least-once delivery, a dead-letter queue and retries — the backbone for anything that reacts to something else.",
      pt: "Publica e consome eventos entre apps com entrega at-least-once, dead-letter queue e retries — a espinha dorsal de tudo que reage a algo.",
    },
    features: [
      { en: "Publish events to its own <name>.* topics", pt: "Publica eventos nos próprios tópicos <name>.*" },
      { en: "Consume topics it has been explicitly granted", pt: "Consome tópicos que recebeu grant explícito" },
      { en: "At-least-once delivery", pt: "Entrega at-least-once" },
      { en: "Automatic retries with backoff", pt: "Retries automáticos com backoff" },
      { en: "Dead-letter queue for messages that keep failing", pt: "Dead-letter queue para mensagens que seguem falhando" },
      { en: "Durable queues that survive restarts", pt: "Filas duráveis que sobrevivem a reinícios" },
    ],
    boundaries: [
      { en: "An App may publish only to its own <name>.* topics", pt: "Um App pode publicar apenas nos próprios tópicos <name>.*" },
      { en: "Cross-App consumption requires an explicit manifest grant", pt: "O consumo entre Apps exige um grant explícito no manifesto" },
    ],
  },
  {
    id: "storage", name: "Object Storage", category: "Data", icon: "📦", brand: "#F6821F",
    summary: { en: "Brain-side artifact storage and share links.", pt: "Armazenamento de artefatos e links para o Cérebro." },
    blurb: {
      en: "The platform Brain uses the audited R2 sidecar to upload, list and retrieve artifacts. This operator-managed capability is not exposed as an App permission.",
      pt: "O Cérebro da plataforma usa o sidecar R2 auditado para enviar, listar e buscar artefatos. Essa capacidade gerenciada pelo operador não é exposta como permissão de App.",
    },
    features: [
      { en: "Upload one Brain-selected file (PDF, image or export)", pt: "Envia um arquivo selecionado pelo Cérebro (PDF, imagem ou export)" },
      { en: "List a prefix and download one bounded object", pt: "Lista um prefixo e baixa um objeto com tamanho limitado" },
      { en: "Generate signed, time-limited share links", pt: "Gera links de compartilhamento assinados e com validade" },
      { en: "Keep R2 credentials inside the audited sidecar", pt: "Mantém as credenciais R2 dentro do sidecar auditado" },
    ],
    boundaries: [
      { en: "Platform Brain only; no App manifest grant or App route exists", pt: "Somente o Cérebro da plataforma; não existe grant de manifesto nem rota para Apps" },
      { en: "The Brain-facing API has upload, list and get operations, but no delete operation", pt: "A API voltada ao Cérebro oferece upload, list e get, mas não oferece delete" },
    ],
  },
  {
    id: "openai", name: "OpenAI", category: "AI", icon: "🧠", brand: "#10A37F",
    summary: { en: "Platform media generation and voice processing.", pt: "Geração de mídia e processamento de voz da plataforma." },
    blurb: {
      en: "The platform Brain's image tool and Telegram voice gateway call the audited OpenAI sidecar. This media capability is not exposed as an App permission.",
      pt: "A ferramenta de imagens do Cérebro da plataforma e o gateway de voz do Telegram chamam o sidecar OpenAI auditado. Essa capacidade de mídia não é exposta como permissão de App.",
    },
    features: [
      { en: "Image generation (gpt-image)", pt: "Geração de imagens (gpt-image)" },
      { en: "Speech-to-text transcription", pt: "Transcrição de fala para texto" },
      { en: "Text-to-speech voice", pt: "Voz de texto para fala" },
      { en: "The OpenAI sidecar holds the media API key", pt: "O sidecar OpenAI guarda a chave de API de mídia" },
      { en: "Requests are audited", pt: "As requisições são auditadas" },
    ],
    boundaries: [
      { en: "Platform Brain and Telegram gateway only; no App manifest grant or App route exists", pt: "Somente o Cérebro da plataforma e o gateway do Telegram; não existe grant de manifesto nem rota para Apps" },
      { en: "Only allow-listed image, transcription and speech operations are accepted", pt: "Somente operações permitidas de imagem, transcrição e fala são aceitas" },
    ],
  },
  {
    id: "proxy", name: "Residential Proxy", category: "Network", icon: "🛰️",
    summary: { en: "Optional residential egress for the platform Browser.", pt: "Egress residencial opcional para o Browser da plataforma." },
    blurb: {
      en: "When the operator configures IPRoyal credentials, the Browser container routes Chrome through that residential upstream. This is a Browser setting, not an App egress permission.",
      pt: "Quando o operador configura credenciais IPRoyal, o container do Browser roteia o Chrome por esse upstream residencial. Essa é uma configuração do Browser, não uma permissão de egress para Apps.",
    },
    features: [
      { en: "Optionally route Chrome through a configured residential ISP upstream", pt: "Opcionalmente roteia o Chrome por um upstream residencial configurado" },
      { en: "Use a local authenticated relay because Chrome does not accept upstream proxy credentials", pt: "Usa um relay local autenticado porque o Chrome não aceita credenciais do proxy upstream" },
      { en: "Select one configured upstream when the Browser starts", pt: "Seleciona um upstream configurado quando o Browser inicia" },
      { en: "Keep residential proxy credentials inside the Browser container", pt: "Mantém as credenciais do proxy residencial dentro do container do Browser" },
    ],
    boundaries: [
      { en: "Browser container only; Apps never receive this egress path or its credentials", pt: "Somente o container do Browser; Apps nunca recebem esse caminho de egress nem suas credenciais" },
      { en: "App egress uses the separate destination-allowlisted App proxy", pt: "O egress de Apps usa o proxy separado com destinos permitidos" },
    ],
  },
];

export const DRIVER_BY_ID = new Map(DRIVERS.map((d) => [d.id, d]));

// ── Apps (internal operational inventory only) ──────────────────────────────────────────────────
// This type deliberately contains only deployment-policy facts. It has no public presentation,
// publisher, pricing, review, or route metadata, and no rendered component imports APPS. Adding a
// trusted registry entry here therefore cannot silently publish a product surface or an install CTA.
export type Arch = "amd64" | "arm64";

export interface App {
  id: string;
  permissions: string[]; // driver ids it needs
  dependsOn: string[]; // app ids it needs installed
  archs: Arch[];
}

// Runtime status and installed-App controls come from capsule-driver, not from this source list.
export const APPS: App[] = [];

// ── Creators ─────────────────────────────────────────────────────────────────────────
// A Creator owns platform artifacts such as drivers. GitHub identity is explicit catalog metadata;
// the handle is the profile slug. Platform-owned artifacts default to DEFAULT_CREATOR.
export const DEFAULT_CREATOR = "julianoamg";
export const creatorOf = (x: { creator?: string }): string => x.creator ?? DEFAULT_CREATOR;

export interface Creator {
  handle: string; // GitHub handle — also the profile slug
  name: string;
  github: string; // explicit github.com/<github> profile metadata; unrelated to account signup
  bio: I18n;
}

export const CREATORS: Creator[] = [
  {
    handle: "julianoamg",
    name: "Juliano Amaral Gouveia",
    github: "julianoamg",
    bio: {
      en: "Creator of Shimpz and its default audited platform drivers.",
      pt: "Criador do Shimpz e de seus drivers de plataforma auditados padrão.",
    },
  },
];

export const CREATOR_BY_HANDLE = new Map(CREATORS.map((c) => [c.handle, c]));
export const driversByCreator = (handle: string): Driver[] => DRIVERS.filter((d) => creatorOf(d) === handle);

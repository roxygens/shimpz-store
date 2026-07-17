// The Shimpz capability catalog is the source of truth for public Service documentation. The legacy
// App shape at the end of this file is a separate, neutral runtime-policy inventory contract. It is
// not consumed by rendered frontend code and does not describe or publish products.

export const LOCALES = ["en", "pt"] as const;
export type Locale = (typeof LOCALES)[number];
export type I18n = Record<Locale, string>;
export const t = (v: I18n, l: Locale): string => v[l] ?? v.en;

// ── Services (audited platform capability inventory) ────────────────────────────────────────────
export type DriverCategory =
  | "Hosting" | "Data" | "Integration" | "AI" | "Network" | "Dev" | "Automation";

export type ServiceIconName =
  | "edge"
  | "database"
  | "event-bus"
  | "object-storage"
  | "neural-media"
  | "secure-route";

export interface Driver {
  id: string;
  name: string; // brand/technical name — not translated
  category: DriverCategory;
  icon: ServiceIconName; // semantic Shimpz glyph; rendered as a code-native SVG
  brand?: string; // official BRAND COLOR (recognition) for third-party Services — not a reproduced logo
  summary: I18n; // one line, human-readable
  blurb: I18n; // a paragraph
  features: I18n[]; // the COMPLETE list of shipping operations for this platform component
  boundaries: I18n[]; // who can call it and the limits of that access; never an implied Assistant grant
  creator?: string; // Creator handle — defaults to the platform owner (see DEFAULT_CREATOR)
}

export const DRIVERS: Driver[] = [
  {
    id: "cloudflare", name: "Cloudflare", category: "Hosting", icon: "edge", brand: "#F38020",
    summary: { en: "Publish an operator-managed workload to its own domain.", pt: "Publica um workload gerenciado pelo operador no próprio domínio." },
    blurb: {
      en: "The platform Brain's deployment tooling creates DNS, a Cloudflare Tunnel route and Zero-Trust access for an operator-managed workload, scoped to its own <slug>.grid.shimpz.com.",
      pt: "As ferramentas de deploy do Cérebro da plataforma criam DNS, rota no Cloudflare Tunnel e acesso Zero-Trust para um workload gerenciado pelo operador, restritos ao próprio <slug>.grid.shimpz.com.",
    },
    features: [
      { en: "Publish a workload to its own subdomain (<slug>.grid.shimpz.com)", pt: "Publica um workload no próprio subdomínio (<slug>.grid.shimpz.com)" },
      { en: "Create and update proxied DNS records", pt: "Cria e atualiza registros DNS proxied" },
      { en: "Add a Cloudflare Tunnel ingress route to the workload", pt: "Adiciona uma rota de ingress no Cloudflare Tunnel para o workload" },
      { en: "Gate the domain behind Zero-Trust Access (allow-list + one-time PIN)", pt: "Protege o domínio com Zero-Trust Access (allow-list + PIN de uso único)" },
      { en: "Automatic TLS at the edge — no certificates to manage", pt: "TLS automático na borda — sem certificados pra gerenciar" },
      { en: "Clean teardown — the route and DNS are removed on uninstall", pt: "Desmonte limpo — a rota e o DNS são removidos ao desinstalar" },
    ],
    boundaries: [
      { en: "Called by the platform Brain's deployment tooling; Assistants never receive Cloudflare credentials", pt: "Chamado pelas ferramentas de deploy do Cérebro da plataforma; Assistants nunca recebem credenciais Cloudflare" },
      { en: "May create its own proxied DNS record and append its own tunnel route", pt: "Pode criar o próprio registro DNS proxied e acrescentar a própria rota no túnel" },
    ],
  },
  {
    id: "postgres", name: "Postgres", category: "Data", icon: "database", brand: "#336791",
    summary: { en: "Provision an isolated database for one admitted workload.", pt: "Provisiona um banco isolado para um workload admitido." },
    blurb: {
      en: "The current internal lifecycle can provision one least-privilege Postgres database (proj_<name>) per admitted workload. Assistant Spec v1 does not claim this binding until its Capsule controller enforces it.",
      pt: "O lifecycle interno atual pode provisionar um banco Postgres de menor privilégio (proj_<name>) por workload admitido. A Assistant Spec v1 não declara esse binding até o controller da Cápsula aplicá-lo.",
    },
    features: [
      { en: "A dedicated database (proj_<name>), provisioned on install", pt: "Um banco dedicado (proj_<name>), provisionado na instalação" },
      { en: "A least-privilege role scoped to that database only", pt: "Um papel de menor privilégio restrito só àquele banco" },
      { en: "Full read/write, schema and migrations within its own database", pt: "Leitura/escrita completa, schema e migrações no próprio banco" },
      { en: "A scoped connection for the admitted workload — never an administrator credential", pt: "Uma conexão restrita ao workload admitido — nunca uma credencial de administrador" },
      { en: "Fully isolated from another workload's data and from platform data", pt: "Totalmente isolado dos dados de outro workload e dos dados da plataforma" },
      { en: "Dropped cleanly on uninstall", pt: "Removido de forma limpa ao desinstalar" },
    ],
    boundaries: [
      { en: "Current internal App compatibility only; Assistant binding is not released", pt: "Somente compatibilidade interna de App; o binding para Assistant não foi lançado" },
      { en: "No platform or Postgres administrator credential enters a tenant workload", pt: "Nenhuma credencial da plataforma ou de administrador Postgres entra em um workload do tenant" },
    ],
  },
  {
    id: "bus", name: "Event Bus", category: "Integration", icon: "event-bus", brand: "#E4462B",
    summary: { en: "Async events, queues and retries.", pt: "Eventos async, filas e retries." },
    blurb: {
      en: "The existing workspace runtime publishes and consumes events with at-least-once delivery, a dead-letter queue and retries. Capsule Assistants are not connected to this bus yet.",
      pt: "O runtime de workspace existente publica e consome eventos com entrega at-least-once, dead-letter queue e retries. Assistants de Cápsula ainda não estão conectados a esse bus.",
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
      { en: "Workspace Apps publish only to their own <name>.* topics", pt: "Apps de workspace publicam apenas nos próprios tópicos <name>.*" },
      { en: "Capsule Assistants have no bus principal or Service operation grant today", pt: "Assistants de Cápsula ainda não têm principal no bus nem grant de operação de Service" },
    ],
  },
  {
    id: "storage", name: "Object Storage", category: "Data", icon: "object-storage", brand: "#F6821F",
    summary: { en: "Brain-side artifact storage and share links.", pt: "Armazenamento de artefatos e links para o Cérebro." },
    blurb: {
      en: "The platform Brain uses the audited R2 sidecar to upload, list and retrieve artifacts. This operator-managed capability is not exposed as an Assistant permission.",
      pt: "O Cérebro da plataforma usa o sidecar R2 auditado para enviar, listar e buscar artefatos. Essa capacidade gerenciada pelo operador não é exposta como permissão de Assistant.",
    },
    features: [
      { en: "Upload one Brain-selected file (PDF, image or export)", pt: "Envia um arquivo selecionado pelo Cérebro (PDF, imagem ou export)" },
      { en: "List a prefix and download one bounded object", pt: "Lista um prefixo e baixa um objeto com tamanho limitado" },
      { en: "Generate signed, time-limited share links", pt: "Gera links de compartilhamento assinados e com validade" },
      { en: "Keep R2 credentials inside the audited sidecar", pt: "Mantém as credenciais R2 dentro do sidecar auditado" },
    ],
    boundaries: [
      { en: "Platform Brain only; no Assistant manifest grant or Assistant route exists", pt: "Somente o Cérebro da plataforma; não existe grant de manifesto nem rota para Assistants" },
      { en: "The Brain-facing API has upload, list and get operations, but no delete operation", pt: "A API voltada ao Cérebro oferece upload, list e get, mas não oferece delete" },
    ],
  },
  {
    id: "openai", name: "OpenAI", category: "AI", icon: "neural-media", brand: "#10A37F",
    summary: { en: "Platform media generation and voice processing.", pt: "Geração de mídia e processamento de voz da plataforma." },
    blurb: {
      en: "The platform Brain's image tool and Telegram voice gateway call the audited OpenAI sidecar. This media capability is not exposed as an Assistant permission.",
      pt: "A ferramenta de imagens do Cérebro da plataforma e o gateway de voz do Telegram chamam o sidecar OpenAI auditado. Essa capacidade de mídia não é exposta como permissão de Assistant.",
    },
    features: [
      { en: "Image generation (gpt-image)", pt: "Geração de imagens (gpt-image)" },
      { en: "Speech-to-text transcription", pt: "Transcrição de fala para texto" },
      { en: "Text-to-speech voice", pt: "Voz de texto para fala" },
      { en: "The OpenAI sidecar holds the media API key", pt: "O sidecar OpenAI guarda a chave de API de mídia" },
      { en: "Requests are audited", pt: "As requisições são auditadas" },
    ],
    boundaries: [
      { en: "Platform Brain and Telegram gateway only; no Assistant manifest grant or Assistant route exists", pt: "Somente o Cérebro da plataforma e o gateway do Telegram; não existe grant de manifesto nem rota para Assistants" },
      { en: "Only allow-listed image, transcription and speech operations are accepted", pt: "Somente operações permitidas de imagem, transcrição e fala são aceitas" },
    ],
  },
  {
    id: "proxy", name: "Residential Proxy", category: "Network", icon: "secure-route",
    summary: { en: "Optional residential egress for the platform Browser.", pt: "Egress residencial opcional para o Browser da plataforma." },
    blurb: {
      en: "When the operator configures IPRoyal credentials, the Browser container routes Chrome through that residential upstream. This is a Browser setting, not an Assistant egress permission.",
      pt: "Quando o operador configura credenciais IPRoyal, o container do Browser roteia o Chrome por esse upstream residencial. Essa é uma configuração do Browser, não uma permissão de egress para Assistants.",
    },
    features: [
      { en: "Optionally route Chrome through a configured residential ISP upstream", pt: "Opcionalmente roteia o Chrome por um upstream residencial configurado" },
      { en: "Use a local authenticated relay because Chrome does not accept upstream proxy credentials", pt: "Usa um relay local autenticado porque o Chrome não aceita credenciais do proxy upstream" },
      { en: "Select one configured upstream when the Browser starts", pt: "Seleciona um upstream configurado quando o Browser inicia" },
      { en: "Keep residential proxy credentials inside the Browser container", pt: "Mantém as credenciais do proxy residencial dentro do container do Browser" },
    ],
    boundaries: [
      { en: "Browser container only; Assistants never receive this egress path or its credentials", pt: "Somente o container do Browser; Assistants nunca recebem esse caminho de egress nem suas credenciais" },
      { en: "Assistant egress uses the separate destination-allowlisted proxy", pt: "O egress de Assistants usa o proxy separado com destinos permitidos" },
    ],
  },
];

export const DRIVER_BY_ID = new Map(DRIVERS.map((d) => [d.id, d]));

// Canonical public names. Driver-named exports remain compatibility aliases for existing runtime
// payloads and routes while the migration happens without a breaking wire-contract rename.
export type Service = Driver;
export const SERVICES: Service[] = DRIVERS;
export const SERVICE_BY_ID = DRIVER_BY_ID;

// ── Assistants (public presentation; execution policy remains controller-owned) ─────────────────
// The Store intentionally exposes product facts only. Image references, digests, ports and runtime
// privileges never enter browser code; the Capsule controller resolves an ID against its own trusted
// registry. This keeps the public and embedded Store on one codebase without making it an authority.
export interface AssistantPower {
  id: string;
  name: I18n;
  summary: I18n;
}

export interface AssistantListing {
  id: string;
  name: string;
  version: string;
  creator: string;
  summary: I18n;
  description: I18n;
  price: "free";
  archs: Arch[];
  powers: AssistantPower[];
  permissions: string[];
}

export const ASSISTANT_CATALOG: AssistantListing[] = [
  {
    id: "hello-pulse",
    name: "Hello Pulse",
    version: "0.1.0",
    creator: "julianoamg",
    summary: {
      en: "Validate a Capsule with one safe hello Power.",
      pt: "Valide uma Cápsula com um Power hello seguro.",
    },
    description: {
      en: "Use Hello Pulse to validate a complete contextual install, invoke and uninstall flow without credentials, Services or internet access.",
      pt: "Use o Hello Pulse para validar um fluxo contextual completo de instalação, execução e desinstalação sem credenciais, Services ou acesso à internet.",
    },
    price: "free",
    archs: ["amd64", "arm64"],
    powers: [
      {
        id: "hello",
        name: { en: "Say hello", pt: "Dizer olá" },
        summary: {
          en: "Returns a typed greeting for one bounded name.",
          pt: "Retorna uma saudação tipada para um nome limitado.",
        },
      },
    ],
    permissions: [],
  },
];

export const ASSISTANT_BY_ID = new Map(ASSISTANT_CATALOG.map((assistant) => [assistant.id, assistant]));

// ── Apps (legacy internal operational inventory only) ───────────────────────────────────────────
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

// Runtime status and installed-Assistant controls still come from the legacy capsule-driver API.
export const APPS: App[] = [];
export type Assistant = App;
export const ASSISTANTS: Assistant[] = APPS;

// ── Creators ─────────────────────────────────────────────────────────────────────────
// A Creator owns platform artifacts such as Services. GitHub identity is explicit catalog metadata;
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
      en: "Creator of Shimpz and its default audited platform Services.",
      pt: "Criador do Shimpz e de seus Services de plataforma auditados padrão.",
    },
  },
];

export const CREATOR_BY_HANDLE = new Map(CREATORS.map((c) => [c.handle, c]));
export const driversByCreator = (handle: string): Driver[] => DRIVERS.filter((d) => creatorOf(d) === handle);
export const servicesByCreator = (handle: string): Service[] => SERVICES.filter((service) => creatorOf(service) === handle);

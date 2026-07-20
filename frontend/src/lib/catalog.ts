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
  | "neural-media";

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
      en: "The current internal lifecycle can provision one least-privilege Postgres database (proj_<name>) per admitted workload. Assistant Spec v2 can request the Service operation, but the generic runtime binding is not released yet.",
      pt: "O lifecycle interno atual pode provisionar um banco Postgres de menor privilégio (proj_<name>) por workload admitido. A Assistant Spec v2 pode solicitar a operação do Service, mas o binding genérico de runtime ainda não foi lançado.",
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
      en: "The existing workspace runtime publishes and consumes events with at-least-once delivery, a dead-letter queue and retries. Team Assistants are not connected to this bus yet.",
      pt: "O runtime de workspace existente publica e consome eventos com entrega at-least-once, dead-letter queue e retries. Assistants de Time ainda não estão conectados a esse bus.",
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
      { en: "Team Assistants have no bus principal or Service operation grant today", pt: "Assistants de Time ainda não têm principal no bus nem grant de operação de Service" },
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
    summary: { en: "Audited image, transcription, and speech operations.", pt: "Operações auditadas de imagem, transcrição e voz." },
    blurb: {
      en: "The audited OpenAI media sidecar implements allow-listed image generation, speech-to-text transcription, and text-to-speech. These operations are not yet exposed through an Assistant Power.",
      pt: "O sidecar auditado de mídia OpenAI implementa geração de imagens, transcrição de voz em texto e conversão de texto em voz permitidas. Essas operações ainda não são expostas por um Power de Assistant.",
    },
    features: [
      { en: "Image generation (gpt-image)", pt: "Geração de imagens (gpt-image)" },
      { en: "Speech-to-text transcription", pt: "Transcrição de fala para texto" },
      { en: "Text-to-speech voice", pt: "Voz de texto para fala" },
    ],
    boundaries: [
      { en: "Every request is audited; the media API key remains inside the sidecar", pt: "Toda requisição é auditada; a chave de API de mídia permanece dentro do sidecar" },
      { en: "No Assistant Power or Assistant route exposes these operations yet", pt: "Nenhum Power nem rota de Assistant expõe essas operações ainda" },
      { en: "Only allow-listed image, transcription and speech operations are accepted", pt: "Somente operações permitidas de imagem, transcrição e fala são aceitas" },
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
// privileges never enter browser code; the Team controller resolves an ID against its own trusted
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
  permissions: I18n[];
}

export const ASSISTANT_CATALOG: AssistantListing[] = [
  {
    id: "shimpz-assistant",
    name: "Shimpz Assistant",
    version: "0.2.0",
    creator: "roxygens",
    summary: {
      en: "Connect X through four typed Powers with just-in-time credentials and explicit approval for every write.",
      pt: "Conecte o X por quatro Powers tipados, com credenciais solicitadas apenas quando necessárias e aprovação explícita para cada escrita.",
    },
    description: {
      en: "Read public X profiles, inspect the connected account, and create or delete its Posts. The Admin requests only the secrets declared by the selected Power, every write requires explicit approval, and network access is restricted to api.x.com.",
      pt: "Leia perfis públicos do X, consulte a conta conectada e crie ou exclua seus Posts. O Admin solicita apenas os secrets declarados pelo Power selecionado, toda escrita exige aprovação explícita e o acesso de rede é restrito a api.x.com.",
    },
    price: "free",
    archs: ["amd64", "arm64"],
    powers: [
      {
        id: "public-user-lookup",
        name: { en: "Public profile", pt: "Perfil público" },
        summary: {
          en: "Reads one public X profile by username with an app Bearer Token.",
          pt: "Consulta um perfil público do X pelo nome de usuário com um Bearer Token do app.",
        },
      },
      {
        id: "identity-me",
        name: { en: "Connected identity", pt: "Identidade conectada" },
        summary: {
          en: "Reads the identity of the connected X account with OAuth 1.0a.",
          pt: "Consulta a identidade da conta conectada do X com OAuth 1.0a.",
        },
      },
      {
        id: "create-post",
        name: { en: "Create Post", pt: "Criar Post" },
        summary: {
          en: "Publishes one Post only after explicit approval for that invocation.",
          pt: "Publica um Post somente após aprovação explícita para aquela execução.",
        },
      },
      {
        id: "delete-post",
        name: { en: "Delete Post", pt: "Excluir Post" },
        summary: {
          en: "Deletes one owned Post only after explicit approval for that invocation.",
          pt: "Exclui um Post próprio somente após aprovação explícita para aquela execução.",
        },
      },
    ],
    permissions: [
      {
        en: "Egress: api.x.com only",
        pt: "Egress: somente api.x.com",
      },
      {
        en: "Secrets: requested just in time per Power (X Bearer Token or four OAuth 1.0a credentials)",
        pt: "Secrets: solicitados apenas quando necessários por Power (Bearer Token do X ou quatro credenciais OAuth 1.0a)",
      },
      {
        en: "Writes: explicit approval for every Create Post or Delete Post invocation",
        pt: "Escritas: aprovação explícita para cada execução de Criar Post ou Excluir Post",
      },
    ],
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

// Runtime status and installed-Assistant controls come from the Team controller API.
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

// The Shimpz capability catalog is the source of truth for public Service documentation. The legacy
// App shape at the end of this file is a separate, neutral runtime-policy inventory contract. It is
// not consumed by rendered frontend code and does not describe or publish products.

export const LOCALES = ["en", "pt"] as const;
export type Locale = (typeof LOCALES)[number];
export type I18n = Record<Locale, string>;
export const t = (v: I18n, l: Locale): string => v[l] ?? v.en;

// ── Services (audited platform capability inventory) ────────────────────────────────────────────
export type DriverCategory = "Data" | "Network" | "Dev" | "Automation";

export type ServiceIconName = "database";

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
    id: "shimpz-cloudflare",
    name: "Shimpz Cloudflare",
    version: "0.1.5",
    creator: "roxygens",
    summary: {
      en: "List Cloudflare zones and inspect DNS records with a least-privilege OAuth Account.",
      pt: "Liste zonas do Cloudflare e inspecione registros DNS com uma Account OAuth de privilégio mínimo.",
    },
    description: {
      en: "Connect one Cloudflare Account through OAuth and use two read-only Powers to list a bounded page of zones or DNS records. The token is delivered only to the selected Power invocation, and egress is limited to api.cloudflare.com.",
      pt: "Conecte uma Account do Cloudflare por OAuth e use dois Powers somente de leitura para listar uma página limitada de zonas ou registros DNS. O token é entregue apenas à execução do Power selecionado, e o egress é limitado a api.cloudflare.com.",
    },
    price: "free",
    archs: ["amd64", "arm64"],
    powers: [
      {
        id: "list-zones",
        name: { en: "List zones", pt: "Listar zonas" },
        summary: {
          en: "Lists one bounded page of Cloudflare zones and domains.",
          pt: "Lista uma página limitada de zonas e domínios do Cloudflare.",
        },
      },
      {
        id: "list-dns-records",
        name: { en: "List DNS records", pt: "Listar registros DNS" },
        summary: {
          en: "Lists one bounded page of DNS records for an exact zone.",
          pt: "Lista uma página limitada de registros DNS para uma zona exata.",
        },
      },
    ],
    permissions: [
      {
        en: "Allowed host: api.cloudflare.com only",
        pt: "Host permitido: somente api.cloudflare.com",
      },
      {
        en: "Account: controller-owned Cloudflare OAuth with zone.read, dns.read and offline_access",
        pt: "Account: OAuth do Cloudflare sob custódia do controller com zone.read, dns.read e offline_access",
      },
      {
        en: "Approval: both Powers are read-only and require no execution approval",
        pt: "Aprovação: ambos os Powers são somente de leitura e não exigem aprovação de execução",
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

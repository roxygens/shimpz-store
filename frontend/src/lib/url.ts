// Public URLs for the implemented product and platform-capability surfaces.
import type { AssistantListing, Driver, Locale, Service } from "$lib/catalog";

export const SITE = "https://shimpz.com";

export const u = {
  home: (l: Locale) => `/${l}`,
  services: (l: Locale) => `/${l}/services`,
  service: (l: Locale, service: Service) => `/${l}/services/${service.id}`,
  assistants: (l: Locale) => `/${l}/assistants`,
  assistant: (l: Locale, assistant: AssistantListing) => `/${l}/assistants/${assistant.id}`,
  // Legacy public URLs retained for redirect compatibility while runtime contracts still use
  // driver/app names internally.
  drivers: (l: Locale) => `/${l}/drivers`,
  driver: (l: Locale, d: Driver) => `/${l}/drivers/${d.id}`,
  team: (l: Locale) => `/${l}/team`,
  chat: (l: Locale, teamId?: string) =>
    `/${l}/chat${teamId ? `?team=${encodeURIComponent(teamId)}` : ""}`,
  login: (l: Locale) => `/${l}/login`,
  account: (l: Locale) => `/${l}/account`,
  creators: (l: Locale) => `/${l}/creators`,
  creator: (l: Locale, handle: string) => `/${l}/creators/${handle}`,
};

// Same page in another locale — swaps the leading /<lang>/ segment (for hreflang + the language switch).
export const swapLocale = (path: string, target: Locale): string =>
  path.replace(/^\/[a-z]{2}(\/|$)/, `/${target}$1`);

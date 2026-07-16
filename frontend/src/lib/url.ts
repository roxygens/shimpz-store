// Public URLs for the implemented product and platform-capability surfaces.
import type { Driver, Locale, Service } from "$lib/catalog";

export const SITE = "https://shimpz.com";

export const u = {
  home: (l: Locale) => `/${l}`,
  services: (l: Locale) => `/${l}/services`,
  service: (l: Locale, service: Service) => `/${l}/services/${service.id}`,
  assistants: (l: Locale) => `/${l}/assistants`,
  // Legacy public URLs retained for redirect compatibility while runtime contracts still use
  // driver/app names internally.
  drivers: (l: Locale) => `/${l}/drivers`,
  driver: (l: Locale, d: Driver) => `/${l}/drivers/${d.id}`,
  capsule: (l: Locale) => `/${l}/capsule`,
  chat: (l: Locale, capsule?: string) =>
    `/${l}/chat${capsule ? `?capsule=${encodeURIComponent(capsule)}` : ""}`,
  login: (l: Locale) => `/${l}/login`,
  account: (l: Locale) => `/${l}/account`,
  creators: (l: Locale) => `/${l}/creators`,
  creator: (l: Locale, handle: string) => `/${l}/creators/${handle}`,
};

// Same page in another locale — swaps the leading /<lang>/ segment (for hreflang + the language switch).
export const swapLocale = (path: string, target: Locale): string =>
  path.replace(/^\/[a-z]{2}(\/|$)/, `/${target}$1`);

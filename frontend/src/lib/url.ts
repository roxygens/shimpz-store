// Public URLs for the implemented product and platform-capability surfaces.
import type { Driver, Locale } from "$lib/catalog";

export const SITE = "https://shimpz.com";

export const u = {
  home: (l: Locale) => `/${l}`,
  drivers: (l: Locale) => `/${l}/drivers`,
  driver: (l: Locale, d: Driver) => `/${l}/drivers/${d.id}`,
  capsule: (l: Locale) => `/${l}/capsule`,
  chat: (l: Locale) => `/${l}/chat`,
  login: (l: Locale) => `/${l}/login`,
  account: (l: Locale) => `/${l}/account`,
  creators: (l: Locale) => `/${l}/creators`,
  creator: (l: Locale, handle: string) => `/${l}/creators/${handle}`,
};

// Same page in another locale — swaps the leading /<lang>/ segment (for hreflang + the language switch).
export const swapLocale = (path: string, target: Locale): string =>
  path.replace(/^\/[a-z]{2}(\/|$)/, `/${target}$1`);

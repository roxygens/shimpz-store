// Composite English URLs + the helpers that make every page link to the related ones (link building).
import { catSlug, type App, type Driver, type AppCategory, type Locale } from "$lib/catalog";

export const SITE = "https://shimpz.com";

export const u = {
  home: (l: Locale) => `/${l}`,
  apps: (l: Locale) => `/${l}/apps`,
  category: (l: Locale, c: AppCategory) => `/${l}/apps/${catSlug(c)}`,
  app: (l: Locale, a: App) => `/${l}/apps/${catSlug(a.category)}/${a.id}`,
  drivers: (l: Locale) => `/${l}/drivers`,
  driver: (l: Locale, d: Driver) => `/${l}/drivers/${d.id}`,
  capsule: (l: Locale) => `/${l}/capsule`,
  chat: (l: Locale) => `/${l}/chat`,
  install: (l: Locale) => `/${l}/install`,
};

// Same page in another locale — swaps the leading /<lang>/ segment (for hreflang + the language switch).
export const swapLocale = (path: string, target: Locale): string =>
  path.replace(/^\/[a-z]{2}(\/|$)/, `/${target}$1`);

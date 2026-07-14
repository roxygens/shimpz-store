import { LOCALES } from "$lib/catalog";

export const prerender = true;

export function entries() {
  return LOCALES.map((lang) => ({ lang }));
}

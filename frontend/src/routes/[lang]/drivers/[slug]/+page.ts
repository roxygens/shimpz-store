import { error } from "@sveltejs/kit";
import { LOCALES, DRIVERS, DRIVER_BY_ID, type Locale } from "$lib/catalog";

export const prerender = true;

export function entries() {
  const out: { lang: string; slug: string }[] = [];
  for (const lang of LOCALES) for (const d of DRIVERS) out.push({ lang, slug: d.id });
  return out;
}

export function load({ params }: { params: { lang: string; slug: string } }) {
  const d = DRIVER_BY_ID.get(params.slug);
  if (!d) error(404, "driver not found");
  return { lang: params.lang as Locale, driver: d };
}

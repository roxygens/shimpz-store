import { error } from "@sveltejs/kit";
import { LOCALES, CREATORS, CREATOR_BY_HANDLE, driversByCreator, type Locale } from "$lib/catalog";

export const prerender = true;

export function entries() {
  const out: { lang: string; handle: string }[] = [];
  for (const lang of LOCALES) for (const c of CREATORS) out.push({ lang, handle: c.handle });
  return out;
}

export function load({ params }: { params: { lang: string; handle: string } }) {
  const c = CREATOR_BY_HANDLE.get(params.handle);
  if (!c) error(404, "creator not found");
  return {
    lang: params.lang as Locale,
    creator: c,
    drivers: driversByCreator(c.handle),
  };
}

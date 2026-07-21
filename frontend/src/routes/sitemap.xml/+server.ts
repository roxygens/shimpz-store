import { ASSISTANT_CATALOG, LOCALES, SERVICES } from "$lib/catalog";
import { SITE, u } from "$lib/url";

export const prerender = true;

export function GET() {
  const paths: string[] = [];
  paths.push("/privacy", "/terms");
  for (const l of LOCALES) {
    paths.push(u.home(l), u.services(l), u.assistants(l));
    for (const service of SERVICES) paths.push(u.service(l, service));
    for (const assistant of ASSISTANT_CATALOG) paths.push(u.assistant(l, assistant));
  }
  const body =
    '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    paths.map((p) => `  <url><loc>${SITE}${p}</loc></url>`).join("\n") +
    "\n</urlset>\n";
  return new Response(body, { headers: { "content-type": "application/xml" } });
}

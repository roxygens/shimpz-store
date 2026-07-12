"""Shimpz storefront — the marketplace front door, served at shimpz.com.

Minimum-viable + server-rendered (no build step): browse the app catalog by category and open an app's
page. It's a public, read-only marketing surface (no auth, no private data — secaudit-SAFE by design).
The layers it fronts (accounts, DB-backed catalog, publish pipeline, install-into-tenant) evolve behind
this same surface. Payment is a separate layer at pay.shimpz.com; installed apps live at
<slug>.grid.shimpz.com.
"""

from __future__ import annotations

import html

import shimpzbus
import structlog
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from app import catalog
from app.logconf import setup

setup("shimpz")
log = structlog.get_logger()

app = FastAPI(title="Shimpz", docs_url=None, redoc_url=None, openapi_url=None)

_STYLE = """
:root{--bg:#0a0b10;--panel:#12131b;--line:#20222e;--txt:#e7e9f3;--dim:#9aa0b4;--accent:#5eead4;--accent2:#a78bfa}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);
font:16px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:inherit;text-decoration:none}.wrap{max-width:1040px;margin:0 auto;padding:0 1.2rem}
header{border-bottom:1px solid var(--line);position:sticky;top:0;
background:rgba(10,11,16,.85);backdrop-filter:blur(8px);z-index:5}
.bar{display:flex;align-items:center;gap:.7rem;padding:1rem 0}
.logo{font-weight:800;font-size:1.15rem;letter-spacing:.3px}.logo b{color:var(--accent)}
.tag{color:var(--dim);font-size:.85rem}
.hero{padding:3.2rem 0 2rem}.hero h1{font-size:2.5rem;line-height:1.1;margin:0 0 .6rem;letter-spacing:-.02em}
.hero h1 span{background:linear-gradient(90deg,var(--accent),var(--accent2));
-webkit-background-clip:text;background-clip:text;color:transparent}
.hero p{color:var(--dim);font-size:1.1rem;max-width:640px;margin:0}
.cat{margin:2.2rem 0 1rem;font-size:.8rem;text-transform:uppercase;letter-spacing:.14em;color:var(--dim)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:1rem}
.card{display:block;background:var(--panel);border:1px solid var(--line);
border-radius:14px;padding:1.15rem 1.2rem;transition:border-color .15s,transform .05s}
.card:hover{border-color:var(--accent);transform:translateY(-2px)}
.card .nm{font-weight:700;font-size:1.05rem;margin-bottom:.25rem}
.card .bl{color:var(--dim);font-size:.92rem;min-height:2.8em}
.pill{display:inline-block;margin-top:.7rem;font-size:.72rem;color:var(--accent);border:1px solid var(--line);
border-radius:999px;padding:.15rem .6rem}
.soon{color:var(--dim);border-color:var(--line)}
footer{border-top:1px solid var(--line);margin-top:4rem;padding:2rem 0;color:var(--dim);font-size:.85rem}
footer a{color:var(--accent)}
.detail{padding:2.4rem 0}.detail h1{font-size:2rem;margin:.2rem 0 .4rem}.detail .lead{color:var(--dim);font-size:1.1rem}
.detail p{max-width:680px}.back{color:var(--dim);font-size:.9rem}
.needs{display:flex;flex-wrap:wrap;gap:.5rem;margin:1rem 0}
.need{font-size:.82rem;background:var(--panel);border:1px solid var(--line);
border-radius:8px;padding:.3rem .6rem;color:var(--dim)}
.install{display:inline-block;margin-top:1.4rem;
background:linear-gradient(90deg,var(--accent),var(--accent2));
color:#04121a;font-weight:700;border-radius:10px;padding:.7rem 1.3rem}
code{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:.1rem .4rem;font-size:.9em}
"""


def _page(title: str, body: str) -> str:
    return (
        f"<!doctype html><html lang=en><head><meta charset=utf-8>"
        f"<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head><body>"
        f"<header><div class='wrap bar'><a class=logo href='/'>Ship<b>Base</b></a>"
        f"<span class=tag>· app marketplace for your Shimpz</span></div></header>{body}"
        f"<footer><div class=wrap>Shimpz · apps install into your own Shimpz · payments via "
        f"<a href='https://pay.shimpz.com'>ShimpzPay</a></div></footer></body></html>"
    )


def _card(a: catalog.App) -> str:
    e = html.escape
    pill = f"<span class=pill>{e(a.price)}</span>" if a.available else "<span class='pill soon'>Coming soon</span>"
    return (
        f"<a class=card href='/app/{e(a.slug)}'><div class=nm>{e(a.name)}</div>"
        f"<div class=bl>{e(a.blurb)}</div>{pill}</a>"
    )


@app.get("/", response_class=HTMLResponse)
def storefront() -> HTMLResponse:
    log.info("storefront_view", apps=len(catalog.APPS))
    sections = ""
    for cat, apps in catalog.by_category().items():
        cards = "".join(_card(a) for a in apps)
        sections += f"<div class=cat>{html.escape(cat)}</div><div class=grid>{cards}</div>"
    body = (
        "<div class='wrap hero'><h1>Install <span>apps</span> into your Shimpz.</h1>"
        "<p>Each app is an installable capability package — its own business rules and micro-skills, "
        "installed securely, running in your own isolated environment. Browse, install, done.</p></div>"
        f"<div class=wrap>{sections}</div>"
    )
    return HTMLResponse(_page("Shimpz — app marketplace", body))


@app.get("/app/{slug}", response_class=HTMLResponse)
def app_page(slug: str) -> HTMLResponse:
    a = catalog.BY_SLUG.get(slug)
    if a is None:
        return HTMLResponse(_page("Not found", "<div class='wrap detail'><a class=back href='/'>← back</a>"
                                              "<h1>App not found</h1></div>"), status_code=404)
    e = html.escape
    needs = "".join(f"<span class=need>{e(n)}</span>" for n in a.needs)
    needs_block = f"<div class=cat>Includes</div><div class=needs>{needs}</div>" if a.needs else ""
    if a.available:
        install = (
            f"<button class=install style='border:none;cursor:pointer;font:inherit' "
            f"onclick=\"install('{e(a.slug)}')\">Install</button>"
            f"<p id=msg class=back style='margin-top:.8rem'>Runs at <code>{e(a.domain)}</code></p>"
            "<script>async function install(s){var m=document.getElementById('msg');m.textContent='Requesting…';"
            "try{var r=await fetch('/api/install/'+s,{method:'POST'});var j=await r.json();"
            "m.textContent=r.ok?('✓ '+j.note):('✗ '+(j.error||'failed'));}"
            "catch(e){m.textContent='✗ network error';}}</script>"
        )
    else:
        install = "<p class=back style='margin-top:1.4rem'>Coming soon.</p>"
    body = (
        f"<div class='wrap detail'><a class=back href='/'>← all apps</a>"
        f"<h1>{e(a.name)}</h1><div class=lead>{e(a.blurb)}</div>"
        f"<p style='margin-top:1.2rem'>{e(a.description)}</p>{needs_block}{install}</div>"
    )
    return HTMLResponse(_page(f"{a.name} — Shimpz", body))


@app.post("/api/install/{slug}")
def install(slug: str) -> JSONResponse:
    """Request an install of the store app `slug`.

    Publishes to the `shimpz.install` bus topic; the brain's installer worker asks the owner to approve
    (the store is PUBLIC → approval is the auth gate), then runs `shimpz-app install`.
    """
    a = catalog.BY_SLUG.get(slug)
    if a is None or not a.available:
        return JSONResponse({"error": "unknown app"}, status_code=404)
    shimpzbus.publish("shimpz.install", {"app": slug})
    log.info("install_requested", app=slug)
    return JSONResponse({"status": "requested", "app": slug, "note": "Shimpz will ask you to approve, then install it."})


@app.get("/api/apps")
def api_apps() -> JSONResponse:
    return JSONResponse(
        [
            {"slug": a.slug, "name": a.name, "category": a.category, "blurb": a.blurb,
             "domain": a.domain, "price": a.price, "available": a.available}
            for a in catalog.APPS
        ]
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

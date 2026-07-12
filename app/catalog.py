"""The Shimpz marketplace catalog — MVP seed.

In-process for the minimum-viable store (no DB yet); the publish pipeline replaces this with a
Postgres-backed, publisher-owned catalog in a later layer without changing the storefront.
"""

from __future__ import annotations

from dataclasses import dataclass

CATEGORIES = ("Marketing", "Content", "Commerce", "Automation")


@dataclass(frozen=True)
class App:
    slug: str
    name: str
    category: str
    blurb: str
    description: str
    needs: tuple[str, ...] = ()
    price: str = "Free"
    available: bool = True

    @property
    def domain(self) -> str:
        """Where an installed instance answers — the enforced <slug>.grid.shimpz.com convention."""
        return f"{self.slug}.grid.shimpz.com"


APPS: tuple[App, ...] = (
    App(
        slug="meta-ads-operator",
        name="Meta Ads Operator",
        category="Marketing",
        blurb="Launch, optimize and report on Meta ad campaigns — end to end.",
        description=(
            "An autonomous operator for Meta advertising. It reads your goals, drafts and launches "
            "campaigns, watches performance, and reports back — driving the browser, building landing "
            "pages, and firing Conversions API events, all with your approval on anything outward-facing."
        ),
        needs=("Browser", "Landing Page Builder", "Cloudflare", "Notification Center"),
        price="Paid · via ShimpzPay",
    ),
    App(
        slug="landing-page-builder",
        name="Landing Page Builder",
        category="Content",
        blurb="Generate and publish high-converting landing pages on your own domain.",
        description=(
            "Describe the offer; get a fast, beautiful, published landing page. Ships as a capability "
            "other apps (like Meta Ads Operator) install and reuse."
        ),
    ),
    App(
        slug="notification-center",
        name="Notification Center",
        category="Automation",
        blurb="Approvals, alerts and reports over Telegram — one place for human-in-the-loop.",
        description=(
            "The channel your apps use to ask for approval, report results, and alert you — with buttons "
            "and voice, restart-survivable."
        ),
    ),
)

BY_SLUG = {a.slug: a for a in APPS}


def by_category() -> dict[str, list[App]]:
    """Apps grouped by category, in CATEGORIES order (empty categories dropped)."""
    grouped: dict[str, list[App]] = {c: [] for c in CATEGORIES}
    for a in APPS:
        grouped.setdefault(a.category, []).append(a)
    return {c: apps for c, apps in grouped.items() if apps}

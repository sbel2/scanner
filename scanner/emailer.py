from __future__ import annotations

from collections import OrderedDict
from datetime import date
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import EMAIL_FROM, EMAIL_TO, RESEND_API_KEY
from .models import ScoredOpportunity

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)

CATEGORY_ORDER = ["funding", "research", "internship", "event", "other"]


def _group_by_category(items: list[ScoredOpportunity]) -> "OrderedDict[str, list[ScoredOpportunity]]":
    buckets: dict[str, list[ScoredOpportunity]] = {c: [] for c in CATEGORY_ORDER}
    for s in items:
        buckets.setdefault(s.opportunity.category, []).append(s)
    return OrderedDict((c, buckets[c]) for c in CATEGORY_ORDER if buckets.get(c))


def render(items: list[ScoredOpportunity], total_new: int, welcome: bool = False) -> tuple[str, str]:
    grouped = _group_by_category(items)
    template = _env.get_template("digest.html.j2")
    html = template.render(
        items=items,
        grouped=grouped,
        today=date.today().isoformat(),
        total=total_new,
        welcome=welcome,
    )
    subject = f"AI scan · {date.today().isoformat()} · {len(items)} picks"
    return subject, html


def send(items: list[ScoredOpportunity], total_new: int, welcome: bool = False) -> tuple[str, list[str]]:
    subject, html = render(items, total_new, welcome=welcome)

    archive = Path(__file__).resolve().parent.parent / "logs" / f"digest-{date.today().isoformat()}.html"
    archive.parent.mkdir(exist_ok=True)
    archive.write_text(html, encoding="utf-8")

    resend.api_key = RESEND_API_KEY
    params: resend.Emails.SendParams = {
        "from": EMAIL_FROM,
        "to": [EMAIL_TO],
        "subject": subject,
        "html": html,
    }
    resend.Emails.send(params)
    return subject, [s.opportunity.id for s in items]


def send_failure_alert(total_new: int, failed_scoring: int, sample_error: str) -> None:
    subject = f"AI scan · {date.today().isoformat()} · FAILED ({failed_scoring}/{total_new} scoring errors)"
    html = (
        f"<p>Scanner ran but <b>{failed_scoring} of {total_new}</b> items failed scoring.</p>"
        f"<p><b>Possible causes:</b> invalid or expired ANTHROPIC_API_KEY, rate limit, or network error.</p>"
        f"<p>Check your <code>.env</code> file and verify your API key is valid.</p>"
        f"<p><b>Sample error:</b><br><code>{sample_error}</code></p>"
    )
    resend.api_key = RESEND_API_KEY
    params: resend.Emails.SendParams = {
        "from": EMAIL_FROM,
        "to": [EMAIL_TO],
        "subject": subject,
        "html": html,
    }
    resend.Emails.send(params)

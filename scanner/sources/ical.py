from __future__ import annotations

import re
from datetime import date, datetime
from typing import Iterable

import httpx

from ..config import ICAL_FEEDS, LUMA_CALENDAR_IDS
from ..models import Opportunity

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; scanner/1.0)"}

LUMA_ICS = "https://api.lu.ma/ics/get?entity=calendar&id={id}"


def _unfold(text: str) -> list[str]:
    raw = text.replace("\r\n", "\n").split("\n")
    lines: list[str] = []
    for line in raw:
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def _unescape(s: str) -> str:
    return s.replace("\\,", ",").replace("\\;", ";").replace("\\n", "\n").replace("\\\\", "\\")


def _parse_dt(value: str) -> date | None:
    v = value.strip()
    if not v:
        return None
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _split_kv(line: str) -> tuple[str, str]:
    if ":" not in line:
        return "", ""
    key, _, value = line.partition(":")
    name = key.split(";", 1)[0].upper()
    return name, value


def parse_ics(text: str) -> list[dict]:
    events: list[dict] = []
    cur: dict | None = None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
        elif cur is not None:
            key, val = _split_kv(line)
            if key in ("SUMMARY", "DESCRIPTION", "LOCATION", "URL", "UID"):
                cur[key.lower()] = _unescape(val)
            elif key == "DTSTART":
                cur["dtstart"] = _parse_dt(val)
            elif key == "DTEND":
                cur["dtend"] = _parse_dt(val)
    return events


def _fetch(url: str) -> list[dict]:
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        return parse_ics(resp.text)
    except Exception as e:
        print(f"[ical] fetch failed for {url}: {e}")
        return []


def _to_opportunities(
    events: Iterable[dict],
    source_label: str,
    default_location: str | None,
) -> list[Opportunity]:
    today = date.today()
    out: list[Opportunity] = []
    for ev in events:
        title = (ev.get("summary") or "").strip()
        url = (ev.get("url") or "").strip()
        if not title or not url:
            continue
        starts = ev.get("dtstart")
        ends = ev.get("dtend") or starts
        if ends and ends < today:
            continue
        desc = (ev.get("description") or "").strip()
        loc = (ev.get("location") or default_location or "").strip() or None
        summary_parts = []
        if starts:
            summary_parts.append(f"Starts: {starts.isoformat()}.")
        if loc:
            summary_parts.append(f"Location: {loc}.")
        if desc:
            summary_parts.append(re.sub(r"\s+", " ", desc)[:500])
        out.append(
            Opportunity(
                title=title,
                url=url,
                source=source_label,
                category="event",
                summary=" ".join(summary_parts)[:800],
                deadline=ends,
                starts_at=starts,
                location=loc,
            )
        )
    return out


def collect_luma() -> list[Opportunity]:
    items: list[Opportunity] = []
    for cal_id in LUMA_CALENDAR_IDS:
        cal_id = cal_id.strip()
        if not cal_id:
            continue
        events = _fetch(LUMA_ICS.format(id=cal_id))
        items.extend(
            _to_opportunities(events, source_label=f"luma:{cal_id}", default_location=None)
        )
    return items


def collect_ical() -> list[Opportunity]:
    items: list[Opportunity] = []
    for feed in ICAL_FEEDS:
        name = feed.get("name", "ical")
        url = feed.get("url", "").strip()
        default_loc = feed.get("location")
        if not url:
            continue
        events = _fetch(url)
        items.extend(
            _to_opportunities(events, source_label=f"ical:{name}", default_location=default_loc)
        )
    return items

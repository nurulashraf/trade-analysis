"""Economic calendar (Forex Factory style).

Pulls the free weekly calendar XML that powers forexfactory.com
(published by faireconomy.media — no API key, refreshed weekly) and
normalises it. Falls back to a deterministic mock calendar so the app
keeps working fully offline, matching the rest of the project.

Feed times are GMT; the frontend renders them in the viewer's local time.
"""
from __future__ import annotations

import hashlib
import random
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
CACHE_TTL = 3600  # refresh at most hourly; the feed itself updates weekly

_cache: dict = {"ts": 0.0, "events": None, "source": None}


def _parse_feed(xml_text: str) -> list[dict]:
    events = []
    root = ET.fromstring(xml_text)
    for ev in root.iter("event"):
        get = lambda tag: (ev.findtext(tag) or "").strip()  # noqa: E731
        date_s, time_s = get("date"), get("time")
        ts, all_day = None, False
        try:
            dt = datetime.strptime(f"{date_s} {time_s}", "%m-%d-%Y %I:%M%p")
            ts = int(dt.replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            all_day = True  # "All Day", "Tentative", holidays, ...
            try:
                dt = datetime.strptime(date_s, "%m-%d-%Y")
                ts = int(dt.replace(tzinfo=timezone.utc).timestamp())
            except ValueError:
                continue
        events.append({
            "ts": ts,
            "all_day": all_day,
            "title": get("title"),
            "currency": get("country") or "ALL",
            "impact": get("impact") or "Low",   # High | Medium | Low | Holiday
            "forecast": get("forecast"),
            "previous": get("previous"),
        })
    events.sort(key=lambda e: e["ts"])
    return events


# Deterministic offline fallback: plausible recurring releases spread over
# the coming days so the UI always has something sensible to show.
_MOCK_TEMPLATE = [
    ("CPI y/y", "USD", "High", "3.1%", "3.4%"),
    ("Main Refinancing Rate", "EUR", "High", "2.40%", "2.40%"),
    ("Unemployment Claims", "USD", "Medium", "221K", "224K"),
    ("GDP m/m", "GBP", "High", "0.2%", "0.1%"),
    ("Trade Balance", "CNY", "Low", "612B", "598B"),
    ("Retail Sales m/m", "AUD", "Medium", "0.3%", "0.1%"),
    ("BOJ Policy Rate", "JPY", "High", "0.50%", "0.50%"),
    ("Crude Oil Inventories", "USD", "Low", "-2.1M", "-3.4M"),
    ("Overnight Policy Rate", "MYR", "Medium", "2.75%", "2.75%"),
    ("Manufacturing PMI", "EUR", "Medium", "49.8", "49.6"),
]


def _mock_events() -> list[dict]:
    day = int(time.time() // 86400)
    rng = random.Random(int(hashlib.sha256(str(day).encode()).hexdigest(), 16))
    base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    events = []
    for i, (title, ccy, impact, fc, prev) in enumerate(_MOCK_TEMPLATE):
        dt = base + timedelta(days=i % 5, hours=rng.choice([1, 3, 6, 9, 13]))
        events.append({
            "ts": int(dt.timestamp()), "all_day": False, "title": title,
            "currency": ccy, "impact": impact, "forecast": fc, "previous": prev,
        })
    events.sort(key=lambda e: e["ts"])
    return events


def get_calendar() -> dict:
    """Returns {source, fetched_at, events}. Live feed when reachable, mock otherwise."""
    now = time.time()
    if _cache["events"] is not None and now - _cache["ts"] < CACHE_TTL:
        return {"source": _cache["source"], "fetched_at": _cache["ts"], "events": _cache["events"]}
    try:
        req = urllib.request.Request(FEED_URL, headers={"User-Agent": "konsensus/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            events = _parse_feed(resp.read().decode("windows-1252", errors="replace"))
        source = "forexfactory-weekly"
    except Exception:
        if _cache["events"] is not None:  # serve stale rather than mock
            return {"source": _cache["source"], "fetched_at": _cache["ts"], "events": _cache["events"]}
        events, source = _mock_events(), "mock"
    _cache.update(ts=now, events=events, source=source)
    return {"source": source, "fetched_at": now, "events": events}

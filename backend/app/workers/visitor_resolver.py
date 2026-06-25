"""Visitor → company resolver (F1).

Runs as an Arq cron every 5 minutes. Reads recent unresolved `VisitorEvent`
rows, groups by IP, looks up the ASN via the optional IP2Location LITE
DB-ASN CSV, and writes `LeadCandidate(source='visitor_pixel')` rows for
ASNs that look like real companies (not residential ISPs). 24h dedupe.
"""
from __future__ import annotations

import csv
import ipaddress
import logging
import os
import time
import uuid
from bisect import bisect_right
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import LeadCandidate, VisitorEvent

logger = logging.getLogger(__name__)

_RESIDENTIAL_HINTS = (
    "comcast", "spectrum", "verizon", "at&t", "att services", "t-mobile",
    "charter", "cox", "centurylink", "frontier", "windstream", "xfinity",
    "vodafone", "orange", "telefonica", "sky broadband", "deutsche telekom",
    "bt group", "virgin media",
)

# Loaded lazily: list of (start_int, end_int, asn, asn_name)
_ASN_TABLE: list[tuple[int, int, int, str]] | None = None
_ASN_STARTS: list[int] = []


def _load_asn_table() -> None:
    global _ASN_TABLE, _ASN_STARTS
    path = settings.ip2asn_db_path
    if not path or not os.path.exists(path):
        _ASN_TABLE = []
        _ASN_STARTS = []
        return
    table: list[tuple[int, int, int, str]] = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for row in csv.reader(fh):
            if len(row) < 4:
                continue
            try:
                start = int(row[0])
                end = int(row[1])
                asn = int(row[2]) if row[2].isdigit() else 0
            except ValueError:
                continue
            name = row[3] if len(row) >= 4 else ""
            table.append((start, end, asn, name))
    table.sort(key=lambda t: t[0])
    _ASN_TABLE = table
    _ASN_STARTS = [t[0] for t in table]
    logger.info("Loaded %d IP→ASN rows from %s", len(table), path)


def _lookup_asn(ip: str) -> tuple[int, str] | None:
    if _ASN_TABLE is None:
        _load_asn_table()
    if not _ASN_TABLE:
        return None
    try:
        addr = int(ipaddress.IPv4Address(ip))
    except (ipaddress.AddressValueError, ValueError):
        return None
    idx = bisect_right(_ASN_STARTS, addr) - 1
    if idx < 0:
        return None
    start, end, asn, name = _ASN_TABLE[idx]
    if start <= addr <= end:
        return (asn, name)
    return None


def _looks_residential(name: str) -> bool:
    lower = name.lower()
    return any(hint in lower for hint in _RESIDENTIAL_HINTS)


async def task_resolve_visitors(ctx: dict[str, Any]) -> None:
    cutoff = int(time.time()) - 3600  # last hour
    dedup_window = int(time.time()) - 86_400  # 24h
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(VisitorEvent)
            .where(VisitorEvent.resolved_at.is_(None))
            .where(VisitorEvent.occurred_at >= cutoff)
        )
        events = list(rows.scalars().all())
        if not events:
            return

        by_ip: dict[str, list[VisitorEvent]] = {}
        for ev in events:
            if ev.ip:
                by_ip.setdefault(ev.ip, []).append(ev)

        now = int(time.time())
        for ip, ip_events in by_ip.items():
            asn = _lookup_asn(ip)
            for ev in ip_events:
                ev.resolved_at = now
            if not asn:
                continue
            _, asn_name = asn
            if not asn_name or _looks_residential(asn_name):
                continue

            recent = await session.execute(
                select(LeadCandidate)
                .where(LeadCandidate.source == "visitor_pixel")
                .where(LeadCandidate.source_ref == asn_name)
                .where(LeadCandidate.discovered_at >= dedup_window)
            )
            if recent.scalar_one_or_none():
                for ev in ip_events:
                    ev.resolved_company = asn_name
                continue

            session.add(LeadCandidate(
                id=str(uuid.uuid4()),
                source="visitor_pixel",
                source_ref=asn_name,
                company_name=asn_name,
                website=None,
                category=None,
                raw_payload={
                    "ip": ip,
                    "event_count": len(ip_events),
                    "first_url": ip_events[0].url,
                },
                status="pending",
                discovered_at=now,
            ))
            for ev in ip_events:
                ev.resolved_company = asn_name

        await session.commit()

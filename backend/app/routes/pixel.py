"""First-party visitor pixel (F1).

`POST /api/v1/pixel/track` is intentionally unauthenticated and accepts a
small payload from a `<script>`-injected pixel on the team's marketing site.
A background Arq cron resolves visitor IPs to companies via an IP→ASN
lookup and writes `LeadCandidate(source='visitor_pixel')` rows.
"""
from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.db import get_session
from app.models import VisitorEvent

router = APIRouter()


class PixelEvent(BaseModel):
    url: str
    referrer: str | None = None
    anonymous_id: str


@router.post("/track")
async def track(
    body: PixelEvent,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user_agent: str | None = Header(default=None, alias="User-Agent"),
):
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() \
        or (request.client.host if request.client else "")
    session.add(VisitorEvent(
        id=str(uuid.uuid4()),
        anonymous_id=body.anonymous_id[:128],
        url=body.url[:2048],
        referrer=(body.referrer or "")[:2048] or None,
        ip=ip[:64],
        user_agent=(user_agent or "")[:512] or None,
        occurred_at=int(time.time()),
    ))
    await session.commit()
    return Response(status_code=204)


_PIXEL_JS = """\
(function () {
  try {
    var KEY = 'lg_anon_id';
    var aid = localStorage.getItem(KEY);
    if (!aid) {
      aid = (crypto && crypto.randomUUID ? crypto.randomUUID() :
        Date.now().toString(36) + Math.random().toString(36).slice(2));
      localStorage.setItem(KEY, aid);
    }
    var payload = JSON.stringify({
      url: location.href,
      referrer: document.referrer || null,
      anonymous_id: aid
    });
    var url = (document.currentScript && document.currentScript.dataset.endpoint)
      || '/api/v1/pixel/track';
    if (navigator.sendBeacon) {
      navigator.sendBeacon(url, new Blob([payload], { type: 'application/json' }));
    } else {
      fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: payload, keepalive: true });
    }
  } catch (e) { /* swallow */ }
})();
"""


@router.get("/pixel.js")
async def pixel_js():
    return Response(content=_PIXEL_JS, media_type="application/javascript")

"""Reply / bounce poller (F3) — Arq cron, every 10 minutes.

For each enrollment with `status='enrolled'` and a `graph_conversation_id`
on its most-recent outbound message, query Graph for messages in that
conversation. Any message from someone other than the sender flips the
enrollment to `replied` and stops the sequence. NDR detection: subject
starts with 'Undeliverable:' AND from address starts with 'postmaster@'.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import AsyncSessionLocal
from app.models import OutboundMessage, SequenceEnrollment
from app.services.outreach import graph_mailer

logger = logging.getLogger(__name__)


def _iso_from_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def task_poll_replies(ctx: dict[str, Any]) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SequenceEnrollment)
            .options(selectinload(SequenceEnrollment.messages))
            .where(SequenceEnrollment.status == "enrolled")
        )
        enrollments = list(result.scalars().all())
        if not enrollments:
            return

        now = int(time.time())
        for enr in enrollments:
            sent_msgs = [m for m in enr.messages if m.status == "sent" and m.graph_conversation_id]
            if not sent_msgs:
                continue
            latest = max(sent_msgs, key=lambda m: m.sent_at or 0)
            token = graph_mailer.get_cached_graph_token(enr.enrolled_by_user_id)
            if not token:
                continue
            after = _iso_from_ts(latest.sent_at) if latest.sent_at else None
            try:
                replies = await graph_mailer.fetch_replies(
                    token, latest.graph_conversation_id, after_iso=after,
                )
            except Exception as exc:
                logger.debug("fetch_replies failed for %s: %s", enr.id, exc)
                continue
            if not replies:
                continue

            ndr = False
            for r in replies:
                subj = (r.get("subject") or "").lower()
                from_addr = (r.get("from", {}).get("emailAddress", {}).get("address") or "").lower()
                if subj.startswith("undeliverable:") or from_addr.startswith("postmaster@"):
                    ndr = True
                    break

            if ndr:
                enr.status = "bounced"
                enr.next_send_at = None
                latest.bounce_at = now
            else:
                enr.status = "replied"
                enr.next_send_at = None
                latest.reply_at = now

        await session.commit()

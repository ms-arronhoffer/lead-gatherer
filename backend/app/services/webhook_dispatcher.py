"""Outbound webhook dispatcher with HMAC signing + exponential-backoff retries."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import Webhook, WebhookDelivery

logger = logging.getLogger(__name__)

# Retry schedule in seconds: 1m, 5m, 30m, 2h, 12h
RETRY_DELAYS = [60, 300, 1800, 7200, 43200]
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1
REQUEST_TIMEOUT = 10.0
POLL_INTERVAL = 30.0


def sign_payload(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


async def enqueue_event(event: str, payload: dict) -> None:
    """Find all webhooks subscribed to `event` and create pending deliveries."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Webhook).where(Webhook.enabled.is_(True)))
        for hook in result.scalars().all():
            if event not in (hook.events or []):
                continue
            session.add(WebhookDelivery(
                id=str(uuid.uuid4()),
                webhook_id=hook.id,
                event=event,
                payload=payload,
                status="pending",
                attempt=0,
                next_retry_at=int(time.time()),
            ))
        await session.commit()


async def _attempt_delivery(
    session: AsyncSession,
    delivery: WebhookDelivery,
    hook: Webhook,
) -> None:
    body_obj = {
        "id": delivery.id,
        "event": delivery.event,
        "created_at": delivery.created_at,
        "data": delivery.payload,
    }
    body = json.dumps(body_obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = sign_payload(hook.secret, body)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "lead-gatherer-webhook/1.0",
        "X-LG-Event": delivery.event,
        "X-LG-Delivery": delivery.id,
        "X-LG-Signature": signature,
    }
    delivery.attempt += 1
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(hook.url, content=body, headers=headers)
        delivery.status_code = resp.status_code
        delivery.error = None
        if 200 <= resp.status_code < 300:
            delivery.status = "delivered"
            delivery.delivered_at = int(time.time())
            delivery.next_retry_at = None
            return
        raise RuntimeError(f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        delivery.error = str(exc)[:1000]
        retry_index = delivery.attempt - 1
        if retry_index < len(RETRY_DELAYS):
            delivery.status = "pending"
            delivery.next_retry_at = int(time.time()) + RETRY_DELAYS[retry_index]
        else:
            delivery.status = "failed"
            delivery.next_retry_at = None


async def _process_due_deliveries() -> None:
    now = int(time.time())
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.status == "pending")
            .where(WebhookDelivery.next_retry_at <= now)
            .limit(50)
        )
        deliveries = result.scalars().all()
        if not deliveries:
            return
        hook_ids = {d.webhook_id for d in deliveries}
        hooks_result = await session.execute(select(Webhook).where(Webhook.id.in_(hook_ids)))
        hooks = {h.id: h for h in hooks_result.scalars().all()}
        for delivery in deliveries:
            hook = hooks.get(delivery.webhook_id)
            if not hook or not hook.enabled:
                delivery.status = "failed"
                delivery.error = "webhook missing or disabled"
                delivery.next_retry_at = None
                continue
            await _attempt_delivery(session, delivery, hook)
        await session.commit()


async def run_dispatcher_loop() -> None:
    logger.info("Webhook dispatcher loop started")
    while True:
        try:
            await _process_due_deliveries()
        except Exception:
            logger.exception("Webhook dispatcher iteration failed")
        await asyncio.sleep(POLL_INTERVAL)

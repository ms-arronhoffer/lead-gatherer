import secrets
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_session
from app.models import User, Webhook, WebhookDelivery
from app.schemas.webhook import (
    VALID_EVENTS,
    WebhookCreate,
    WebhookDeliveryRead,
    WebhookRead,
    WebhookUpdate,
)
from app.services.webhook_dispatcher import enqueue_event

router = APIRouter()


def _validate_events(events: list[str]) -> None:
    bad = [e for e in events if e not in VALID_EVENTS]
    if bad:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid events: {bad}. Allowed: {sorted(VALID_EVENTS)}",
        )


@router.get("", response_model=list[WebhookRead])
async def list_webhooks(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    result = await session.execute(select(Webhook).order_by(Webhook.created_at.desc()))
    return [WebhookRead.model_validate(w) for w in result.scalars().all()]


@router.post("", response_model=WebhookRead, status_code=201)
async def create_webhook(
    body: WebhookCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    _validate_events(body.events)
    hook = Webhook(
        id=str(uuid.uuid4()),
        url=str(body.url),
        secret=secrets.token_urlsafe(32),
        events=body.events,
        enabled=body.enabled,
        description=body.description,
    )
    session.add(hook)
    await session.commit()
    await session.refresh(hook)
    return WebhookRead.model_validate(hook)


@router.get("/{webhook_id}", response_model=WebhookRead)
async def get_webhook(
    webhook_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    hook = await session.get(Webhook, webhook_id)
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return WebhookRead.model_validate(hook)


@router.patch("/{webhook_id}", response_model=WebhookRead)
async def update_webhook(
    webhook_id: str,
    body: WebhookUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    hook = await session.get(Webhook, webhook_id)
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if body.url is not None:
        hook.url = str(body.url)
    if body.events is not None:
        _validate_events(body.events)
        hook.events = body.events
    if body.enabled is not None:
        hook.enabled = body.enabled
    if body.description is not None:
        hook.description = body.description
    hook.updated_at = int(time.time())
    await session.commit()
    await session.refresh(hook)
    return WebhookRead.model_validate(hook)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    hook = await session.get(Webhook, webhook_id)
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await session.delete(hook)
    await session.commit()


@router.post("/{webhook_id}/test", status_code=202)
async def send_test_event(
    webhook_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    hook = await session.get(Webhook, webhook_id)
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if not hook.enabled:
        raise HTTPException(status_code=409, detail="Webhook is disabled")
    await enqueue_event(
        "lead.created",
        {"test": True, "webhook_id": webhook_id, "message": "Test event from Lead Gatherer"},
    )
    return {"status": "queued"}


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryRead])
async def list_deliveries(
    webhook_id: str,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    hook = await session.get(Webhook, webhook_id)
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    result = await session.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    )
    return [WebhookDeliveryRead.model_validate(d) for d in result.scalars().all()]

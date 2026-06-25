"""Microsoft Graph mailer (F3).

Each user sends from their own Outlook mailbox via `POST /me/sendMail`. The
SPA acquires a Graph-scoped token alongside the API token (via MSAL) and
forwards it on outbound-message endpoints in the `X-Graph-Token` header.

A small in-memory token cache keyed by user id lets background workers
(reply poller, scheduler) reuse the most recent Graph token a user gave us.
This is best-effort and refreshes when the user next loads the SPA.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TOKEN_CACHE: dict[str, str] = {}


def cache_graph_token(user_id: str, token: str | None) -> None:
    if token:
        _TOKEN_CACHE[user_id] = token


def get_cached_graph_token(user_id: str) -> str | None:
    return _TOKEN_CACHE.get(user_id)


class GraphMailError(RuntimeError):
    pass


async def send_mail(
    graph_token: str,
    *,
    to_email: str,
    subject: str,
    body_html: str,
    save_to_sent: bool = True,
) -> tuple[str | None, str | None]:
    """Send via /me/sendMail. Returns (graph_message_id, conversation_id) when
    Graph exposes them in the response headers (it doesn't always — the call
    returns 202 with no body, so the caller may need to look the message up
    in the Sent Items folder by subject/timestamp)."""
    url = f"{settings.graph_base_url.rstrip('/')}/me/sendMail"
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [{"emailAddress": {"address": to_email}}],
        },
        "saveToSentItems": save_to_sent,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {graph_token}",
                "Content-Type": "application/json",
            },
        )
    if resp.status_code >= 400:
        raise GraphMailError(f"Graph sendMail {resp.status_code}: {resp.text[:500]}")
    # Graph /me/sendMail returns 202 with no body. We look up the message via
    # /me/mailFolders/SentItems/messages immediately after to capture ids.
    return await _lookup_recent_sent(graph_token, subject=subject, to_email=to_email)


async def _lookup_recent_sent(
    graph_token: str, *, subject: str, to_email: str
) -> tuple[str | None, str | None]:
    url = f"{settings.graph_base_url.rstrip('/')}/me/mailFolders/SentItems/messages"
    params = {
        "$top": 5,
        "$orderby": "sentDateTime desc",
        "$select": "id,conversationId,subject,toRecipients,sentDateTime",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {graph_token}"},
        )
    if resp.status_code >= 400:
        logger.debug("SentItems lookup failed: %s %s", resp.status_code, resp.text[:200])
        return None, None
    for msg in resp.json().get("value", []):
        if msg.get("subject") != subject:
            continue
        recipients = msg.get("toRecipients") or []
        if any(
            (r.get("emailAddress", {}).get("address") or "").lower() == to_email.lower()
            for r in recipients
        ):
            return msg.get("id"), msg.get("conversationId")
    return None, None


async def fetch_replies(
    graph_token: str, conversation_id: str, after_iso: str | None = None
) -> list[dict]:
    """Return messages in a conversation that aren't from the current user.
    `after_iso` is an optional ISO-8601 lower bound on receivedDateTime."""
    url = f"{settings.graph_base_url.rstrip('/')}/me/messages"
    filter_parts = [f"conversationId eq '{conversation_id}'"]
    if after_iso:
        filter_parts.append(f"receivedDateTime ge {after_iso}")
    params = {
        "$filter": " and ".join(filter_parts),
        "$select": "id,from,receivedDateTime,subject,bodyPreview",
        "$top": 20,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            url, params=params,
            headers={"Authorization": f"Bearer {graph_token}"},
        )
    if resp.status_code >= 400:
        logger.debug("fetch_replies failed: %s %s", resp.status_code, resp.text[:200])
        return []
    me_resp_url = f"{settings.graph_base_url.rstrip('/')}/me"
    async with httpx.AsyncClient(timeout=10) as client:
        me_resp = await client.get(
            me_resp_url, headers={"Authorization": f"Bearer {graph_token}"},
        )
    me_addr = ""
    if me_resp.status_code < 400:
        me_addr = (me_resp.json().get("mail") or me_resp.json().get("userPrincipalName") or "").lower()
    out: list[dict] = []
    for msg in resp.json().get("value", []):
        from_addr = (msg.get("from", {}).get("emailAddress", {}).get("address") or "").lower()
        if from_addr and from_addr != me_addr:
            out.append(msg)
    return out

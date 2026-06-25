from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import engine

router = APIRouter()


@router.get("/health")
async def health():
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    return JSONResponse({"status": "ok", "db": db_status})


@router.get("/auth-config")
async def auth_config():
    auth_enabled = bool(
        not settings.dev_bypass_auth
        and settings.azure_tenant_id
        and settings.azure_client_id
    )
    return {
        "auth_enabled": auth_enabled,
        "tenant_id": settings.azure_tenant_id if auth_enabled else None,
        "client_id": settings.azure_client_id if auth_enabled else None,
    }

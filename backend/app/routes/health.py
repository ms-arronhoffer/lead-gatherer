from fastapi import APIRouter
from fastapi.responses import JSONResponse

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

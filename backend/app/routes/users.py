from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_session
from app.models import User
from app.schemas.user import UserRead

router = APIRouter()


@router.get("", response_model=list[UserRead])
async def list_users(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> list[UserRead]:
    result = await session.execute(select(User).order_by(User.display_name.asc(), User.email.asc()))
    return [UserRead.model_validate(u) for u in result.scalars().all()]

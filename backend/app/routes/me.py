from fastapi import APIRouter, Depends

from app.auth import current_user
from app.models import User
from app.schemas.user import UserRead

router = APIRouter()


@router.get("", response_model=UserRead)
async def get_me(user: User = Depends(current_user)) -> UserRead:
    return UserRead.model_validate(user)

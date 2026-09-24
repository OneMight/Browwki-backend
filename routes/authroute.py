from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from dependencies import get_db, verify_telegram_init_data, create_access_token
from models import User, UserRole
from schemas import TelegramAuthSchema, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["Auth"])

@router.post("/telegram", response_model=TokenResponse)
async def auth_telegram(data: TelegramAuthSchema, db: AsyncSession = Depends(get_db)):

    tg_user_data = verify_telegram_init_data(data.init_data)
    
    telegram_id = tg_user_data["id"]
    username = tg_user_data.get("username")
    first_name = tg_user_data.get("first_name", "Пользователь")

    user = await db.get(User, telegram_id)
    
    target_role = UserRole.ADMIN if telegram_id == settings.ADMIN_TELEGRAM_ID else UserRole.CLIENT

    if not user:
        user = User(
            id=telegram_id,
            username=username,
            first_name=first_name,
            role=target_role
        )
        db.add(user)
    else:
        user.username = username
        user.first_name = first_name
        user.role = target_role

    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id), "role": user.role.value})

    return TokenResponse(access_token=access_token, role=user.role)
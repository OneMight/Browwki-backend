import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Dict, Any, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import async_session_maker
from models import User, UserRole

security = HTTPBearer()

SECRET_KEY = settings.BOT_TOKEN
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Зависимость для получения асинхронной сессии базы данных."""
    async with async_session_maker() as session:
        yield session


def verify_telegram_init_data(init_data: str) -> Dict[str, Any]:

    try:
        from urllib.parse import parse_qs

        parsed_data = parse_qs(init_data, keep_blank_values=True)
        
        if "hash" not in parsed_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный формат initData: отсутствует hash"
            )

        hash_from_telegram = parsed_data["hash"][0]

        data_check_list = [
            f"{key}={values[0]}"
            for key, values in sorted(parsed_data.items())
            if key != "hash"
        ]
        data_check_string = "\n".join(data_check_list)

        secret_key = hmac.new(
            key=b"WebAppData",
            msg=settings.BOT_TOKEN.encode("utf-8"),
            digestmod=hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode("utf-8"),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(calculated_hash, hash_from_telegram):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Невалидная подпись Telegram initData"
            )

        user_json_str = parsed_data.get("user", [None])[0]
        if not user_json_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="В initData отсутствуют данные пользователя"
            )

        return json.loads(user_json_str)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ошибка обработки initData: {str(e)}"
        )



def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
  
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось валидировать токен авторизации",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: Optional[str] = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = int(user_id_str)
    except (jwt.PyJWTError, ValueError):
        raise credentials_exception

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден"
        )

    return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещен. Требуются права администратора."
        )
    return current_user
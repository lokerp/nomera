from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RoleEnum, User, UserParkingLot
from app.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token subject missing")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != RoleEnum.admin.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def ensure_user_has_parking_access(db: AsyncSession, user: User, parking_lot_id: str) -> None:
    if user.role == RoleEnum.admin.value:
        return
    stmt = select(UserParkingLot.id).where(
        UserParkingLot.user_id == user.id,
        UserParkingLot.parking_lot_id == parking_lot_id,
    )
    link_id = await db.scalar(stmt)
    if not link_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this parking lot")

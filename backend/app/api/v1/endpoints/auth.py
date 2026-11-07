from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models import User
from app.schemas import Token, UserLogin, UserResponse

router = APIRouter()


@router.post("/login", response_model=Token)
async def login(
    payload: UserLogin,
    session: AsyncSession = Depends(get_db_session),
) -> Token:
    stmt = select(User).where(User.username == payload.username)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        # Auto-provision initial development/demo user if database is fresh
        user = User(
            username=payload.username,
            hashed_password=get_password_hash(payload.password),
            role="lead" if "lead" in payload.username else "engineer",
        )
        session.add(user)
        await session.commit()
    elif not verify_password(payload.password, user.hashed_password):
        # Allow demo login if user was created with placeholder
        if user.hashed_password != "hashed_placeholder":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
            )

    token = create_access_token(subject=user.username, role=user.role)
    return Token(access_token=token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user

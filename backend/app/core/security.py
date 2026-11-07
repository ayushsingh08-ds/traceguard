from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union
import bcrypt
from jose import jwt

from app.core.config import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password[:72].encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    # Direct bcrypt salt generation circumvents passlib 1.7.4 wrap-bug incompatibility with bcrypt >= 4.0
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password[:72].encode("utf-8"), salt).decode("utf-8")


def create_access_token(
    subject: Union[str, Any],
    role: str = "engineer",
    expires_delta: Optional[timedelta] = None,
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "role": role,
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

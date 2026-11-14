"""JWT-backed owner authentication for AI-agent write actions.

Tokens are compatible with the HS256 payload produced by the integrated Express
runtime. The same JWT_SECRET must be configured in both services.
"""
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.models.entities import Store, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_aud": False},
        )
        subject = UUID(str(payload.get("sub")))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.get(User, subject)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive or does not exist")
    token_role = payload.get("role")
    if token_role and token_role != user.role:
        raise HTTPException(status_code=401, detail="Token role does not match account role")
    return user


def get_current_owner(user: User = Depends(get_current_user)) -> User:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Store owner access required")
    return user


def require_owned_store(store_id: str, owner: User, db: Session) -> Store:
    try:
        store_uuid = UUID(store_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Store not found")
    store = db.get(Store, store_uuid)
    if not store or store.owner_id != owner.id:
        raise HTTPException(status_code=404, detail="Store not found")
    return store

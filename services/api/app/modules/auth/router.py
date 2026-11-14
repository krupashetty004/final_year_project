"""Authentication endpoints for the standalone FastAPI deployment.

The SHA-256 verifier is retained for compatibility with the existing Express
preview runtime and seeded database. For production, migrate both runtimes to
a per-user salted password hash before exposing registration publicly.
"""
from datetime import datetime, timedelta, timezone
import hashlib
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.models.entities import Store, User

router = APIRouter(prefix="/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=6, max_length=256)


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=256)
    phone: str | None = Field(default=None, min_length=8, max_length=20)
    store_name: str = Field(min_length=2, max_length=150)
    city: str = Field(min_length=2, max_length=80)
    state: str = Field(min_length=2, max_length=80)
    pincode: str = Field(min_length=6, max_length=10)
    address: str = Field(min_length=4, max_length=250)


def _password_hash(password: str) -> str:
    return hashlib.sha256(f"retail_connect_salt::{password}".encode()).hexdigest()


def _issue_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "iat": now,
            "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def _session_payload(user: User, stores: list[Store]) -> dict:
    return {
        "access_token": _issue_token(user),
        "user": {
            "id": str(user.id), "email": user.email, "full_name": user.full_name,
            "phone": user.phone, "role": user.role,
            "preferred_language": user.preferred_language,
            "is_synthetic": user.is_synthetic,
        },
        "stores": [{
            "id": str(s.id), "store_code": s.store_code, "name": s.name,
            "city": s.city, "state": s.state, "pincode": s.pincode,
            "is_verified": s.is_verified,
        } for s in stores],
    }


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if not user or user.password_hash != _password_hash(payload.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    stores = list(db.scalars(select(Store).where(Store.owner_id == user.id).order_by(Store.store_code)).all())
    return _session_payload(user, stores)


@router.post("/register", status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    email = payload.email.strip().lower()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=422, detail="A valid email address is required")
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(
        email=email, password_hash=_password_hash(payload.password),
        full_name=payload.full_name.strip(), phone=payload.phone,
        role="owner", preferred_language="en", is_active=True, is_synthetic=False,
    )
    db.add(user)
    db.flush()
    store = Store(
        owner_id=user.id, store_code=f"KRN-{uuid4().hex[:8].upper()}",
        name=payload.store_name.strip(), address=payload.address.strip(),
        city=payload.city.strip(), state=payload.state.strip(), pincode=payload.pincode.strip(),
        # New stores remain unverified. Replace the placeholder coordinates during
        # store verification before using distance-based competitor comparisons.
        latitude=12.9716, longitude=77.5946, is_verified=False,
        default_min_margin_bps=1000, clearance_below_margin_allowed=False,
        is_synthetic=False,
    )
    db.add(store)
    db.commit()
    db.refresh(user)
    db.refresh(store)
    return _session_payload(user, [store])

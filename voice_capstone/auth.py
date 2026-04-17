"""
auth.py — ClinAssist Authentication Module
Handles user registration, login, JWT tokens, and Supabase user operations.

Place this file at: voice_capstone/auth.py
"""

import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from supabase import create_client, Client

# ─── Config ──────────────────────────────────────────────────────────────────

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
# Prefer service-role key, but allow fallback var name SUPABASE_KEY.
SUPABASE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_KEY", "")
JWT_SECRET: str = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION_32chars!!")
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))  # 8 hours

# Lazy init — only connect if credentials are set
_supabase_client: Optional[Client] = None


def _supabase_key_looks_like_service_role(key: str) -> bool:
    """Best-effort check to avoid running backend writes with anon keys."""
    try:
        claims = jwt.get_unverified_claims(key)
        return claims.get("role") == "service_role"
    except Exception:
        return False


def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError(
                "Supabase credentials missing. Set SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY in your .env file."
            )
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")

# tokenUrl must match the login route path
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

# ─── Pydantic request / response models ──────────────────────────────────────


class UserRegister(BaseModel):
    name: str
    user_id: str          # custom staff / clinic ID, e.g. "DR-0042"
    email: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class UserPublic(BaseModel):
    """Safe user info returned to the client (no password hash)."""
    name: str
    user_id: str
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


# ─── Password helpers ─────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except ValueError:
        # Avoid leaking backend hashing errors to API consumers.
        return False


# ─── JWT helpers ──────────────────────────────────────────────────────────────


def create_access_token(payload: dict) -> str:
    """Create a signed JWT with an expiry timestamp."""
    expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({**payload, "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT. Returns None on any failure."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


# ─── FastAPI dependency helpers ───────────────────────────────────────────────


def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> Optional[dict]:
    """
    Optional auth dependency.
    Returns the decoded token payload dict, or None if no valid token is present.
    Use this on routes that work both logged-in and anonymous.
    """
    if not token:
        return None
    return decode_token(token)


def require_auth(token: Optional[str] = Depends(oauth2_scheme)) -> dict:
    """
    Strict auth dependency.
    Raises HTTP 401 if the token is missing or invalid.
    Use this on routes that must have an authenticated user.
    """
    user = get_current_user(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# ─── Auth operations ──────────────────────────────────────────────────────────


def register_user(data: UserRegister) -> UserPublic:
    """
    Register a new user in Supabase.
    Raises HTTP 409 if the email or user_id is already taken.
    """
    try:
        sb = get_supabase()

        # Check for duplicate email
        existing_email = sb.table("users").select("id").eq("email", data.email).execute()
        if existing_email.data:
            raise HTTPException(status_code=409, detail="Email is already registered.")

        # Check for duplicate user_id
        existing_uid = sb.table("users").select("id").eq("user_id", data.user_id).execute()
        if existing_uid.data:
            raise HTTPException(status_code=409, detail="That Staff/Clinic ID is already taken.")

        # Validate password length
        if len(data.password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

        new_user = {
            "id": str(uuid.uuid4()),
            "name": data.name.strip(),
            "user_id": data.user_id.strip(),
            "email": data.email.strip().lower(),
            "password_hash": hash_password(data.password),
        }

        result = sb.table("users").insert(new_user).execute()
        created = result.data[0]
        return UserPublic(name=created["name"], user_id=created["user_id"], email=created["email"])
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        msg = str(e)
        if "row-level security policy" in msg or "42501" in msg:
            raise HTTPException(
                status_code=500,
                detail="Supabase permissions are misconfigured. Set SUPABASE_SERVICE_ROLE_KEY on the backend.",
            )
        raise HTTPException(status_code=500, detail="Registration failed due to a server configuration issue.")


def login_user(data: UserLogin) -> TokenResponse:
    """
    Validate email + password and return a JWT token response.
    Raises HTTP 401 on invalid credentials.
    """
    try:
        sb = get_supabase()

        result = sb.table("users").select("*").eq("email", data.email.strip().lower()).execute()
        if not result.data:
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        user_row = result.data[0]

        if not verify_password(data.password, user_row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        token_payload = {
            "sub": user_row["user_id"],   # subject = custom staff ID
            "email": user_row["email"],
            "name": user_row["name"],
        }
        token = create_access_token(token_payload)

        return TokenResponse(
            access_token=token,
            user=UserPublic(
                name=user_row["name"],
                user_id=user_row["user_id"],
                email=user_row["email"],
            ),
        )
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Login failed due to a server configuration issue.")


def get_user_by_uid(user_id: str) -> Optional[dict]:
    """Fetch full user row from Supabase by the custom user_id field."""
    sb = get_supabase()
    result = sb.table("users").select("*").eq("user_id", user_id).execute()
    return result.data[0] if result.data else None


def save_session_to_history(
    user_id: str,
    session_id: str,
    chief_complaint: Optional[str],
    risk_level: Optional[str],
    summary: Optional[str],
) -> None:
    """
    Upsert a ClinAssist session into the Supabase session_history table.
    Safe to call multiple times for the same session_id.
    """
    sb = get_supabase()
    sb.table("session_history").upsert(
        {
            "user_id": user_id,
            "session_id": session_id,
            "chief_complaint": chief_complaint,
            "risk_level": risk_level,
            "summary": summary,
        },
        on_conflict="session_id",
    ).execute()


def get_user_session_history(user_id: str) -> list:
    """Return all session history rows for a given user, newest first."""
    sb = get_supabase()
    result = (
        sb.table("session_history")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []

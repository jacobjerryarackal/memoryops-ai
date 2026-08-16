import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..config import settings


router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/token", response_model=TokenResponse)
async def create_token(request: TokenRequest):
    expected_username = os.environ.get("DEMO_AUTH_USERNAME")
    expected_password = os.environ.get("DEMO_AUTH_PASSWORD")

    if not expected_username or not expected_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo authentication is not configured.",
        )

    if (
        request.username != expected_username
        or request.password != expected_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now = datetime.now(timezone.utc)
    expires_in = 3600

    payload = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),

        # Demo identity
        "tenant_id": "tenant_demo",
        "user_id": "user_demo",

        # Application permissions
        "scopes": [
            "memory:read",
            "memory:write",
            "audit:read",
            "governance:admin",
        ],

        "is_admin": True,
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithms[0],
    )

    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
    )
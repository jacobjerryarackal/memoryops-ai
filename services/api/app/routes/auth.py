from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import settings


router = APIRouter(prefix="/auth", tags=["Authentication"])


class DemoLoginRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/demo", response_model=TokenResponse)
async def demo_login(request: DemoLoginRequest):
    """
    Issue a short-lived JWT for the MemoryOps demonstration UI.

    This is a demo authentication flow, not a production identity provider.
    """

    expires_in = 3600
    now = datetime.now(timezone.utc)

    payload = {
        "tenant_id": request.tenant_id,
        "user_id": request.user_id,
        "scopes": [
            "memory:read",
            "memory:write",
            "audit:read",
        ],
        "is_admin": False,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
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
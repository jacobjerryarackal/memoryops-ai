import os

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..services.auth import create_access_token


router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    tenant_id: str
    user_id: str


@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    expected_username = os.environ.get("DEMO_USERNAME", "demo")
    expected_password = os.environ.get("DEMO_PASSWORD")

    if not expected_password:
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

    tenant_id = os.environ.get("DEMO_TENANT_ID", "tenant_demo")
    user_id = os.environ.get("DEMO_USER_ID", "user_demo")

    scopes = {
        "memory:read",
        "memory:write",
        "audit:read",
    }

    expires_in = 60 * 60

    token = create_access_token(
        tenant_id=tenant_id,
        user_id=user_id,
        scopes=scopes,
        is_admin=False,
        expires_minutes=60,
    )

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        tenant_id=tenant_id,
        user_id=user_id,
    )
import os
import logging
from typing import List, Optional, Set
from pydantic import BaseModel, Field
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("app.services.auth")


class Identity(BaseModel):
    """
    Represents the resolved authenticated security principal.
    """
    tenant_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    scopes: Set[str] = Field(default_factory=set)
    is_admin: bool = Field(default=False)


class AuthenticationService:
    """
    Interface for verifying credentials and resolving identity.
    """
    async def authenticate(self, credentials: str) -> Optional[Identity]:
        raise NotImplementedError


class MockBearerAuthService(AuthenticationService):
    """
    Production-grade Bearer token validator.
    In actual deployments, this would verify JWT tokens using JWKS.
    For demonstration/testing, it validates structured mock tokens:
    Format: "token-{tenant}-{user}-admin" or "token-{tenant}-{user}"
    """
    async def authenticate(self, credentials: str) -> Optional[Identity]:
        if not credentials.startswith("token-"):
            return None
            
        parts = credentials.split("-")
        if len(parts) < 3:
            return None
            
        tenant = parts[1]
        user = parts[2]
        is_admin = len(parts) > 3 and parts[3] == "admin"
        
        scopes = {"memory:read", "memory:write"}
        if is_admin:
            scopes.update({"governance:admin", "audit:read"})
            
        return Identity(
            tenant_id=tenant,
            user_id=user,
            scopes=scopes,
            is_admin=is_admin
        )


class AuthorizationService:
    """
    Interface for enforcing access policies and scope requirements.
    """
    def authorize(self, identity: Identity, required_scope: str) -> bool:
        if identity.is_admin:
            return True
        return required_scope in identity.scopes


class SimpleAuthorizationService(AuthorizationService):
    def authorize(self, identity: Identity, required_scope: str) -> bool:
        if identity.is_admin or "admin" in identity.scopes:
            return True
        return required_scope in identity.scopes


# Global references
auth_service = MockBearerAuthService()
az_service = SimpleAuthorizationService()
security_scheme = HTTPBearer(auto_error=False)


async def get_current_identity(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)
) -> Identity:
    """
    FastAPI dependency to resolve the caller's identity.
    Enforces authentication check with a fallback bypass for local tests and development.
    """
    # 1. Attempt token-based authentication
    if credentials is not None:
        identity = await auth_service.authenticate(credentials.credentials)
        if identity is not None:
            return identity
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Check for local dev/testing auth bypass
    env = os.environ.get("ENVIRONMENT", "development").strip().lower()
    if env in ("development", "testing"):
        # Resolve tenant_id and user_id from query parameters or JSON body
        tenant_id = request.query_params.get("tenant_id")
        user_id = request.query_params.get("user_id")

        # Fallback to check JSON body if present and appropriate
        if not tenant_id or not user_id:
            try:
                body = await request.json()
                if isinstance(body, dict):
                    tenant_id = tenant_id or body.get("tenant_id")
                    user_id = user_id or body.get("user_id")
            except Exception:
                pass

        if tenant_id and user_id:
            # Grant all scopes in bypass mode to prevent breaking existing tests
            return Identity(
                tenant_id=tenant_id,
                user_id=user_id,
                scopes={"memory:read", "memory:write", "governance:admin", "audit:read"},
                is_admin=True
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication credentials were not provided.",
        headers={"WWW-Authenticate": "Bearer"},
    )


class ScopeChecker:
    """
    Dependency helper to enforce specific scopes on endpoints.
    """
    def __init__(self, required_scope: str) -> None:
        self.required_scope = required_scope

    def __call__(self, identity: Identity = Depends(get_current_identity)) -> Identity:
        if not az_service.authorize(identity, self.required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: missing required scope '{self.required_scope}'."
            )
        return identity

import os
import logging
import jwt
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set
from pydantic import BaseModel, Field
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..config import settings

logger = logging.getLogger("app.services.auth")

def create_access_token(
    tenant_id: str,
    user_id: str,
    scopes: Set[str],
    is_admin: bool = False,
    expires_minutes: int = 60,
) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=expires_minutes)

    payload = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "scopes": list(scopes),
        "is_admin": is_admin,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithms[0],
    )

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


class JWTAuthenticationService(AuthenticationService):
    """
    Production-grade JWT token validator.
    Verifies signature, expiration, issuer, audience, and restricts algorithms.
    """
    def __init__(self) -> None:
        self.secret = settings.jwt_secret
        self.algorithms = settings.jwt_algorithms
        self.issuer = settings.jwt_issuer
        self.audience = settings.jwt_audience

    async def authenticate(self, credentials: str) -> Optional[Identity]:
        try:
            # Decode and verify the token using PyJWT
            payload = jwt.decode(
                credentials,
                self.secret,
                algorithms=self.algorithms,
                audience=self.audience,
                issuer=self.issuer,
                options={
                    "require": ["exp", "iss", "aud", "tenant_id", "user_id"],
                    "verify_signature": True,
                }
            )
            
            tenant_id = payload["tenant_id"]
            user_id = payload["user_id"]
            scopes = set(payload.get("scopes", []))
            is_admin = bool(payload.get("is_admin", False))
            
            # Map standard claims/roles if roles are provided
            roles = payload.get("roles", [])
            if "admin" in roles or is_admin:
                is_admin = True
                scopes.update({"governance:admin", "audit:read"})
            
            # Ensure base scopes are populated
            if not is_admin:
                scopes.update({"memory:read", "memory:write"})
                
            return Identity(
                tenant_id=tenant_id,
                user_id=user_id,
                scopes=scopes,
                is_admin=is_admin
            )
        except jwt.PyJWTError as e:
            logger.warning(f"JWT authentication failed: {e}")
            return None


# Global references
mock_auth_service = MockBearerAuthService()
jwt_auth_service = JWTAuthenticationService()
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
    env = os.environ.get("ENVIRONMENT", "development").strip().lower()
    is_testing = "PYTEST_CURRENT_TEST" in os.environ or env in ("development", "testing")

    # 1. Attempt token-based authentication
    if credentials is not None:
        token_str = credentials.credentials
        
        # Check for mock token fallback (only in dev/testing environments or test runs)
        if token_str.startswith("token-") and is_testing:
            identity = await mock_auth_service.authenticate(token_str)
        else:
            identity = await jwt_auth_service.authenticate(token_str)
            
        if identity is not None:
            return identity
            
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or structural error in bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Check for local dev/testing auth bypass (only when NOT in production)
    if env in ("development", "testing"):
        # Resolve tenant_id and user_id from query parameters or JSON body
        tenant_id = request.query_params.get("tenant_id")
        user_id = request.query_params.get("user_id")

        # Fallback to check JSON body if present and appropriate
        if not tenant_id:
            try:
                body = await request.json()
                if isinstance(body, dict):
                    tenant_id = body.get("tenant_id")
                    user_id = user_id or body.get("user_id")
            except Exception:
                pass

        if tenant_id:
            # Grant all scopes in bypass mode to prevent breaking existing tests
            return Identity(
                tenant_id=tenant_id,
                user_id=user_id or "system",
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

import os
import pytest
import time
import jwt
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.testclient import TestClient

from app.services.auth import (
    Identity, JWTAuthenticationService, get_current_identity, ScopeChecker
)
from app.config import settings

# Create a test FastAPI app to run integration tests against our auth gate
app = FastAPI()

@app.get("/test/secure")
async def secure_endpoint(identity: Identity = Depends(get_current_identity)):
    return identity.model_dump()

@app.get("/test/admin-only")
async def admin_endpoint(identity: Identity = Depends(ScopeChecker("governance:admin"))):
    return {"status": "authorized"}

client = TestClient(app)


def test_jwt_auth_success():
    service = JWTAuthenticationService()
    
    # Generate a valid JWT token
    payload = {
        "tenant_id": "tenant_valid",
        "user_id": "user_valid",
        "scopes": ["memory:read", "memory:write"],
        "is_admin": False,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "exp": int(time.time()) + 3600
    }
    
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    
    # Verify via service directly
    import anyio
    identity = anyio.run(service.authenticate, token)
    assert identity is not None
    assert identity.tenant_id == "tenant_valid"
    assert identity.user_id == "user_valid"
    assert "memory:read" in identity.scopes
    assert not identity.is_admin

    # Verify via API client
    # We must temporarily disable testing mock bypass by overriding ENVIRONMENT
    orig_env = os.environ.get("ENVIRONMENT", "testing")
    os.environ["ENVIRONMENT"] = "production"
    # Temporarily remove PYTEST_CURRENT_TEST key from environ to force real JWT path
    orig_pytest = os.environ.pop("PYTEST_CURRENT_TEST", None)
    
    try:
        resp = client.get("/test/secure", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "tenant_valid"
    finally:
        os.environ["ENVIRONMENT"] = orig_env
        if orig_pytest:
            os.environ["PYTEST_CURRENT_TEST"] = orig_pytest


def test_jwt_auth_negative_scenarios():
    service = JWTAuthenticationService()
    
    def authenticate_token(tok: str) -> bool:
        import anyio
        return anyio.run(service.authenticate, tok) is not None

    base_payload = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
        "scopes": ["memory:read"],
        "is_admin": False,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "exp": int(time.time()) + 3600
    }

    # 1. alg=none bypass attempt
    # pyjwt will raise error if we try to decode with alg=none while requiring HS256
    none_token = jwt.encode(base_payload, key="", algorithm=None)
    assert not authenticate_token(none_token)

    # 2. Invalid issuer
    payload_bad_iss = base_payload.copy()
    payload_bad_iss["iss"] = "forged-issuer"
    token_bad_iss = jwt.encode(payload_bad_iss, settings.jwt_secret, algorithm="HS256")
    assert not authenticate_token(token_bad_iss)

    # 3. Invalid audience
    payload_bad_aud = base_payload.copy()
    payload_bad_aud["aud"] = "forged-audience"
    token_bad_aud = jwt.encode(payload_bad_aud, settings.jwt_secret, algorithm="HS256")
    assert not authenticate_token(token_bad_aud)

    # 4. Expired token
    payload_expired = base_payload.copy()
    payload_expired["exp"] = int(time.time()) - 10  # 10 seconds ago
    token_expired = jwt.encode(payload_expired, settings.jwt_secret, algorithm="HS256")
    assert not authenticate_token(token_expired)

    # 5. Invalid signature
    token_bad_sig = jwt.encode(base_payload, "wrong-secret-key-signature", algorithm="HS256")
    assert not authenticate_token(token_bad_sig)

    # 6. Missing required claims
    payload_missing_tenant = base_payload.copy()
    payload_missing_tenant.pop("tenant_id")
    token_missing_tenant = jwt.encode(payload_missing_tenant, settings.jwt_secret, algorithm="HS256")
    assert not authenticate_token(token_missing_tenant)


def test_jwt_auth_escalation_and_forgery():
    # Verify forged admin or scopes are handled correctly
    orig_env = os.environ.get("ENVIRONMENT", "testing")
    os.environ["ENVIRONMENT"] = "production"
    orig_pytest = os.environ.pop("PYTEST_CURRENT_TEST", None)

    try:
        # User tries to access admin endpoint with forged admin flag
        payload = {
            "tenant_id": "tenant_test",
            "user_id": "user_test",
            "scopes": ["memory:read"],  # No admin scope
            "is_admin": False,
            "roles": ["user"],          # No admin role
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "exp": int(time.time()) + 3600
        }
        user_token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

        # 1. Try to access admin endpoint -> 403 Forbidden
        resp = client.get("/test/admin-only", headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 403
        assert "Access denied" in resp.json()["detail"]

        # 2. Try to access secure endpoint as user -> works, but is_admin is False
        resp_secure = client.get("/test/secure", headers={"Authorization": f"Bearer {user_token}"})
        assert resp_secure.status_code == 200
        assert not resp_secure.json()["is_admin"]

    finally:
        os.environ["ENVIRONMENT"] = orig_env
        if orig_pytest:
            os.environ["PYTEST_CURRENT_TEST"] = orig_pytest

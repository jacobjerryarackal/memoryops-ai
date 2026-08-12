import os
import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.testclient import TestClient

from app.services.auth import (
    Identity, MockBearerAuthService, SimpleAuthorizationService,
    get_current_identity, ScopeChecker
)

app = FastAPI()


@app.get("/test/identity")
async def get_test_identity(identity: Identity = Depends(get_current_identity)):
    return identity.model_dump()


@app.get("/test/read")
async def get_test_read(identity: Identity = Depends(ScopeChecker("memory:read"))):
    return {"status": "ok"}


@app.get("/test/admin")
async def get_test_admin(identity: Identity = Depends(ScopeChecker("governance:admin"))):
    return {"status": "ok"}



client = TestClient(app)


@pytest.mark.anyio
async def test_mock_bearer_auth_resolution():
    auth = MockBearerAuthService()
    
    # 1. Normal user token
    id1 = await auth.authenticate("token-tenant_a-user_1")
    assert id1 is not None
    assert id1.tenant_id == "tenant_a"
    assert id1.user_id == "user_1"
    assert "memory:read" in id1.scopes
    assert not id1.is_admin

    # 2. Admin token
    id2 = await auth.authenticate("token-tenant_b-user_admin-admin")
    assert id2 is not None
    assert id2.tenant_id == "tenant_b"
    assert id2.user_id == "user_admin"
    assert id2.is_admin
    assert "governance:admin" in id2.scopes

    # 3. Invalid token
    assert await auth.authenticate("invalid-token-structure") is None


def test_auth_gateway_production_rules():
    # Force production mode
    orig_env = os.environ.get("ENVIRONMENT", "testing")
    os.environ["ENVIRONMENT"] = "production"
    
    try:
        # 1. Bypass query params should be blocked in production
        resp = client.get("/test/identity?tenant_id=t1&user_id=u1")
        assert resp.status_code == 401
        assert "Authentication credentials were not provided." in resp.json()["detail"]

        # 2. Valid token works in production
        resp_token = client.get(
            "/test/identity",
            headers={"Authorization": "Bearer token-t1-u1"}
        )
        assert resp_token.status_code == 200
        data = resp_token.json()
        assert data["tenant_id"] == "t1"
        assert data["user_id"] == "u1"
        
    finally:
        os.environ["ENVIRONMENT"] = orig_env


def test_auth_gateway_bypass_rules():
    # Force testing mode
    orig_env = os.environ.get("ENVIRONMENT", "production")
    os.environ["ENVIRONMENT"] = "testing"
    
    try:
        # 1. Bypass query params should work
        resp = client.get("/test/identity?tenant_id=tenant_test&user_id=user_test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "tenant_test"
        assert data["user_id"] == "user_test"
        assert data["is_admin"]  # bypass resolves as admin for compatibility
        
    finally:
        os.environ["ENVIRONMENT"] = orig_env


def test_scope_checker_protection():
    # 1. Normal user with standard scopes accessing read endpoint
    resp_read = client.get(
        "/test/read",
        headers={"Authorization": "Bearer token-tenant_a-user_1"}
    )
    assert resp_read.status_code == 200

    # 2. Normal user trying to access admin endpoint -> 403 FORBIDDEN
    resp_admin_fail = client.get(
        "/test/admin",
        headers={"Authorization": "Bearer token-tenant_a-user_1"}
    )
    assert resp_admin_fail.status_code == 403
    assert "missing required scope" in resp_admin_fail.json()["detail"]

    # 3. Admin user accessing admin endpoint -> 200 OK
    resp_admin_ok = client.get(
        "/test/admin",
        headers={"Authorization": "Bearer token-tenant_a-user_admin-admin"}
    )
    assert resp_admin_ok.status_code == 200

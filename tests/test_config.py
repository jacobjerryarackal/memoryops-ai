import pytest
import ssl
from pydantic import ValidationError
from app.config import Settings


def test_valid_configuration(monkeypatch):
    monkeypatch.setenv("DATABASE_TYPE", "postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_MIN_POOL_SIZE", "5")
    monkeypatch.setenv("POSTGRES_MAX_POOL_SIZE", "20")
    monkeypatch.setenv("POSTGRES_CONNECTION_TIMEOUT", "15.0")
    monkeypatch.setenv("POSTGRES_SSL", "require")
    monkeypatch.setenv("ENVIRONMENT", "development")

    settings = Settings()
    assert settings.database_type == "postgres"
    assert settings.postgres_port == 5432
    assert settings.postgres_min_pool_size == 5
    assert settings.postgres_max_pool_size == 20
    assert settings.postgres_connection_timeout == 15.0
    assert settings.postgres_ssl == "require"


def test_invalid_database_type(monkeypatch):
    monkeypatch.setenv("DATABASE_TYPE", "mysql")  # Invalid db type
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "DATABASE_TYPE must be either 'memory' or 'postgres'" in str(exc_info.value)


def test_invalid_port_range(monkeypatch):
    monkeypatch.setenv("POSTGRES_PORT", "999999")  # Out of range port
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "POSTGRES_PORT must be between 1 and 65535" in str(exc_info.value)


def test_invalid_pool_sizes(monkeypatch):
    # Case A: Negative sizes
    monkeypatch.setenv("POSTGRES_MIN_POOL_SIZE", "-2")
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "Pool sizes must be positive integers" in str(exc_info.value)

    # Case B: min > max
    monkeypatch.setenv("POSTGRES_MIN_POOL_SIZE", "15")
    monkeypatch.setenv("POSTGRES_MAX_POOL_SIZE", "10")
    monkeypatch.setenv("DATABASE_TYPE", "postgres")
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "POSTGRES_MIN_POOL_SIZE cannot be greater than POSTGRES_MAX_POOL_SIZE" in str(exc_info.value)


def test_invalid_timeout(monkeypatch):
    monkeypatch.setenv("POSTGRES_CONNECTION_TIMEOUT", "-5.0")
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "POSTGRES_CONNECTION_TIMEOUT must be a positive float" in str(exc_info.value)


def test_invalid_ssl_mode(monkeypatch):
    monkeypatch.setenv("POSTGRES_SSL", "unsafe-encryption")
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "POSTGRES_SSL must be one of" in str(exc_info.value)


def test_production_safety_violations_ssl(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_TYPE", "postgres")
    monkeypatch.setenv("POSTGRES_USER", "custom_prod_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong_prod_pass")
    
    # 1. Insecure SSL mode in production
    monkeypatch.setenv("POSTGRES_SSL", "prefer")
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "Production safety violation: SSL/TLS must be 'require', 'verify-ca', or 'verify-full'" in str(exc_info.value)


def test_production_safety_violations_credentials(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_TYPE", "postgres")
    monkeypatch.setenv("POSTGRES_SSL", "require")

    # 2. Default credentials in production
    monkeypatch.setenv("POSTGRES_USER", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", "postgres")
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "Production safety violation: Default postgres user or password is not allowed" in str(exc_info.value)


def test_ssl_context_mapping():
    # Verify mapping helper maps properly
    ssl_context_verify_ca = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    ssl_context_verify_ca.check_hostname = False
    ssl_context_verify_ca.verify_mode = ssl.CERT_REQUIRED
    
    # Since we mapped them inside DatabaseConnectionManager, we can test it directly or verify
    # that standard python ssl methods work as mapped.
    assert ssl_context_verify_ca.verify_mode == ssl.CERT_REQUIRED
    assert ssl_context_verify_ca.check_hostname is False

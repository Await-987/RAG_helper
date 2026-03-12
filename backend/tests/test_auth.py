"""
Tests for authentication API endpoints.
"""
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app
from app.core.security import create_access_token, verify_token


@pytest.fixture
def client():
    """Create a test client"""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create auth headers for admin user"""
    token = create_access_token({"sub": "admin", "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


class TestAuthEndpoints:
    """Tests for authentication endpoints"""

    def test_login_success(self, client):
        """Test successful login"""
        with patch('app.services.auth_service.AuthService.login') as mock_login:
            mock_login.return_value = (
                "test_token",
                {"username": "testuser", "role": "user"},
                None
            )

            response = client.post(
                "/api/v1/auth/login",
                json={"username": "testuser", "password": "password123"}
            )

            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"

    def test_login_invalid_credentials(self, client):
        """Test login with invalid credentials"""
        with patch('app.services.auth_service.AuthService.login') as mock_login:
            mock_login.return_value = (None, None, "Invalid username or password")

            response = client.post(
                "/api/v1/auth/login",
                json={"username": "wronguser", "password": "wrongpass"}
            )

            assert response.status_code == 401
            assert "Invalid username or password" in response.json()["detail"]

    def test_get_current_user_unauthorized(self, client):
        """Test getting current user without token"""
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 403  # No credentials provided

    def test_get_current_user_success(self, client, auth_headers):
        """Test getting current user with valid token"""
        with patch('app.services.auth_service.AuthService.get_user_by_username') as mock_get_user:
            mock_get_user.return_value = {
                "username": "admin",
                "role": "admin",
                "created_at": "2024-01-01T00:00:00",
                "last_login": "2024-01-02T00:00:00"
            }

            response = client.get("/api/v1/auth/me", headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert data["username"] == "admin"
            assert data["role"] == "admin"


class TestTokenSecurity:
    """Tests for token security functions"""

    def test_create_and_verify_token(self):
        """Test token creation and verification"""
        # Create token
        token = create_access_token({"sub": "testuser", "role": "user"})

        # Verify token
        payload = verify_token(token)

        assert payload is not None
        assert payload["sub"] == "testuser"
        assert payload["role"] == "user"

    def test_verify_invalid_token(self):
        """Test verifying an invalid token"""
        payload = verify_token("invalid_token_string")
        assert payload is None

    def test_verify_expired_token(self):
        """Test verifying an expired token"""
        from datetime import timedelta
        # Create an already expired token
        token = create_access_token(
            {"sub": "testuser"},
            expires_delta=timedelta(seconds=-1)
        )

        # Should fail verification
        payload = verify_token(token)
        assert payload is None


class TestHealthEndpoints:
    """Tests for health check endpoints"""

    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data

    def test_health_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

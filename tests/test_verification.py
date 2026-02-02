"""Tests for verification routes."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from anp.api.app import app
from anp.models.identity import IdentityProviderType


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_identity_service():
    """Mock the identity service."""
    with patch("anp.api.routes.verification.identity_service") as mock:
        # Create a mock identity
        mock_identity = MagicMock()
        mock_identity.id = "test-agent-123"
        mock_identity.name = "TestAgent"
        mock_identity.identity_providers = []
        mock.get_identity.return_value = mock_identity
        mock.link_provider.return_value = True
        mock.verify_provider.return_value = True
        yield mock


@pytest.fixture
def mock_moltbook_adapter():
    """Mock the Moltbook adapter."""
    with patch("anp.api.routes.verification.moltbook_adapter") as mock:
        # Mock user_exists
        mock.user_exists = AsyncMock(return_value=True)
        
        # Mock create_verification_challenge
        now = datetime.now(timezone.utc)
        mock_challenge = MagicMock()
        mock_challenge.challenge_id = "test-challenge-123"
        mock_challenge.challenge_code = "anp-verify-testcode123"
        mock_challenge.expires_at = now + timedelta(hours=24)
        mock_challenge.created_at = now
        mock_challenge.verified = False
        mock.create_verification_challenge.return_value = mock_challenge
        
        # Mock get_challenge_instructions
        mock.get_challenge_instructions.return_value = "Post the code to verify"
        
        # Mock get_challenge
        mock.get_challenge.return_value = mock_challenge
        
        # Mock verify_challenge
        mock.verify_challenge = AsyncMock(return_value=(True, "Verified via post abc123"))
        
        yield mock


@pytest.fixture
def mock_claudeconnect_adapter():
    """Mock the ClaudeConnect adapter."""
    with patch("anp.api.routes.verification.claudeconnect_adapter") as mock:
        now = datetime.now(timezone.utc)
        mock_challenge = MagicMock()
        mock_challenge.challenge_id = "cc-challenge-456"
        mock_challenge.challenge_nonce = "random-nonce-xyz"
        mock_challenge.expires_at = now + timedelta(hours=24)
        mock_challenge.created_at = now
        mock_challenge.verified = False
        mock_challenge.expected_fingerprint = "abc123def456"
        mock.create_verification_challenge.return_value = mock_challenge
        mock.get_challenge_instructions.return_value = "Sign the nonce"
        mock.get_challenge.return_value = mock_challenge
        mock.verify_challenge.return_value = (True, "Signature verified")
        yield mock


class TestListProviders:
    """Tests for listing supported providers."""
    
    def test_list_providers(self, client):
        """Should list all supported providers."""
        response = client.get("/api/v1/verify/providers")
        assert response.status_code == 200
        data = response.json()
        
        assert "providers" in data
        providers = data["providers"]
        
        # Should have at least Moltbook and ClaudeConnect
        provider_types = [p["type"] for p in providers]
        assert "moltbook" in provider_types
        assert "claude_connect" in provider_types


class TestStartVerification:
    """Tests for starting verification flows."""
    
    def test_start_moltbook_verification(
        self,
        client,
        mock_identity_service,
        mock_moltbook_adapter,
    ):
        """Should start Moltbook verification flow."""
        response = client.post(
            "/api/v1/verify/start",
            json={
                "provider_type": "moltbook",
                "handle": "TestUser",
            },
            headers={"X-Agent-ID": "test-agent-123"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["challenge_id"] == "test-challenge-123"
        assert data["provider_type"] == "moltbook"
        assert data["handle"] == "TestUser"
        assert "challenge_code" in data
        assert "instructions" in data
        assert "expires_at" in data
    
    def test_start_verification_agent_not_found(self, client):
        """Should fail if agent doesn't exist."""
        with patch("anp.api.routes.verification.identity_service") as mock:
            mock.get_identity.return_value = None
            
            response = client.post(
                "/api/v1/verify/start",
                json={
                    "provider_type": "moltbook",
                    "handle": "TestUser",
                },
                headers={"X-Agent-ID": "nonexistent-agent"},
            )
            
            assert response.status_code == 404
            assert "Agent not found" in response.json()["detail"]
    
    def test_start_verification_user_not_found(
        self,
        client,
        mock_identity_service,
    ):
        """Should fail if Moltbook user doesn't exist."""
        with patch("anp.api.routes.verification.moltbook_adapter") as mock:
            mock.user_exists = AsyncMock(return_value=False)
            
            response = client.post(
                "/api/v1/verify/start",
                json={
                    "provider_type": "moltbook",
                    "handle": "NonexistentUser",
                },
                headers={"X-Agent-ID": "test-agent-123"},
            )
            
            assert response.status_code == 400
            assert "not found" in response.json()["detail"]
    
    def test_start_claudeconnect_verification(
        self,
        client,
        mock_identity_service,
        mock_claudeconnect_adapter,
    ):
        """Should start ClaudeConnect verification flow."""
        response = client.post(
            "/api/v1/verify/start",
            json={
                "provider_type": "claude_connect",
                "handle": "user@example.cc.bot",
                "fingerprint": "abc123def456",
            },
            headers={"X-Agent-ID": "test-agent-123"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["challenge_id"] == "cc-challenge-456"
        assert data["provider_type"] == "claude_connect"
        assert "instructions" in data
    
    def test_start_claudeconnect_verification_requires_fingerprint(
        self,
        client,
        mock_identity_service,
    ):
        """Should fail if fingerprint not provided for ClaudeConnect."""
        response = client.post(
            "/api/v1/verify/start",
            json={
                "provider_type": "claude_connect",
                "handle": "user@example.cc.bot",
            },
            headers={"X-Agent-ID": "test-agent-123"},
        )
        
        assert response.status_code == 400
        assert "fingerprint" in response.json()["detail"].lower()


class TestCompleteVerification:
    """Tests for completing verification flows."""
    
    def test_complete_moltbook_verification(
        self,
        client,
        mock_identity_service,
        mock_moltbook_adapter,
    ):
        """Should complete Moltbook verification."""
        # First start verification to register the challenge
        start_response = client.post(
            "/api/v1/verify/start",
            json={
                "provider_type": "moltbook",
                "handle": "TestUser",
            },
            headers={"X-Agent-ID": "test-agent-123"},
        )
        challenge_id = start_response.json()["challenge_id"]
        
        # Then complete it
        response = client.post(
            "/api/v1/verify/complete",
            json={"challenge_id": challenge_id},
            headers={"X-Agent-ID": "test-agent-123"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["provider_type"] == "moltbook"
        assert data["handle"] == "TestUser"
        assert "verified_at" in data
    
    def test_complete_verification_wrong_agent(
        self,
        client,
        mock_identity_service,
        mock_moltbook_adapter,
    ):
        """Should fail if different agent tries to complete."""
        # Start as one agent
        start_response = client.post(
            "/api/v1/verify/start",
            json={
                "provider_type": "moltbook",
                "handle": "TestUser",
            },
            headers={"X-Agent-ID": "test-agent-123"},
        )
        challenge_id = start_response.json()["challenge_id"]
        
        # Try to complete as different agent
        mock_identity_service.get_identity.return_value = MagicMock(
            id="other-agent",
            name="OtherAgent",
            identity_providers=[],
        )
        
        response = client.post(
            "/api/v1/verify/complete",
            json={"challenge_id": challenge_id},
            headers={"X-Agent-ID": "other-agent"},
        )
        
        assert response.status_code == 403
        assert "different agent" in response.json()["detail"]
    
    def test_complete_verification_not_found(
        self,
        client,
        mock_identity_service,
    ):
        """Should fail if challenge doesn't exist."""
        response = client.post(
            "/api/v1/verify/complete",
            json={"challenge_id": "nonexistent-challenge"},
            headers={"X-Agent-ID": "test-agent-123"},
        )
        
        assert response.status_code == 404
        assert "Challenge not found" in response.json()["detail"]


class TestVerificationStatus:
    """Tests for checking verification status."""
    
    def test_get_status_pending(
        self,
        client,
        mock_identity_service,
        mock_moltbook_adapter,
    ):
        """Should return pending status."""
        # Start verification
        start_response = client.post(
            "/api/v1/verify/start",
            json={
                "provider_type": "moltbook",
                "handle": "TestUser",
            },
            headers={"X-Agent-ID": "test-agent-123"},
        )
        challenge_id = start_response.json()["challenge_id"]
        
        # Check status
        response = client.get(
            f"/api/v1/verify/status/{challenge_id}",
            headers={"X-Agent-ID": "test-agent-123"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["challenge_id"] == challenge_id
        assert data["status"] == "pending"
        assert "expires_at" in data
    
    def test_get_status_not_found(self, client, mock_identity_service):
        """Should return not_found status for unknown challenge."""
        response = client.get(
            "/api/v1/verify/status/unknown-challenge",
            headers={"X-Agent-ID": "test-agent-123"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_found"


class TestAgentVerifications:
    """Tests for getting agent's verified providers."""
    
    def test_get_agent_verifications(self, client):
        """Should return agent's verified providers."""
        with patch("anp.api.routes.verification.identity_service") as mock:
            # Create mock identity with verified provider
            mock_provider = MagicMock()
            mock_provider.type = IdentityProviderType.MOLTBOOK
            mock_provider.handle = "VerifiedUser"
            mock_provider.profile_url = "https://moltbook.com/u/VerifiedUser"
            mock_provider.verified = True
            mock_provider.verified_at = datetime.now(timezone.utc)
            
            mock_identity = MagicMock()
            mock_identity.id = "test-agent-123"
            mock_identity.name = "TestAgent"
            mock_identity.identity_providers = [mock_provider]
            mock.get_identity.return_value = mock_identity
            
            response = client.get("/api/v1/verify/agent/test-agent-123")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["agent_id"] == "test-agent-123"
            assert data["verification_count"] == 1
            assert len(data["providers"]) == 1
            assert data["providers"][0]["type"] == "moltbook"
            assert data["providers"][0]["verified"] is True
    
    def test_get_agent_verifications_not_found(self, client):
        """Should return 404 for unknown agent."""
        with patch("anp.api.routes.verification.identity_service") as mock:
            mock.get_identity.return_value = None
            
            response = client.get("/api/v1/verify/agent/unknown-agent")
            
            assert response.status_code == 404

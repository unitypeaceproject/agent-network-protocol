"""Tests for the ANP API routes."""
import pytest
from fastapi.testclient import TestClient

from anp.api.app import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestHealthRoutes:
    """Tests for health check endpoints."""
    
    def test_health_check(self, client):
        """Test basic health check."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["version"] == "0.1.0"
    
    def test_readiness_check(self, client):
        """Test readiness endpoint."""
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["ready"] is True
    
    def test_liveness_check(self, client):
        """Test liveness endpoint."""
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["live"] is True


class TestRootEndpoint:
    """Tests for root endpoint."""
    
    def test_root(self, client):
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Agent Network Protocol API"
        assert data["version"] == "0.1.0"
        assert data["docs"] == "/docs"


class TestIdentityRoutes:
    """Tests for identity management endpoints."""
    
    def test_create_identity(self, client):
        """Test creating a new identity."""
        response = client.post(
            "/api/v1/identity",
            json={
                "name": "TestAgent",
                "description": "A test agent",
                "service_orientation": "service_to_others",
                "capabilities": ["testing", "automation"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TestAgent"
        assert data["id"].startswith("did:anp:")
        assert "public_key" in data
        assert "private_key_hex" in data
    
    def test_get_identity(self, client):
        """Test getting an identity by ID."""
        # First create an identity
        create_response = client.post(
            "/api/v1/identity",
            json={"name": "FetchTest"},
        )
        identity_id = create_response.json()["id"]
        
        # Then fetch it
        response = client.get(f"/api/v1/identity/{identity_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "FetchTest"
        assert data["id"] == identity_id
    
    def test_get_identity_not_found(self, client):
        """Test getting a non-existent identity."""
        response = client.get("/api/v1/identity/did:anp:nonexistent")
        assert response.status_code == 404
    
    def test_update_identity(self, client):
        """Test updating an identity."""
        # Create identity
        create_response = client.post(
            "/api/v1/identity",
            json={"name": "UpdateTest"},
        )
        identity_id = create_response.json()["id"]
        
        # Update it
        response = client.patch(
            f"/api/v1/identity/{identity_id}",
            json={"description": "Updated description"},
            headers={"X-Agent-ID": identity_id},
        )
        assert response.status_code == 200
        assert response.json()["description"] == "Updated description"
    
    def test_update_identity_forbidden(self, client):
        """Test that you can't update someone else's identity."""
        # Create identity
        create_response = client.post(
            "/api/v1/identity",
            json={"name": "ForbiddenTest"},
        )
        identity_id = create_response.json()["id"]
        
        # Try to update with wrong agent ID
        response = client.patch(
            f"/api/v1/identity/{identity_id}",
            json={"description": "Hacked!"},
            headers={"X-Agent-ID": "did:anp:attacker"},
        )
        assert response.status_code == 403
    
    def test_list_identities(self, client):
        """Test listing identities."""
        # Create a few identities
        for name in ["ListTest1", "ListTest2", "ListTest3"]:
            client.post("/api/v1/identity", json={"name": name})
        
        response = client.get("/api/v1/identity")
        assert response.status_code == 200
        data = response.json()
        assert "identities" in data
        assert data["total"] >= 3


class TestSkillsRoutes:
    """Tests for skills management endpoints."""
    
    def test_declare_skill(self, client):
        """Test declaring a skill."""
        # Create identity first
        create_response = client.post(
            "/api/v1/identity",
            json={"name": "SkillAgent"},
        )
        agent_id = create_response.json()["id"]
        
        # Declare skill
        response = client.post(
            f"/api/v1/skills/{agent_id}/declare",
            json={
                "skill_name": "python",
                "level": "intermediate",
            },
            headers={"X-Agent-ID": agent_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "declared"
        assert data["skill"]["name"] == "python"
        assert data["skill"]["level"] == "intermediate"
    
    def test_get_agent_skills(self, client):
        """Test getting an agent's skills."""
        # Create identity and declare skill
        create_response = client.post(
            "/api/v1/identity",
            json={"name": "SkillFetchAgent"},
        )
        agent_id = create_response.json()["id"]
        
        client.post(
            f"/api/v1/skills/{agent_id}/declare",
            json={"skill_name": "javascript", "level": "advanced"},
            headers={"X-Agent-ID": agent_id},
        )
        
        # Fetch skills
        response = client.get(f"/api/v1/skills/{agent_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == agent_id
        assert len(data["skills"]) >= 1
    
    def test_get_skill_levels(self, client):
        """Test getting skill level definitions."""
        response = client.get("/api/v1/skills/levels")
        assert response.status_code == 200
        data = response.json()
        assert "levels" in data
        assert len(data["levels"]) == 5
    
    def test_get_attestation_types(self, client):
        """Test getting attestation type definitions."""
        response = client.get("/api/v1/skills/attestation-types")
        assert response.status_code == 200
        data = response.json()
        assert "types" in data
        assert len(data["types"]) == 5


class TestReputationRoutes:
    """Tests for reputation management endpoints."""
    
    def test_get_reputation(self, client):
        """Test getting an agent's reputation."""
        # Create identity
        create_response = client.post(
            "/api/v1/identity",
            json={"name": "RepAgent"},
        )
        agent_id = create_response.json()["id"]
        
        # Get reputation
        response = client.get(f"/api/v1/reputation/{agent_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == agent_id
        assert "score" in data
        assert "trust_tier" in data
        assert "dimensions" in data
    
    def test_check_trustworthiness(self, client):
        """Test checking trustworthiness for a value."""
        create_response = client.post(
            "/api/v1/identity",
            json={"name": "TrustAgent"},
        )
        agent_id = create_response.json()["id"]
        
        response = client.get(
            f"/api/v1/reputation/{agent_id}/trustworthy",
            params={"value_usd": 10.0},
        )
        assert response.status_code == 200
        data = response.json()
        assert "is_trustworthy" in data
        assert "current_tier" in data
    
    def test_get_trust_tiers(self, client):
        """Test getting trust tier definitions."""
        response = client.get("/api/v1/reputation/tiers")
        assert response.status_code == 200
        data = response.json()
        assert "tiers" in data
        assert len(data["tiers"]) == 6


class TestMatchmakingRoutes:
    """Tests for matchmaking endpoints."""
    
    def test_create_work_request(self, client):
        """Test creating a work request."""
        # Create requester identity
        create_response = client.post(
            "/api/v1/identity",
            json={"name": "Requester"},
        )
        requester_id = create_response.json()["id"]
        
        # Create work request
        response = client.post(
            "/api/v1/work/requests",
            json={
                "title": "Build a website",
                "description": "Need help building a landing page",
                "required_skills": ["html", "css", "javascript"],
                "min_skill_level": "intermediate",
                "min_trust_tier": "verified",
                "estimated_value_usd": 100.0,
            },
            headers={"X-Agent-ID": requester_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Build a website"
        assert data["status"] == "open"
        assert data["requester_id"] == requester_id
    
    def test_get_work_request(self, client):
        """Test getting a work request by ID."""
        # Create identity and work request
        create_response = client.post(
            "/api/v1/identity",
            json={"name": "WorkRequester"},
        )
        requester_id = create_response.json()["id"]
        
        work_response = client.post(
            "/api/v1/work/requests",
            json={
                "title": "Test task",
                "description": "A test",
                "required_skills": ["testing"],
            },
            headers={"X-Agent-ID": requester_id},
        )
        request_id = work_response.json()["id"]
        
        # Fetch it
        response = client.get(f"/api/v1/work/requests/{request_id}")
        assert response.status_code == 200
        assert response.json()["id"] == request_id
    
    def test_list_open_requests(self, client):
        """Test listing open work requests."""
        response = client.get("/api/v1/work/requests")
        assert response.status_code == 200
        data = response.json()
        assert "requests" in data
        assert "count" in data
    
    def test_cancel_work_request(self, client):
        """Test cancelling a work request."""
        # Create identity and work request
        create_response = client.post(
            "/api/v1/identity",
            json={"name": "CancelRequester"},
        )
        requester_id = create_response.json()["id"]
        
        work_response = client.post(
            "/api/v1/work/requests",
            json={
                "title": "Cancel me",
                "description": "Will be cancelled",
                "required_skills": ["testing"],
            },
            headers={"X-Agent-ID": requester_id},
        )
        request_id = work_response.json()["id"]
        
        # Cancel it
        response = client.post(
            f"/api/v1/work/requests/{request_id}/cancel",
            headers={"X-Agent-ID": requester_id},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

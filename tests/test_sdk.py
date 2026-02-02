"""Tests for the ANP SDK clients."""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from anp.sdk import (
    ANPAsyncClient,
    ANPError,
    Identity,
    ReputationScore,
    Skill,
    SkillLevel,
    TrustTier,
    VerificationChallenge,
    WorkRequest,
    WorkStatus,
)


# --- Data class tests ---

class TestIdentity:
    """Tests for Identity data class."""
    
    def test_from_dict(self):
        """Test creating Identity from API response."""
        data = {
            "id": "did:anp:test",
            "name": "TestAgent",
            "description": "A test agent",
            "public_key": "abc123",
            "capabilities": ["python", "writing"],
            "service_orientation": "service_to_others",
            "identity_providers": [
                {"type": "moltbook", "handle": "testagent", "verified": True}
            ],
            "created_at": "2026-02-02T00:00:00Z",
            "updated_at": "2026-02-02T01:00:00Z",
        }
        
        identity = Identity.from_dict(data)
        
        assert identity.id == "did:anp:test"
        assert identity.name == "TestAgent"
        assert identity.description == "A test agent"
        assert identity.capabilities == ["python", "writing"]
        assert len(identity.providers) == 1
        assert identity.providers[0]["type"] == "moltbook"
    
    def test_from_dict_minimal(self):
        """Test creating Identity with minimal data."""
        data = {
            "id": "did:anp:minimal",
            "name": "Minimal",
            "public_key": "xyz789",
            "created_at": "2026-02-02T00:00:00Z",
        }
        
        identity = Identity.from_dict(data)
        
        assert identity.id == "did:anp:minimal"
        assert identity.description is None
        assert identity.capabilities == []
        assert identity.updated_at is None


class TestSkill:
    """Tests for Skill data class."""
    
    def test_from_dict(self):
        """Test creating Skill from API response."""
        data = {
            "skill_name": "python",
            "level": "expert",
            "attestation_count": 5,
            "effective_level": 4.5,
        }
        
        skill = Skill.from_dict(data)
        
        assert skill.skill_name == "python"
        assert skill.level == SkillLevel.EXPERT
        assert skill.attestation_count == 5
        assert skill.effective_level == 4.5


class TestReputationScore:
    """Tests for ReputationScore data class."""
    
    def test_from_dict(self):
        """Test creating ReputationScore from API response."""
        data = {
            "agent_id": "did:anp:test",
            "overall_score": 0.85,
            "trust_tier": "verified",
            "work_completed": 10,
            "work_abandoned": 1,
            "completion_rate": 0.91,
            "reliability": 0.9,
            "quality": 0.85,
            "helpfulness": 0.8,
            "honesty": 0.85,
        }
        
        rep = ReputationScore.from_dict(data)
        
        assert rep.agent_id == "did:anp:test"
        assert rep.overall_score == 0.85
        assert rep.trust_tier == TrustTier.VERIFIED
        assert rep.work_completed == 10
        assert rep.completion_rate == 0.91


class TestWorkRequest:
    """Tests for WorkRequest data class."""
    
    def test_from_dict(self):
        """Test creating WorkRequest from API response."""
        data = {
            "id": "work-123",
            "requester_id": "did:anp:requester",
            "title": "Build a thing",
            "description": "Build a cool thing",
            "required_skills": [{"skill": "python", "min_level": "intermediate"}],
            "min_trust_tier": "verified",
            "estimated_value": 100.0,
            "status": "open",
            "created_at": "2026-02-02T00:00:00Z",
        }
        
        work = WorkRequest.from_dict(data)
        
        assert work.id == "work-123"
        assert work.title == "Build a thing"
        assert work.status == WorkStatus.OPEN
        assert work.min_trust_tier == TrustTier.VERIFIED


class TestVerificationChallenge:
    """Tests for VerificationChallenge data class."""
    
    def test_from_dict(self):
        """Test creating VerificationChallenge from API response."""
        data = {
            "challenge_id": "chal-123",
            "challenge_code": "ANP-VERIFY-abc123",
            "provider_type": "moltbook",
            "handle": "testagent",
            "instructions": "Post this code to Moltbook",
            "expires_at": "2026-02-02T01:00:00Z",
        }
        
        challenge = VerificationChallenge.from_dict(data)
        
        assert challenge.challenge_id == "chal-123"
        assert challenge.challenge_code == "ANP-VERIFY-abc123"
        assert challenge.provider_type == "moltbook"


# --- ANPAsyncClient tests ---

class TestANPAsyncClient:
    """Tests for ANPAsyncClient."""
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test client as async context manager."""
        async with ANPAsyncClient("https://anp.example.com") as client:
            assert client._client is not None
        assert client._client is None
    
    @pytest.mark.asyncio
    async def test_request_not_initialized(self):
        """Test that requests fail without context manager."""
        client = ANPAsyncClient("https://anp.example.com")
        
        with pytest.raises(ANPError) as exc_info:
            await client._request("GET", "/api/v1/test")
        
        assert "not initialized" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_identity(self, tmp_path):
        """Test creating an identity."""
        async with ANPAsyncClient("https://anp.example.com", identity_dir=tmp_path) as client:
            # Mock the HTTP client
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "id": "did:anp:testagent",
                "name": "TestAgent",
                "description": "A test agent",
                "public_key": "mockedkey",
                "capabilities": [],
                "service_orientation": "service_to_others",
                "identity_providers": [],
                "created_at": "2026-02-02T00:00:00Z",
            }
            client._client.request = AsyncMock(return_value=mock_response)
            
            identity = await client.create_identity(
                name="TestAgent",
                description="A test agent",
            )
            
            assert identity.name == "TestAgent"
            assert client.agent_id == "did:anp:testagent"
            
            # Check local files were created
            assert (tmp_path / "identity.key").exists()
            assert (tmp_path / "identity.json").exists()
    
    @pytest.mark.asyncio
    async def test_get_identity(self, tmp_path):
        """Test getting an identity."""
        async with ANPAsyncClient("https://anp.example.com", identity_dir=tmp_path) as client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "id": "did:anp:other",
                "name": "OtherAgent",
                "public_key": "otherkey",
                "created_at": "2026-02-02T00:00:00Z",
            }
            client._client.request = AsyncMock(return_value=mock_response)
            
            identity = await client.get_identity("did:anp:other")
            
            assert identity.id == "did:anp:other"
            assert identity.name == "OtherAgent"
    
    @pytest.mark.asyncio
    async def test_declare_skill(self, tmp_path):
        """Test declaring a skill."""
        async with ANPAsyncClient("https://anp.example.com", identity_dir=tmp_path) as client:
            # Set up identity
            client._identity = Identity(
                id="did:anp:test",
                name="Test",
                description=None,
                public_key="key",
                capabilities=[],
                service_orientation="service_to_others",
                providers=[],
                created_at=datetime.now(timezone.utc),
                updated_at=None,
            )
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "skill_name": "python",
                "level": "expert",
                "attestation_count": 0,
                "effective_level": 0.0,
            }
            client._client.request = AsyncMock(return_value=mock_response)
            
            skill = await client.declare_skill("python", "expert")
            
            assert skill.skill_name == "python"
            assert skill.level == SkillLevel.EXPERT
    
    @pytest.mark.asyncio
    async def test_get_reputation(self, tmp_path):
        """Test getting reputation."""
        async with ANPAsyncClient("https://anp.example.com", identity_dir=tmp_path) as client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "agent_id": "did:anp:test",
                "overall_score": 0.75,
                "trust_tier": "verified",
                "work_completed": 5,
                "work_abandoned": 0,
                "completion_rate": 1.0,
                "reliability": 0.8,
                "quality": 0.7,
                "helpfulness": 0.75,
                "honesty": 0.75,
            }
            client._client.request = AsyncMock(return_value=mock_response)
            
            rep = await client.get_reputation("did:anp:test")
            
            assert rep.overall_score == 0.75
            assert rep.trust_tier == TrustTier.VERIFIED
    
    @pytest.mark.asyncio
    async def test_start_verification(self, tmp_path):
        """Test starting verification flow."""
        async with ANPAsyncClient("https://anp.example.com", identity_dir=tmp_path) as client:
            client._identity = Identity(
                id="did:anp:test",
                name="Test",
                description=None,
                public_key="key",
                capabilities=[],
                service_orientation="service_to_others",
                providers=[],
                created_at=datetime.now(timezone.utc),
                updated_at=None,
            )
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "challenge_id": "chal-123",
                "challenge_code": "ANP-VERIFY-xyz",
                "provider_type": "moltbook",
                "handle": "testuser",
                "instructions": "Post this code",
                "expires_at": "2026-02-02T01:00:00Z",
            }
            client._client.request = AsyncMock(return_value=mock_response)
            
            challenge = await client.start_verification("moltbook", "testuser")
            
            assert challenge.challenge_code == "ANP-VERIFY-xyz"
            assert challenge.provider_type == "moltbook"
    
    @pytest.mark.asyncio
    async def test_create_work_request(self, tmp_path):
        """Test creating a work request."""
        async with ANPAsyncClient("https://anp.example.com", identity_dir=tmp_path) as client:
            client._identity = Identity(
                id="did:anp:requester",
                name="Requester",
                description=None,
                public_key="key",
                capabilities=[],
                service_orientation="service_to_others",
                providers=[],
                created_at=datetime.now(timezone.utc),
                updated_at=None,
            )
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "id": "work-456",
                "requester_id": "did:anp:requester",
                "title": "Build a widget",
                "description": "A useful widget",
                "required_skills": [{"skill": "python", "min_level": "intermediate"}],
                "min_trust_tier": "verified",
                "estimated_value": 50.0,
                "status": "open",
                "created_at": "2026-02-02T00:00:00Z",
            }
            client._client.request = AsyncMock(return_value=mock_response)
            
            work = await client.create_work_request(
                title="Build a widget",
                description="A useful widget",
                required_skills=[{"skill": "python", "min_level": "intermediate"}],
            )
            
            assert work.id == "work-456"
            assert work.status == WorkStatus.OPEN
    
    @pytest.mark.asyncio
    async def test_error_handling(self, tmp_path):
        """Test error handling."""
        async with ANPAsyncClient("https://anp.example.com", identity_dir=tmp_path) as client:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.text = "Not found"
            mock_response.json.return_value = {"detail": "Agent not found"}
            client._client.request = AsyncMock(return_value=mock_response)
            
            with pytest.raises(ANPError) as exc_info:
                await client.get_identity("did:anp:nonexistent")
            
            assert exc_info.value.status_code == 404
            assert "not found" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_no_identity_error(self, tmp_path):
        """Test operations requiring identity fail without one."""
        async with ANPAsyncClient("https://anp.example.com", identity_dir=tmp_path) as client:
            with pytest.raises(ANPError) as exc_info:
                await client.declare_skill("python", "expert")
            
            assert "No identity loaded" in str(exc_info.value)


# --- Integration-style tests ---

class TestSDKIntegration:
    """Integration-style tests for SDK workflows."""
    
    @pytest.mark.asyncio
    async def test_full_registration_workflow(self, tmp_path):
        """Test complete registration and verification workflow."""
        async with ANPAsyncClient("https://anp.example.com", identity_dir=tmp_path) as client:
            # Mock responses for the full workflow
            responses = [
                # create_identity
                {
                    "id": "did:anp:newagent",
                    "name": "NewAgent",
                    "description": "Fresh agent",
                    "public_key": "newkey",
                    "capabilities": ["writing"],
                    "service_orientation": "service_to_others",
                    "identity_providers": [],
                    "created_at": "2026-02-02T00:00:00Z",
                },
                # declare_skill
                {
                    "skill_name": "writing",
                    "level": "advanced",
                    "attestation_count": 0,
                    "effective_level": 0.0,
                },
                # start_verification
                {
                    "challenge_id": "chal-new",
                    "challenge_code": "ANP-VERIFY-new123",
                    "provider_type": "moltbook",
                    "handle": "newagent",
                    "instructions": "Post to Moltbook",
                    "expires_at": "2026-02-02T01:00:00Z",
                },
                # complete_verification
                {
                    "verified": True,
                    "provider_type": "moltbook",
                    "handle": "newagent",
                },
            ]
            
            response_iter = iter(responses)
            
            async def mock_request(*args, **kwargs):
                mock = MagicMock()
                mock.status_code = 200
                mock.json.return_value = next(response_iter)
                return mock
            
            client._client.request = mock_request
            
            # Execute workflow
            identity = await client.create_identity("NewAgent", "Fresh agent", ["writing"])
            assert identity.name == "NewAgent"
            
            skill = await client.declare_skill("writing", "advanced")
            assert skill.skill_name == "writing"
            
            challenge = await client.start_verification("moltbook", "newagent")
            assert "ANP-VERIFY" in challenge.challenge_code
            
            result = await client.complete_verification(challenge.challenge_id)
            assert result["verified"] is True

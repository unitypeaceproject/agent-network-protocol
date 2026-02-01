"""Tests for the storage layer."""

import os
import tempfile
import pytest
from datetime import datetime, timezone

from anp.models.identity import AgentIdentity, IdentityProvider, IdentityProviderType, ServiceOrientation
from anp.models.skills import Skill, SkillAttestation, SkillLevel, AttestationType
from anp.models.reputation import ReputationEvent, ReputationEventType
from anp.storage.database import Database
from anp.storage.repositories import IdentityRepository, SkillsRepository, ReputationRepository


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(path)
    yield db
    os.unlink(path)


@pytest.fixture
def identity_repo(temp_db):
    """Create an identity repository with temp database."""
    return IdentityRepository(temp_db)


@pytest.fixture
def skills_repo(temp_db):
    """Create a skills repository with temp database."""
    return SkillsRepository(temp_db)


@pytest.fixture
def reputation_repo(temp_db):
    """Create a reputation repository with temp database."""
    return ReputationRepository(temp_db)


class TestIdentityRepository:
    """Tests for IdentityRepository."""
    
    def test_create_and_get(self, identity_repo):
        """Test creating and retrieving an identity."""
        identity = AgentIdentity(
            id="did:anp:test@moltbook",
            name="TestAgent",
            description="A test agent",
            service_orientation=ServiceOrientation.SERVICE_TO_OTHERS,
            capabilities=["python", "research"],
        )
        
        created = identity_repo.create(identity)
        assert created.id == identity.id
        
        retrieved = identity_repo.get(identity.id)
        assert retrieved is not None
        assert retrieved.name == "TestAgent"
        assert retrieved.service_orientation == ServiceOrientation.SERVICE_TO_OTHERS
        assert "python" in retrieved.capabilities
    
    def test_create_with_providers(self, identity_repo):
        """Test creating identity with linked providers."""
        provider = IdentityProvider(
            type=IdentityProviderType.MOLTBOOK,
            handle="testagent",
            profile_url="https://moltbook.com/u/testagent",
            verified=True,
            verified_at=datetime.now(timezone.utc),
        )
        
        identity = AgentIdentity(
            id="did:anp:test2@moltbook",
            name="TestAgent2",
            identity_providers=[provider],
        )
        
        identity_repo.create(identity)
        
        retrieved = identity_repo.get(identity.id)
        assert len(retrieved.identity_providers) == 1
        assert retrieved.identity_providers[0].handle == "testagent"
        assert retrieved.identity_providers[0].verified is True
    
    def test_get_by_provider(self, identity_repo):
        """Test finding identity by provider."""
        provider = IdentityProvider(
            type=IdentityProviderType.MOLTBOOK,
            handle="uniquehandle",
        )
        
        identity = AgentIdentity(
            id="did:anp:test3@moltbook",
            name="TestAgent3",
            identity_providers=[provider],
        )
        
        identity_repo.create(identity)
        
        found = identity_repo.get_by_provider(
            IdentityProviderType.MOLTBOOK,
            "uniquehandle",
        )
        assert found is not None
        assert found.name == "TestAgent3"
    
    def test_update(self, identity_repo):
        """Test updating an identity."""
        identity = AgentIdentity(
            id="did:anp:test4@moltbook",
            name="OriginalName",
        )
        identity_repo.create(identity)
        
        identity.name = "UpdatedName"
        identity.description = "New description"
        identity_repo.update(identity)
        
        retrieved = identity_repo.get(identity.id)
        assert retrieved.name == "UpdatedName"
        assert retrieved.description == "New description"
    
    def test_delete(self, identity_repo):
        """Test deleting an identity."""
        identity = AgentIdentity(
            id="did:anp:test5@moltbook",
            name="ToDelete",
        )
        identity_repo.create(identity)
        
        deleted = identity_repo.delete(identity.id)
        assert deleted is True
        
        retrieved = identity_repo.get(identity.id)
        assert retrieved is None
    
    def test_list_and_search(self, identity_repo):
        """Test listing and searching identities."""
        # Create several identities
        for i in range(5):
            identity = AgentIdentity(
                id=f"did:anp:list{i}@moltbook",
                name=f"Agent{i}",
                service_orientation=ServiceOrientation.SERVICE_TO_OTHERS if i % 2 == 0 else ServiceOrientation.NEUTRAL,
            )
            identity_repo.create(identity)
        
        # List all
        all_identities = identity_repo.list(limit=10)
        assert len(all_identities) == 5
        
        # Filter by orientation
        sto_identities = identity_repo.list(
            service_orientation=ServiceOrientation.SERVICE_TO_OTHERS,
        )
        assert len(sto_identities) == 3  # 0, 2, 4
        
        # Search by name
        search_results = identity_repo.search("Agent2")
        assert len(search_results) == 1


class TestSkillsRepository:
    """Tests for SkillsRepository."""
    
    @pytest.fixture(autouse=True)
    def setup(self, temp_db):
        """Create an identity for skill tests."""
        self.identity_repo = IdentityRepository(temp_db)
        self.identity = AgentIdentity(
            id="did:anp:skilltest@moltbook",
            name="SkillTestAgent",
        )
        self.identity_repo.create(self.identity)
    
    def test_add_and_get_skill(self, skills_repo):
        """Test adding and retrieving a skill."""
        skill = Skill(
            name="python",
            level=SkillLevel.ADVANCED,
            description="Python programming",
            proof_urls=["https://github.com/test/repo"],
        )
        
        skills_repo.add_skill(self.identity.id, skill)
        
        retrieved = skills_repo.get_skill(self.identity.id, "python")
        assert retrieved is not None
        assert retrieved.level == SkillLevel.ADVANCED
        assert "https://github.com/test/repo" in retrieved.proof_urls
    
    def test_get_all_skills(self, skills_repo):
        """Test getting all skills for an agent."""
        skills_repo.add_skill(self.identity.id, Skill(name="python"))
        skills_repo.add_skill(self.identity.id, Skill(name="javascript"))
        skills_repo.add_skill(self.identity.id, Skill(name="rust"))
        
        skills = skills_repo.get_skills(self.identity.id)
        assert len(skills) == 3
        skill_names = {s.name for s in skills}
        assert skill_names == {"python", "javascript", "rust"}
    
    def test_search_by_skill(self, skills_repo):
        """Test finding agents by skill."""
        skills_repo.add_skill(self.identity.id, Skill(
            name="rare_skill",
            level=SkillLevel.EXPERT,
        ))
        
        results = skills_repo.search_by_skill("rare_skill")
        assert len(results) == 1
        assert results[0]["agent_name"] == "SkillTestAgent"
    
    def test_attestation_flow(self, skills_repo):
        """Test creating and retrieving attestations."""
        skills_repo.add_skill(self.identity.id, Skill(name="testing"))
        
        attestation = SkillAttestation(
            id="att-001",
            skill_name="testing",
            subject_id=self.identity.id,
            attester_id="did:anp:attester@moltbook",
            attestation_type=AttestationType.PEER,
            level=SkillLevel.INTERMEDIATE,
            comment="Verified this agent's testing skills",
        )
        
        created = skills_repo.create_attestation(attestation)
        assert created.id == "att-001"
        
        # Check attestation count updated
        skill = skills_repo.get_skill(self.identity.id, "testing")
        assert skill.attestation_count == 1
        
        # Retrieve attestations
        attestations = skills_repo.get_attestations_for_agent(self.identity.id)
        assert len(attestations) == 1
        assert attestations[0].attester_id == "did:anp:attester@moltbook"


class TestReputationRepository:
    """Tests for ReputationRepository."""
    
    @pytest.fixture(autouse=True)
    def setup(self, temp_db):
        """Create an identity for reputation tests."""
        self.identity_repo = IdentityRepository(temp_db)
        self.identity = AgentIdentity(
            id="did:anp:reptest@moltbook",
            name="ReputationTestAgent",
        )
        self.identity_repo.create(self.identity)
    
    def test_get_or_create_score(self, reputation_repo):
        """Test getting or creating a reputation score."""
        score = reputation_repo.get_or_create_score(self.identity.id)
        
        assert score is not None
        assert score.agent_id == self.identity.id
        assert score.score == 0.5  # Default
        assert score.trust_tier == "unverified"
    
    def test_add_event_updates_score(self, reputation_repo):
        """Test that events update the score."""
        # Initial score
        score = reputation_repo.get_or_create_score(self.identity.id)
        initial_score = score.score
        
        # Add positive event
        event = ReputationEvent(
            id="evt-001",
            agent_id=self.identity.id,
            event_type=ReputationEventType.WORK_COMPLETED,
            delta=0.05,
        )
        reputation_repo.add_event(event)
        
        # Check score increased
        updated_score = reputation_repo.get_score(self.identity.id)
        assert updated_score.score > initial_score
        assert updated_score.total_work_completed == 1
    
    def test_trust_tier_progression(self, reputation_repo):
        """Test trust tier calculation."""
        # Start with basic score
        score = reputation_repo.get_or_create_score(self.identity.id)
        assert score.trust_tier == "unverified"
        
        # Add attestation - should become "claimed"
        score.total_attestations_received = 1
        reputation_repo.update_score(score)
        score = reputation_repo.get_score(self.identity.id)
        assert score.trust_tier == "claimed"
        
        # Complete work and improve score - should progress
        score.score = 0.65
        score.total_work_completed = 5
        reputation_repo.update_score(score)
        score = reputation_repo.get_score(self.identity.id)
        assert score.trust_tier == "verified"
    
    def test_leaderboard(self, reputation_repo, temp_db):
        """Test leaderboard queries."""
        # Create multiple agents with different scores
        for i in range(3):
            identity = AgentIdentity(
                id=f"did:anp:leader{i}@moltbook",
                name=f"Leader{i}",
            )
            IdentityRepository(temp_db).create(identity)
            
            score = reputation_repo.get_or_create_score(identity.id)
            score.score = 0.5 + (i * 0.1)
            score.total_work_completed = 10
            reputation_repo.update_score(score)
        
        # Get leaderboard
        leaders = reputation_repo.get_leaderboard(limit=10, min_work=5)
        assert len(leaders) == 3
        # Should be sorted by score descending
        assert leaders[0].score > leaders[1].score > leaders[2].score


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

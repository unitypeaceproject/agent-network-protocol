"""Tests for the ANP services layer."""
import os
import tempfile
import pytest
from datetime import datetime, timezone

from anp.storage.database import Database
from anp.services.identity_service import IdentityService
from anp.services.skills_service import SkillsService
from anp.services.reputation_service import ReputationService
from anp.services.matchmaking_service import MatchmakingService, WorkRequestStatus
from anp.models.identity import ServiceOrientation, IdentityProviderType
from anp.models.skills import SkillLevel, AttestationType


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    db = Database(db_path=path)
    
    yield db
    
    os.unlink(path)


@pytest.fixture
def identity_service(temp_db):
    """Create an identity service with test database."""
    from anp.storage.repositories.identity_repo import IdentityRepository
    return IdentityService(IdentityRepository(temp_db))


@pytest.fixture
def skills_service(temp_db):
    """Create a skills service with test database."""
    from anp.storage.repositories.skills_repo import SkillsRepository
    from anp.storage.repositories.reputation_repo import ReputationRepository
    return SkillsService(SkillsRepository(temp_db), ReputationRepository(temp_db))


@pytest.fixture
def reputation_service(temp_db):
    """Create a reputation service with test database."""
    from anp.storage.repositories.reputation_repo import ReputationRepository
    return ReputationService(ReputationRepository(temp_db))


@pytest.fixture
def matchmaking_service(identity_service, skills_service, reputation_service):
    """Create a matchmaking service with test services."""
    return MatchmakingService(identity_service, skills_service, reputation_service)


# Identity Service Tests

class TestIdentityService:
    
    def test_create_identity(self, identity_service):
        """Test creating an identity with keypair."""
        identity, private_key = identity_service.create_identity(
            name="TestAgent",
            description="A test agent",
            service_orientation=ServiceOrientation.SERVICE_TO_OTHERS,
            capabilities=["code", "research"],
        )
        
        assert identity.id.startswith("did:anp:")
        assert identity.name == "TestAgent"
        assert identity.description == "A test agent"
        assert identity.public_key is not None
        assert identity.signature is not None
        assert private_key is not None
        assert len(identity.capabilities) == 2
    
    def test_get_identity(self, identity_service):
        """Test retrieving an identity."""
        identity, _ = identity_service.create_identity(name="GetTest")
        
        retrieved = identity_service.get_identity(identity.id)
        assert retrieved is not None
        assert retrieved.name == "GetTest"
    
    def test_update_identity(self, identity_service):
        """Test updating identity fields."""
        identity, _ = identity_service.create_identity(name="UpdateTest")
        
        updated = identity_service.update_identity(
            identity.id,
            description="Updated description",
            avatar_url="https://example.com/avatar.png",
        )
        
        assert updated.description == "Updated description"
        assert updated.avatar_url == "https://example.com/avatar.png"
    
    def test_link_and_verify_provider(self, identity_service):
        """Test linking and verifying an identity provider."""
        identity, _ = identity_service.create_identity(name="ProviderTest")
        
        # Link Moltbook
        success = identity_service.link_provider(
            identity.id,
            IdentityProviderType.MOLTBOOK,
            "TestMolty",
            profile_url="https://moltbook.com/u/TestMolty",
        )
        assert success
        
        # Check not verified yet
        assert not identity_service.is_provider_verified(
            identity.id, IdentityProviderType.MOLTBOOK
        )
        
        # Verify
        verified = identity_service.verify_provider(
            identity.id, IdentityProviderType.MOLTBOOK, "TestMolty"
        )
        assert verified
        
        # Check now verified
        assert identity_service.is_provider_verified(
            identity.id, IdentityProviderType.MOLTBOOK
        )
    
    def test_find_by_provider(self, identity_service):
        """Test finding identity by provider."""
        identity, _ = identity_service.create_identity(name="FindByProvider")
        identity_service.link_provider(
            identity.id, IdentityProviderType.MOLTBOOK, "UniqueMolty"
        )
        
        found = identity_service.find_by_provider(
            IdentityProviderType.MOLTBOOK, "UniqueMolty"
        )
        assert found is not None
        assert found.name == "FindByProvider"
    
    def test_search(self, identity_service):
        """Test searching identities."""
        identity_service.create_identity(
            name="SearchBot",
            description="A bot for searching things",
        )
        identity_service.create_identity(
            name="OtherBot",
            description="Something completely different",
        )
        
        results = identity_service.search("search")
        assert len(results) == 1
        assert results[0].name == "SearchBot"


# Skills Service Tests

class TestSkillsService:
    
    def test_declare_skill(self, skills_service, identity_service):
        """Test declaring a skill."""
        identity, _ = identity_service.create_identity(name="SkillsBot")
        
        skill = skills_service.declare_skill(
            identity.id,
            skill_name="Python",
            level=SkillLevel.ADVANCED,
            description="Python programming",
        )
        
        assert skill.name == "python"  # Normalized to lowercase
        assert skill.level == SkillLevel.ADVANCED
    
    def test_upgrade_skill(self, skills_service, identity_service):
        """Test upgrading a skill level."""
        identity, _ = identity_service.create_identity(name="UpgradeBot")
        
        skills_service.declare_skill(identity.id, "coding", SkillLevel.NOVICE)
        upgraded = skills_service.upgrade_skill_level(
            identity.id, "coding", SkillLevel.INTERMEDIATE
        )
        
        assert upgraded.level == SkillLevel.INTERMEDIATE
    
    def test_attest_skill(self, skills_service, identity_service):
        """Test creating an attestation."""
        subject, _ = identity_service.create_identity(name="Subject")
        attester, attester_key = identity_service.create_identity(name="Attester")
        
        # Subject declares skill
        skills_service.declare_skill(subject.id, "testing", SkillLevel.INTERMEDIATE)
        
        # Attester attests
        attestation = skills_service.attest_skill(
            attester_id=attester.id,
            subject_id=subject.id,
            skill_name="testing",
            attestation_type=AttestationType.PEER,
            level=SkillLevel.INTERMEDIATE,
            comment="Good at testing!",
            private_key=attester_key,
        )
        
        assert attestation.skill_name == "testing"
        assert attestation.signature is not None
        assert attestation.weight == 0.5  # Peer attestation weight
    
    def test_find_agents_with_skill(self, skills_service, identity_service):
        """Test finding agents by skill."""
        agent1, _ = identity_service.create_identity(name="Agent1")
        agent2, _ = identity_service.create_identity(name="Agent2")
        
        skills_service.declare_skill(agent1.id, "rust", SkillLevel.EXPERT)
        skills_service.declare_skill(agent2.id, "rust", SkillLevel.INTERMEDIATE)
        
        results = skills_service.find_agents_with_skill("rust")
        assert len(results) == 2
    
    def test_find_best_match_for_task(self, skills_service, identity_service):
        """Test multi-skill matchmaking."""
        perfect, _ = identity_service.create_identity(name="PerfectMatch")
        partial, _ = identity_service.create_identity(name="PartialMatch")
        
        # Perfect has all skills
        skills_service.declare_skill(perfect.id, "python", SkillLevel.ADVANCED)
        skills_service.declare_skill(perfect.id, "sql", SkillLevel.ADVANCED)
        
        # Partial has one skill
        skills_service.declare_skill(partial.id, "python", SkillLevel.ADVANCED)
        
        matches = skills_service.find_best_match_for_task(
            required_skills=["python", "sql"],
            min_level=SkillLevel.INTERMEDIATE,
        )
        
        assert len(matches) == 2
        assert matches[0]["agent_name"] == "PerfectMatch"
        assert matches[0]["match_score"] == 1.0


# Reputation Service Tests

class TestReputationService:
    
    def test_get_or_create_score(self, reputation_service, identity_service):
        """Test getting/creating reputation score."""
        # First create an identity
        identity, _ = identity_service.create_identity(name="TestAgent")
        
        score = reputation_service.get_score(identity.id)
        
        assert score.agent_id == identity.id
        assert score.score == 0.5  # Default
        assert score.trust_tier == "unverified"
    
    def test_work_completed_increases_score(self, reputation_service, identity_service):
        """Test that completing work increases reputation."""
        identity, _ = identity_service.create_identity(name="WorkerAgent")
        
        initial = reputation_service.get_score(identity.id)
        
        updated = reputation_service.record_work_completed(
            agent_id=identity.id,
            work_id="work-123",
            quality_rating=0.9,
        )
        
        assert updated.score > initial.score
        assert updated.total_work_completed == 1
    
    def test_work_abandoned_decreases_score(self, reputation_service, identity_service):
        """Test that abandoning work decreases reputation."""
        identity, _ = identity_service.create_identity(name="FlakyAgent")
        
        initial = reputation_service.get_score(identity.id)
        
        updated = reputation_service.record_work_abandoned(
            agent_id=identity.id,
            work_id="work-456",
            reason="Got distracted",
        )
        
        assert updated.score < initial.score
        assert updated.total_work_abandoned == 1
    
    def test_trust_tier_progression(self, reputation_service, identity_service):
        """Test trust tier calculations."""
        identity, _ = identity_service.create_identity(name="ProgressionAgent")
        
        # Start as unverified
        score = reputation_service.get_score(identity.id)
        assert score.trust_tier == "unverified"
        
        # Check eligibility for claimed
        eligibility = reputation_service.check_tier_eligibility(identity.id, "claimed")
        assert eligibility["requirements"]["attestations_received"] == 1
    
    def test_fraud_detection_penalty(self, reputation_service, identity_service):
        """Test fraud detection causes severe penalty."""
        identity, _ = identity_service.create_identity(name="FraudAgent")
        
        # First build up some reputation
        reputation_service.record_work_completed(identity.id, "work-1")
        reputation_service.record_work_completed(identity.id, "work-2")
        
        before = reputation_service.get_score(identity.id)
        
        updated = reputation_service.record_fraud_detected(
            agent_id=identity.id,
            description="Sybil attack detected",
        )
        
        assert updated.score < before.score - 0.2  # Severe penalty
        assert updated.honesty < before.honesty
    
    def test_leaderboard(self, reputation_service, identity_service):
        """Test getting the leaderboard."""
        # Create some agents with work history
        for i in range(5):
            identity, _ = identity_service.create_identity(name=f"LeaderboardAgent{i}")
            for j in range(6):  # Minimum 5 work items
                reputation_service.record_work_completed(identity.id, f"work-{i}-{j}")
        
        leaders = reputation_service.get_leaderboard(limit=3, min_work=5)
        assert len(leaders) == 3
    
    def test_value_based_trust(self, reputation_service, identity_service):
        """Test value-based trust thresholds."""
        identity, _ = identity_service.create_identity(name="ValueTestAgent")
        
        # Unverified can't do anything valuable
        assert not reputation_service.is_trustworthy_for_value(identity.id, 50)


# Matchmaking Service Tests

class TestMatchmakingService:
    
    def test_create_work_request(self, matchmaking_service, identity_service):
        """Test creating a work request."""
        requester, _ = identity_service.create_identity(name="Requester")
        
        request = matchmaking_service.create_work_request(
            requester_id=requester.id,
            title="Build a website",
            description="Need a simple portfolio site",
            required_skills=["html", "css", "javascript"],
            min_skill_level=SkillLevel.INTERMEDIATE,
            min_trust_tier="verified",
            estimated_value_usd=100,
        )
        
        assert request.id is not None
        assert request.status == WorkRequestStatus.OPEN
        assert len(request.required_skills) == 3
    
    def test_find_matches(
        self,
        matchmaking_service,
        identity_service,
        skills_service,
        reputation_service,
    ):
        """Test finding matches for a work request."""
        # Create requester
        requester, _ = identity_service.create_identity(name="Requester")
        
        # Create an agent with skills
        agent, _ = identity_service.create_identity(name="WebDev")
        skills_service.declare_skill(agent.id, "html", SkillLevel.ADVANCED)
        skills_service.declare_skill(agent.id, "css", SkillLevel.ADVANCED)
        skills_service.declare_skill(agent.id, "javascript", SkillLevel.INTERMEDIATE)
        
        # Build reputation to verified tier
        for i in range(6):
            reputation_service.record_work_completed(agent.id, f"work-{i}")
        
        # Simulate attestation to get to claimed tier
        import uuid
        from anp.models.reputation import ReputationEvent, ReputationEventType
        reputation_service.repo.add_event(ReputationEvent(
            id=str(uuid.uuid4()),
            agent_id=agent.id,
            event_type=ReputationEventType.ATTESTATION_RECEIVED,
            delta=0.01,
        ))
        
        # Create work request
        request = matchmaking_service.create_work_request(
            requester_id=requester.id,
            title="Web project",
            description="Build something",
            required_skills=["html", "css"],
            min_skill_level=SkillLevel.INTERMEDIATE,
            min_trust_tier="claimed",
            estimated_value_usd=10,
        )
        
        matches = matchmaking_service.find_matches(request.id)
        
        # Should find our agent
        assert len(matches) >= 1
        assert matches[0].agent_name == "WebDev"
        assert matches[0].skill_coverage == 1.0
    
    def test_work_lifecycle(
        self,
        matchmaking_service,
        identity_service,
        skills_service,
        reputation_service,
    ):
        """Test full work lifecycle: create → match → start → complete."""
        # Setup requester and agent
        requester, _ = identity_service.create_identity(name="Requester")
        agent, _ = identity_service.create_identity(name="LifecycleAgent")
        skills_service.declare_skill(agent.id, "testing", SkillLevel.EXPERT)
        
        # Create request
        request = matchmaking_service.create_work_request(
            requester_id=requester.id,
            title="Test task",
            description="Run some tests",
            required_skills=["testing"],
            min_trust_tier="unverified",
        )
        
        # Accept match
        assert matchmaking_service.accept_match(request.id, agent.id)
        assert matchmaking_service.get_work_request(request.id).status == WorkRequestStatus.MATCHED
        
        # Start work
        assert matchmaking_service.start_work(request.id)
        assert matchmaking_service.get_work_request(request.id).status == WorkRequestStatus.IN_PROGRESS
        
        # Complete work
        assert matchmaking_service.complete_work(request.id, quality_rating=0.9)
        assert matchmaking_service.get_work_request(request.id).status == WorkRequestStatus.COMPLETED
        
        # Check reputation updated
        score = reputation_service.get_score(agent.id)
        assert score.total_work_completed == 1
    
    def test_abandon_work(
        self,
        matchmaking_service,
        identity_service,
        skills_service,
        reputation_service,
    ):
        """Test abandoning work penalizes agent."""
        requester, _ = identity_service.create_identity(name="Requester")
        agent, _ = identity_service.create_identity(name="AbandonAgent")
        skills_service.declare_skill(agent.id, "flaky", SkillLevel.NOVICE)
        
        request = matchmaking_service.create_work_request(
            requester_id=requester.id,
            title="Doomed task",
            description="Will be abandoned",
            required_skills=["flaky"],
            min_trust_tier="unverified",
        )
        
        matchmaking_service.accept_match(request.id, agent.id)
        matchmaking_service.start_work(request.id)
        
        before = reputation_service.get_score(agent.id)
        matchmaking_service.abandon_work(request.id, "Changed my mind")
        after = reputation_service.get_score(agent.id)
        
        # Score should decrease
        assert after.score < before.score
        assert after.total_work_abandoned == 1
        
        # Request should be reopened
        assert matchmaking_service.get_work_request(request.id).status == WorkRequestStatus.OPEN
    
    def test_get_open_requests(self, matchmaking_service, identity_service):
        """Test listing open requests."""
        r1, _ = identity_service.create_identity(name="Requester1")
        r2, _ = identity_service.create_identity(name="Requester2")
        
        # Create some requests
        matchmaking_service.create_work_request(
            requester_id=r1.id, title="Task 1", description="", required_skills=["python"]
        )
        matchmaking_service.create_work_request(
            requester_id=r2.id, title="Task 2", description="", required_skills=["rust"]
        )
        
        # Get all
        all_requests = matchmaking_service.get_open_requests()
        assert len(all_requests) == 2
        
        # Filter by skill
        python_requests = matchmaking_service.get_open_requests(skills=["python"])
        assert len(python_requests) == 1
        assert python_requests[0].title == "Task 1"

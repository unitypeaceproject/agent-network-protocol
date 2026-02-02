"""Service for matchmaking agents to work requests."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
import uuid

from anp.models.skills import SkillLevel
from anp.services.identity_service import IdentityService
from anp.services.skills_service import SkillsService
from anp.services.reputation_service import ReputationService


class WorkRequestStatus(str, Enum):
    """Status of a work request."""
    OPEN = "open"
    MATCHED = "matched"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass
class WorkRequest:
    """A request for work that needs to be matched to an agent."""
    id: str
    requester_id: str
    title: str
    description: str
    required_skills: list[str]
    min_skill_level: SkillLevel
    min_trust_tier: str
    estimated_value_usd: float
    status: WorkRequestStatus
    created_at: datetime
    expires_at: Optional[datetime] = None
    matched_agent_id: Optional[str] = None
    matched_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class MatchResult:
    """Result of a matchmaking attempt."""
    agent_id: str
    agent_name: str
    match_score: float
    skill_coverage: float
    trust_tier: str
    reputation_score: float
    skills_matched: list[str]
    skills_missing: list[str]
    reasons: list[str]


class MatchmakingService:
    """Service for matching work requests to capable agents.
    
    This is the core matchmaking algorithm for the Agent Network Protocol.
    It considers:
    - Required skills and skill levels
    - Trust tier requirements
    - Reputation scores
    - Value-based trust thresholds
    - Agent availability (future)
    """
    
    def __init__(
        self,
        identity_service: Optional[IdentityService] = None,
        skills_service: Optional[SkillsService] = None,
        reputation_service: Optional[ReputationService] = None,
    ):
        self.identity_service = identity_service or IdentityService()
        self.skills_service = skills_service or SkillsService()
        self.reputation_service = reputation_service or ReputationService()
        
        # In-memory work request storage (would be a DB in production)
        self._work_requests: dict[str, WorkRequest] = {}
    
    # Work request management
    
    def create_work_request(
        self,
        requester_id: str,
        title: str,
        description: str,
        required_skills: list[str],
        min_skill_level: SkillLevel = SkillLevel.INTERMEDIATE,
        min_trust_tier: str = "verified",
        estimated_value_usd: float = 0.0,
        expires_in_hours: Optional[int] = 24,
        metadata: dict = None,
    ) -> WorkRequest:
        """Create a new work request."""
        now = datetime.now(timezone.utc)
        
        request = WorkRequest(
            id=str(uuid.uuid4()),
            requester_id=requester_id,
            title=title,
            description=description,
            required_skills=[s.lower().strip() for s in required_skills],
            min_skill_level=min_skill_level,
            min_trust_tier=min_trust_tier,
            estimated_value_usd=estimated_value_usd,
            status=WorkRequestStatus.OPEN,
            created_at=now,
            expires_at=now + timedelta(hours=expires_in_hours) if expires_in_hours else None,
            metadata=metadata or {},
        )
        
        self._work_requests[request.id] = request
        return request
    
    def get_work_request(self, request_id: str) -> Optional[WorkRequest]:
        """Get a work request by ID."""
        return self._work_requests.get(request_id)
    
    def cancel_work_request(self, request_id: str) -> bool:
        """Cancel a work request."""
        request = self._work_requests.get(request_id)
        if not request or request.status not in [WorkRequestStatus.OPEN, WorkRequestStatus.MATCHED]:
            return False
        request.status = WorkRequestStatus.CANCELLED
        return True
    
    # Matchmaking
    
    def find_matches(
        self,
        request_id: str,
        limit: int = 10,
    ) -> list[MatchResult]:
        """Find matching agents for a work request."""
        request = self._work_requests.get(request_id)
        if not request or request.status != WorkRequestStatus.OPEN:
            return []
        
        # Get candidates with required skills
        candidates = self.skills_service.find_best_match_for_task(
            required_skills=request.required_skills,
            min_level=request.min_skill_level,
            limit=50,
        )
        
        results = []
        for candidate in candidates:
            match_result = self._evaluate_candidate(candidate, request)
            if match_result:
                results.append(match_result)
        
        # Sort by match score
        results.sort(key=lambda x: -x.match_score)
        return results[:limit]
    
    def _evaluate_candidate(
        self,
        candidate: dict,
        request: WorkRequest,
    ) -> Optional[MatchResult]:
        """Evaluate a single candidate against a work request."""
        agent_id = candidate["agent_id"]
        
        # Get reputation
        rep_score = self.reputation_service.get_score(agent_id)
        trust_tier = rep_score.trust_tier
        
        # Check trust tier requirement
        tier_order = ["unverified", "claimed", "verified", "staked", "trusted", "steward"]
        if tier_order.index(trust_tier) < tier_order.index(request.min_trust_tier):
            return None  # Doesn't meet trust requirements
        
        # Check value-based trust
        if not self.reputation_service.is_trustworthy_for_value(agent_id, request.estimated_value_usd):
            return None  # Value too high for trust level
        
        # Calculate skill coverage
        skills_matched = [s.name for s in candidate.get("skills_matched", [])]
        skills_missing = [s for s in request.required_skills if s not in skills_matched]
        skill_coverage = len(skills_matched) / len(request.required_skills) if request.required_skills else 1.0
        
        # Calculate match score
        # Weighted: skill_coverage (50%), reputation (30%), trust_tier (20%)
        tier_score = tier_order.index(trust_tier) / (len(tier_order) - 1)
        match_score = (
            skill_coverage * 0.5 +
            rep_score.score * 0.3 +
            tier_score * 0.2
        )
        
        # Generate reasons
        reasons = []
        if skill_coverage == 1.0:
            reasons.append("Has all required skills")
        elif skill_coverage >= 0.7:
            reasons.append(f"Has {len(skills_matched)}/{len(request.required_skills)} required skills")
        
        if trust_tier in ["trusted", "steward"]:
            reasons.append(f"High trust tier: {trust_tier}")
        
        if rep_score.score >= 0.8:
            reasons.append(f"Excellent reputation: {rep_score.score:.2f}")
        
        return MatchResult(
            agent_id=agent_id,
            agent_name=candidate["agent_name"],
            match_score=match_score,
            skill_coverage=skill_coverage,
            trust_tier=trust_tier,
            reputation_score=rep_score.score,
            skills_matched=skills_matched,
            skills_missing=skills_missing,
            reasons=reasons,
        )
    
    def accept_match(
        self,
        request_id: str,
        agent_id: str,
    ) -> bool:
        """Accept a match - assign agent to work request."""
        request = self._work_requests.get(request_id)
        if not request or request.status != WorkRequestStatus.OPEN:
            return False
        
        request.matched_agent_id = agent_id
        request.matched_at = datetime.now(timezone.utc)
        request.status = WorkRequestStatus.MATCHED
        return True
    
    def start_work(self, request_id: str) -> bool:
        """Mark work as in progress."""
        request = self._work_requests.get(request_id)
        if not request or request.status != WorkRequestStatus.MATCHED:
            return False
        
        request.status = WorkRequestStatus.IN_PROGRESS
        return True
    
    def complete_work(
        self,
        request_id: str,
        quality_rating: Optional[float] = None,
    ) -> bool:
        """Mark work as completed and update reputation."""
        request = self._work_requests.get(request_id)
        if not request or request.status != WorkRequestStatus.IN_PROGRESS:
            return False
        
        request.status = WorkRequestStatus.COMPLETED
        request.completed_at = datetime.now(timezone.utc)
        
        # Update agent reputation
        if request.matched_agent_id:
            self.reputation_service.record_work_completed(
                agent_id=request.matched_agent_id,
                work_id=request_id,
                requester_id=request.requester_id,
                quality_rating=quality_rating,
            )
        
        return True
    
    def abandon_work(
        self,
        request_id: str,
        reason: str = "",
    ) -> bool:
        """Mark work as abandoned and update reputation."""
        request = self._work_requests.get(request_id)
        if not request or request.status not in [WorkRequestStatus.MATCHED, WorkRequestStatus.IN_PROGRESS]:
            return False
        
        # Reopen the request
        request.status = WorkRequestStatus.OPEN
        
        # Penalize agent reputation
        if request.matched_agent_id:
            self.reputation_service.record_work_abandoned(
                agent_id=request.matched_agent_id,
                work_id=request_id,
                reason=reason,
            )
        
        request.matched_agent_id = None
        request.matched_at = None
        return True
    
    # Discovery
    
    def get_open_requests(
        self,
        skills: Optional[list[str]] = None,
        max_value: Optional[float] = None,
        limit: int = 50,
    ) -> list[WorkRequest]:
        """Get open work requests, optionally filtered."""
        requests = [
            r for r in self._work_requests.values()
            if r.status == WorkRequestStatus.OPEN
        ]
        
        if skills:
            skills_lower = [s.lower() for s in skills]
            requests = [
                r for r in requests
                if any(s in skills_lower for s in r.required_skills)
            ]
        
        if max_value is not None:
            requests = [r for r in requests if r.estimated_value_usd <= max_value]
        
        # Sort by creation time (newest first)
        requests.sort(key=lambda x: x.created_at, reverse=True)
        return requests[:limit]
    
    def get_my_work(
        self,
        agent_id: str,
        include_completed: bool = False,
    ) -> list[WorkRequest]:
        """Get work requests assigned to an agent."""
        statuses = [WorkRequestStatus.MATCHED, WorkRequestStatus.IN_PROGRESS]
        if include_completed:
            statuses.append(WorkRequestStatus.COMPLETED)
        
        return [
            r for r in self._work_requests.values()
            if r.matched_agent_id == agent_id and r.status in statuses
        ]
    
    def get_my_requests(
        self,
        requester_id: str,
        include_completed: bool = False,
    ) -> list[WorkRequest]:
        """Get work requests created by a requester."""
        requests = [
            r for r in self._work_requests.values()
            if r.requester_id == requester_id
        ]
        
        if not include_completed:
            requests = [
                r for r in requests
                if r.status not in [WorkRequestStatus.COMPLETED, WorkRequestStatus.CANCELLED]
            ]
        
        return requests

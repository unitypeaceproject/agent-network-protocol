"""Service for reputation management operations."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from anp.models.reputation import ReputationEvent, ReputationEventType, ReputationScore
from anp.storage.repositories.reputation_repo import ReputationRepository


class ReputationService:
    """High-level service for managing reputation.
    
    Provides business logic for:
    - Recording work outcomes (completed, abandoned, reviewed)
    - Trust tier calculation and progression
    - Reputation querying and leaderboards
    - Fraud detection and penalties
    """
    
    # Trust tier thresholds
    TIER_THRESHOLDS = {
        "steward": {"score": 0.9, "work": 50, "completion_rate": 0.95},
        "trusted": {"score": 0.8, "work": 20, "completion_rate": 0.90},
        "staked": {"score": 0.7, "work": 10, "completion_rate": 0.85},
        "verified": {"score": 0.6, "work": 5, "completion_rate": 0.0},
        "claimed": {"attestations": 1},
        "unverified": {},
    }
    
    def __init__(self, repo: Optional[ReputationRepository] = None):
        self.repo = repo or ReputationRepository()
    
    # Score access
    
    def get_score(self, agent_id: str) -> ReputationScore:
        """Get an agent's reputation score (creates if needed)."""
        return self.repo.get_or_create_score(agent_id)
    
    def get_trust_tier(self, agent_id: str) -> str:
        """Get an agent's current trust tier."""
        score = self.get_score(agent_id)
        return score.trust_tier
    
    # Work lifecycle events
    
    def record_work_completed(
        self,
        agent_id: str,
        work_id: str,
        requester_id: Optional[str] = None,
        quality_rating: Optional[float] = None,
    ) -> ReputationScore:
        """Record that an agent completed a work item.
        
        quality_rating: 0.0-1.0 rating from requester (optional)
        """
        delta = 0.02  # Base delta for completion
        if quality_rating is not None:
            # Bonus or penalty based on quality
            delta += (quality_rating - 0.5) * 0.02
        
        self.repo.add_event(ReputationEvent(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            event_type=ReputationEventType.WORK_COMPLETED,
            delta=delta,
            related_agent_id=requester_id,
            related_work_id=work_id,
            comment=f"Completed work {work_id}" + (f" (quality: {quality_rating:.2f})" if quality_rating else ""),
        ))
        
        return self.get_score(agent_id)
    
    def record_work_abandoned(
        self,
        agent_id: str,
        work_id: str,
        reason: str = "",
    ) -> ReputationScore:
        """Record that an agent abandoned a work item."""
        self.repo.add_event(ReputationEvent(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            event_type=ReputationEventType.WORK_ABANDONED,
            delta=-0.05,  # Penalty for abandonment
            related_work_id=work_id,
            comment=f"Abandoned work {work_id}" + (f": {reason}" if reason else ""),
        ))
        
        return self.get_score(agent_id)
    
    def record_positive_review(
        self,
        agent_id: str,
        reviewer_id: str,
        work_id: Optional[str] = None,
        comment: str = "",
    ) -> ReputationScore:
        """Record a positive review/feedback."""
        self.repo.add_event(ReputationEvent(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            event_type=ReputationEventType.POSITIVE_REVIEW,
            delta=0.015,
            related_agent_id=reviewer_id,
            related_work_id=work_id,
            comment=comment or "Positive review",
        ))
        
        return self.get_score(agent_id)
    
    def record_negative_review(
        self,
        agent_id: str,
        reviewer_id: str,
        work_id: Optional[str] = None,
        comment: str = "",
    ) -> ReputationScore:
        """Record a negative review/feedback."""
        self.repo.add_event(ReputationEvent(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            event_type=ReputationEventType.NEGATIVE_REVIEW,
            delta=-0.02,
            related_agent_id=reviewer_id,
            related_work_id=work_id,
            comment=comment or "Negative review",
        ))
        
        return self.get_score(agent_id)
    
    # Fraud handling
    
    def record_fraud_detected(
        self,
        agent_id: str,
        detector_id: Optional[str] = None,
        proof_url: Optional[str] = None,
        description: str = "",
    ) -> ReputationScore:
        """Record a fraud detection event.
        
        This is a severe penalty and should only be used after
        verification through the dispute resolution process.
        """
        self.repo.add_event(ReputationEvent(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            event_type=ReputationEventType.FRAUD_DETECTED,
            delta=-0.25,  # Severe penalty
            related_agent_id=detector_id,
            proof_url=proof_url,
            comment=description or "Fraud detected",
        ))
        
        return self.get_score(agent_id)
    
    # Trust tier operations
    
    def check_tier_eligibility(self, agent_id: str, target_tier: str) -> dict:
        """Check if an agent is eligible for a trust tier.
        
        Returns a dict with:
        - eligible: bool
        - current_tier: str
        - requirements: dict of what's needed
        - met: dict of which requirements are met
        """
        score = self.get_score(agent_id)
        thresholds = self.TIER_THRESHOLDS.get(target_tier, {})
        
        total_work = score.total_work_completed + score.total_work_abandoned
        completion_rate = score.total_work_completed / total_work if total_work > 0 else 0.5
        
        requirements = {}
        met = {}
        
        if "score" in thresholds:
            requirements["score"] = thresholds["score"]
            met["score"] = score.score >= thresholds["score"]
        
        if "work" in thresholds:
            requirements["work_completed"] = thresholds["work"]
            met["work_completed"] = score.total_work_completed >= thresholds["work"]
        
        if "completion_rate" in thresholds:
            requirements["completion_rate"] = thresholds["completion_rate"]
            met["completion_rate"] = completion_rate >= thresholds["completion_rate"]
        
        if "attestations" in thresholds:
            requirements["attestations_received"] = thresholds["attestations"]
            met["attestations_received"] = score.total_attestations_received >= thresholds["attestations"]
        
        eligible = all(met.values()) if met else target_tier == "unverified"
        
        return {
            "eligible": eligible,
            "current_tier": score.trust_tier,
            "target_tier": target_tier,
            "requirements": requirements,
            "met": met,
            "current_values": {
                "score": score.score,
                "work_completed": score.total_work_completed,
                "completion_rate": completion_rate,
                "attestations_received": score.total_attestations_received,
            },
        }
    
    def get_tier_progression(self, agent_id: str) -> dict:
        """Get an agent's progress toward the next tier."""
        score = self.get_score(agent_id)
        tier_order = ["unverified", "claimed", "verified", "staked", "trusted", "steward"]
        
        current_idx = tier_order.index(score.trust_tier)
        if current_idx >= len(tier_order) - 1:
            return {
                "current_tier": score.trust_tier,
                "next_tier": None,
                "message": "Maximum tier reached",
            }
        
        next_tier = tier_order[current_idx + 1]
        eligibility = self.check_tier_eligibility(agent_id, next_tier)
        
        # Calculate progress percentage
        progress_items = []
        for key, required in eligibility["requirements"].items():
            current = eligibility["current_values"].get(key, 0)
            if isinstance(required, (int, float)) and required > 0:
                progress_items.append(min(1.0, current / required))
        
        progress = sum(progress_items) / len(progress_items) if progress_items else 0
        
        return {
            "current_tier": score.trust_tier,
            "next_tier": next_tier,
            "progress": progress,
            "eligibility": eligibility,
        }
    
    # Leaderboard & Discovery
    
    def get_leaderboard(
        self,
        limit: int = 50,
        min_work: int = 5,
    ) -> list[ReputationScore]:
        """Get top agents by reputation score."""
        return self.repo.get_leaderboard(limit=limit, min_work=min_work)
    
    def get_agents_by_tier(
        self,
        tier: str,
        limit: int = 100,
    ) -> list[ReputationScore]:
        """Get agents at a specific trust tier."""
        return self.repo.get_by_tier(tier, limit=limit)
    
    def get_activity_history(
        self,
        agent_id: str,
        limit: int = 50,
        event_type: Optional[ReputationEventType] = None,
    ) -> list[ReputationEvent]:
        """Get reputation events for an agent."""
        return self.repo.get_events(agent_id, limit=limit, event_type=event_type)
    
    # Scoring helpers
    
    def calculate_dimension_scores(self, agent_id: str) -> dict:
        """Get detailed dimension breakdown for an agent."""
        score = self.get_score(agent_id)
        return {
            "overall": score.score,
            "reliability": score.reliability,
            "quality": score.quality,
            "helpfulness": score.helpfulness,
            "honesty": score.honesty,
        }
    
    def is_trustworthy_for_value(self, agent_id: str, value_usd: float) -> bool:
        """Check if an agent is trustworthy enough for a value threshold.
        
        Higher values require higher trust tiers.
        """
        score = self.get_score(agent_id)
        tier = score.trust_tier
        
        # Value limits by tier
        tier_limits = {
            "unverified": 0,
            "claimed": 10,
            "verified": 100,
            "staked": 1000,
            "trusted": 10000,
            "steward": float("inf"),
        }
        
        return value_usd <= tier_limits.get(tier, 0)

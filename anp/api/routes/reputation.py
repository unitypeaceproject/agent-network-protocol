"""Reputation management API routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

from anp.services import ReputationService

router = APIRouter()
reputation_service = ReputationService()


# Request/Response models

class ReputationScoreResponse(BaseModel):
    """Reputation score details."""
    agent_id: str
    score: float
    trust_tier: str
    dimensions: dict
    work_completed: int
    work_abandoned: int
    completion_rate: float
    attestation_count: int


class RecordWorkRequest(BaseModel):
    """Request to record work completion/abandonment."""
    work_id: str = Field(..., description="Work request ID")
    requester_id: str = Field(..., description="ID of the work requester")


class RecordReviewRequest(BaseModel):
    """Request to record a review."""
    work_id: str
    reviewer_id: str
    is_positive: bool
    comment: Optional[str] = Field(None, max_length=500)


class FraudReportRequest(BaseModel):
    """Request to report fraud."""
    evidence: str = Field(..., description="Description of fraudulent behavior")


class LeaderboardEntry(BaseModel):
    """Leaderboard entry."""
    rank: int
    agent_id: str
    agent_name: str
    score: float
    trust_tier: str
    work_completed: int


# Static routes MUST come before dynamic routes

@router.get("/leaderboard")
async def get_leaderboard(
    limit: int = 50,
    min_work_completed: int = 0,
):
    """Get the reputation leaderboard.
    
    Shows top agents by reputation score.
    """
    leaders = reputation_service.get_leaderboard(
        limit=limit,
        min_work_completed=min_work_completed,
    )
    
    return {
        "leaderboard": [
            LeaderboardEntry(
                rank=i + 1,
                agent_id=l["agent_id"],
                agent_name=l.get("agent_name", ""),
                score=l["score"],
                trust_tier=l["trust_tier"],
                work_completed=l["work_completed"],
            )
            for i, l in enumerate(leaders)
        ],
        "count": len(leaders),
    }


@router.get("/tiers")
async def get_trust_tiers():
    """Get trust tier definitions and requirements."""
    return {
        "tiers": [
            {
                "name": "unverified",
                "description": "No attestations yet",
                "requirements": "Default tier",
                "max_value_usd": 0,
            },
            {
                "name": "claimed",
                "description": "Has at least one attestation",
                "requirements": "1+ attestation",
                "max_value_usd": 10,
            },
            {
                "name": "verified",
                "description": "Established track record",
                "requirements": "Score ≥0.6, 5+ work completed",
                "max_value_usd": 100,
            },
            {
                "name": "staked",
                "description": "Significant commitment",
                "requirements": "Score ≥0.7, 10+ work, 85% completion rate",
                "max_value_usd": 1000,
            },
            {
                "name": "trusted",
                "description": "High reliability",
                "requirements": "Score ≥0.8, 20+ work, 90% completion rate",
                "max_value_usd": 10000,
            },
            {
                "name": "steward",
                "description": "Pillar of the community",
                "requirements": "Score ≥0.9, 50+ work, 95% completion rate",
                "max_value_usd": None,  # Unlimited
            },
        ],
    }


# Dynamic routes (must come after static routes)

@router.get("/{agent_id}", response_model=ReputationScoreResponse)
async def get_reputation(agent_id: str):
    """Get an agent's reputation score and details."""
    score = reputation_service.get_score(agent_id)
    
    # Calculate completion rate
    total = score.total_work_completed + score.total_work_abandoned
    completion_rate = score.total_work_completed / total if total > 0 else 0.0
    
    return ReputationScoreResponse(
        agent_id=agent_id,
        score=score.score,
        trust_tier=score.trust_tier,
        dimensions={
            "reliability": score.reliability,
            "quality": score.quality,
            "helpfulness": score.helpfulness,
            "honesty": score.honesty,
        },
        work_completed=score.total_work_completed,
        work_abandoned=score.total_work_abandoned,
        completion_rate=completion_rate,
        attestation_count=score.total_attestations_received,
    )


@router.post("/{agent_id}/work-completed")
async def record_work_completed(
    agent_id: str,
    request: RecordWorkRequest,
    quality_rating: Optional[float] = None,
    x_agent_id: str = Header(..., description="Requester's agent ID"),
):
    """Record that an agent completed work.
    
    Should be called by the work requester when work is completed satisfactorily.
    Optionally include a quality rating (0.0 - 1.0).
    """
    if x_agent_id != request.requester_id:
        raise HTTPException(status_code=403, detail="Only the requester can record completion")
    
    success = reputation_service.record_work_completed(
        agent_id=agent_id,
        work_id=request.work_id,
        requester_id=request.requester_id,
        quality_rating=quality_rating,
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to record work completion")
    
    # Get updated score
    score = reputation_service.get_score(agent_id)
    
    return {
        "status": "recorded",
        "agent_id": agent_id,
        "work_id": request.work_id,
        "new_score": score.score,
        "new_tier": score.trust_tier,
    }


@router.post("/{agent_id}/work-abandoned")
async def record_work_abandoned(
    agent_id: str,
    request: RecordWorkRequest,
    reason: str = "",
    x_agent_id: str = Header(..., description="Requester's agent ID"),
):
    """Record that an agent abandoned work.
    
    Called when an agent fails to complete assigned work.
    This negatively impacts their reputation score.
    """
    if x_agent_id != request.requester_id:
        raise HTTPException(status_code=403, detail="Only the requester can record abandonment")
    
    success = reputation_service.record_work_abandoned(
        agent_id=agent_id,
        work_id=request.work_id,
        reason=reason,
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to record work abandonment")
    
    score = reputation_service.get_score(agent_id)
    
    return {
        "status": "recorded",
        "agent_id": agent_id,
        "work_id": request.work_id,
        "new_score": score.score,
        "new_tier": score.trust_tier,
    }


@router.post("/{agent_id}/review")
async def record_review(
    agent_id: str,
    request: RecordReviewRequest,
    x_agent_id: str = Header(..., description="Reviewer's agent ID"),
):
    """Record a review for an agent.
    
    Reviews affect the agent's reputation score. Positive reviews
    boost the score, negative reviews lower it.
    """
    if x_agent_id != request.reviewer_id:
        raise HTTPException(status_code=403, detail="Reviewer ID must match authenticated agent")
    
    success = reputation_service.record_review(
        agent_id=agent_id,
        work_id=request.work_id,
        reviewer_id=request.reviewer_id,
        is_positive=request.is_positive,
        comment=request.comment,
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to record review")
    
    return {
        "status": "recorded",
        "agent_id": agent_id,
        "review_type": "positive" if request.is_positive else "negative",
    }


@router.post("/{agent_id}/fraud")
async def report_fraud(
    agent_id: str,
    request: FraudReportRequest,
    x_agent_id: str = Header(..., description="Reporter's agent ID"),
):
    """Report fraudulent behavior by an agent.
    
    Fraud reports are severe and significantly impact reputation.
    Include detailed evidence to support the report.
    """
    success = reputation_service.record_fraud(
        agent_id=agent_id,
        evidence=request.evidence,
        reporter_id=x_agent_id,
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to record fraud report")
    
    return {
        "status": "reported",
        "agent_id": agent_id,
        "reporter_id": x_agent_id,
        "message": "Fraud report recorded. Agent's reputation has been penalized.",
    }


@router.get("/{agent_id}/history")
async def get_reputation_history(
    agent_id: str,
    limit: int = 50,
):
    """Get reputation event history for an agent.
    
    Shows the events that have affected the agent's reputation score.
    """
    events = reputation_service.get_history(agent_id, limit)
    
    return {
        "agent_id": agent_id,
        "events": [
            {
                "type": e.event_type.value,
                "description": e.description,
                "score_change": e.score_change,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
        "count": len(events),
    }


@router.get("/{agent_id}/trustworthy")
async def check_trustworthiness(
    agent_id: str,
    value_usd: float = 0.0,
):
    """Check if an agent is trustworthy for a given value.
    
    Higher value transactions require higher trust tiers.
    """
    is_trustworthy = reputation_service.is_trustworthy_for_value(
        agent_id=agent_id,
        value_usd=value_usd,
    )
    
    score = reputation_service.get_score(agent_id)
    
    return {
        "agent_id": agent_id,
        "value_usd": value_usd,
        "is_trustworthy": is_trustworthy,
        "current_tier": score.trust_tier,
        "current_score": score.score,
    }

"""Matchmaking API routes for work requests."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

from anp.models.skills import SkillLevel
from anp.services import MatchmakingService, WorkRequestStatus

router = APIRouter()
matchmaking_service = MatchmakingService()


# Request/Response models

class CreateWorkRequestBody(BaseModel):
    """Request to create a new work request."""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., max_length=2000)
    required_skills: list[str] = Field(..., min_length=1)
    min_skill_level: SkillLevel = Field(SkillLevel.INTERMEDIATE)
    min_trust_tier: str = Field("verified")
    estimated_value_usd: float = Field(0.0, ge=0)
    expires_in_hours: Optional[int] = Field(24, ge=1)
    metadata: dict = Field(default_factory=dict)


class WorkRequestResponse(BaseModel):
    """Work request details."""
    id: str
    requester_id: str
    title: str
    description: str
    required_skills: list[str]
    min_skill_level: str
    min_trust_tier: str
    estimated_value_usd: float
    status: str
    created_at: str
    expires_at: Optional[str]
    matched_agent_id: Optional[str]
    matched_at: Optional[str]
    completed_at: Optional[str]


class MatchResultResponse(BaseModel):
    """Match result for a work request."""
    agent_id: str
    agent_name: str
    match_score: float
    skill_coverage: float
    trust_tier: str
    reputation_score: float
    skills_matched: list[str]
    skills_missing: list[str]
    reasons: list[str]


# Routes

@router.post("/requests", response_model=WorkRequestResponse)
async def create_work_request(
    request: CreateWorkRequestBody,
    x_agent_id: str = Header(..., description="Your agent ID"),
):
    """Create a new work request.
    
    Work requests are broadcast to the network and matched with
    capable agents based on skills, trust tier, and reputation.
    """
    work_request = matchmaking_service.create_work_request(
        requester_id=x_agent_id,
        title=request.title,
        description=request.description,
        required_skills=request.required_skills,
        min_skill_level=request.min_skill_level,
        min_trust_tier=request.min_trust_tier,
        estimated_value_usd=request.estimated_value_usd,
        expires_in_hours=request.expires_in_hours,
        metadata=request.metadata,
    )
    
    return _work_request_to_response(work_request)


@router.get("/requests/{request_id}", response_model=WorkRequestResponse)
async def get_work_request(request_id: str):
    """Get a work request by ID."""
    work_request = matchmaking_service.get_work_request(request_id)
    if not work_request:
        raise HTTPException(status_code=404, detail="Work request not found")
    
    return _work_request_to_response(work_request)


@router.post("/requests/{request_id}/cancel")
async def cancel_work_request(
    request_id: str,
    x_agent_id: str = Header(..., description="Your agent ID"),
):
    """Cancel a work request.
    
    Only the requester can cancel. Cannot cancel if work is in progress.
    """
    work_request = matchmaking_service.get_work_request(request_id)
    if not work_request:
        raise HTTPException(status_code=404, detail="Work request not found")
    
    if work_request.requester_id != x_agent_id:
        raise HTTPException(status_code=403, detail="Only the requester can cancel")
    
    success = matchmaking_service.cancel_work_request(request_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel request in current state")
    
    return {"status": "cancelled", "request_id": request_id}


@router.get("/requests/{request_id}/matches", response_model=list[MatchResultResponse])
async def find_matches(
    request_id: str,
    limit: int = 10,
):
    """Find matching agents for a work request.
    
    Returns agents sorted by match score, considering:
    - Skill coverage (50%)
    - Reputation score (30%)
    - Trust tier (20%)
    """
    matches = matchmaking_service.find_matches(request_id, limit)
    
    return [
        MatchResultResponse(
            agent_id=m.agent_id,
            agent_name=m.agent_name,
            match_score=m.match_score,
            skill_coverage=m.skill_coverage,
            trust_tier=m.trust_tier,
            reputation_score=m.reputation_score,
            skills_matched=m.skills_matched,
            skills_missing=m.skills_missing,
            reasons=m.reasons,
        )
        for m in matches
    ]


@router.post("/requests/{request_id}/accept/{agent_id}")
async def accept_match(
    request_id: str,
    agent_id: str,
    x_agent_id: str = Header(..., description="Your agent ID"),
):
    """Accept a match and assign an agent to the work request.
    
    Only the requester can accept matches.
    """
    work_request = matchmaking_service.get_work_request(request_id)
    if not work_request:
        raise HTTPException(status_code=404, detail="Work request not found")
    
    if work_request.requester_id != x_agent_id:
        raise HTTPException(status_code=403, detail="Only the requester can accept matches")
    
    success = matchmaking_service.accept_match(request_id, agent_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot accept match in current state")
    
    return {
        "status": "matched",
        "request_id": request_id,
        "agent_id": agent_id,
    }


@router.post("/requests/{request_id}/start")
async def start_work(
    request_id: str,
    x_agent_id: str = Header(..., description="Your agent ID"),
):
    """Mark work as started/in progress.
    
    Only the matched agent can start work.
    """
    work_request = matchmaking_service.get_work_request(request_id)
    if not work_request:
        raise HTTPException(status_code=404, detail="Work request not found")
    
    if work_request.matched_agent_id != x_agent_id:
        raise HTTPException(status_code=403, detail="Only the matched agent can start work")
    
    success = matchmaking_service.start_work(request_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot start work in current state")
    
    return {"status": "in_progress", "request_id": request_id}


@router.post("/requests/{request_id}/complete")
async def complete_work(
    request_id: str,
    quality_rating: Optional[float] = None,
    x_agent_id: str = Header(..., description="Your agent ID"),
):
    """Mark work as completed.
    
    Only the requester can mark work as complete. This updates the
    agent's reputation positively.
    """
    work_request = matchmaking_service.get_work_request(request_id)
    if not work_request:
        raise HTTPException(status_code=404, detail="Work request not found")
    
    if work_request.requester_id != x_agent_id:
        raise HTTPException(status_code=403, detail="Only the requester can mark complete")
    
    success = matchmaking_service.complete_work(request_id, quality_rating)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot complete work in current state")
    
    return {
        "status": "completed",
        "request_id": request_id,
        "quality_rating": quality_rating,
    }


@router.post("/requests/{request_id}/abandon")
async def abandon_work(
    request_id: str,
    reason: str = "",
    x_agent_id: str = Header(..., description="Your agent ID"),
):
    """Abandon a work request.
    
    Can be called by the matched agent. This negatively impacts
    their reputation and reopens the work request.
    """
    work_request = matchmaking_service.get_work_request(request_id)
    if not work_request:
        raise HTTPException(status_code=404, detail="Work request not found")
    
    if work_request.matched_agent_id != x_agent_id:
        raise HTTPException(status_code=403, detail="Only the matched agent can abandon")
    
    success = matchmaking_service.abandon_work(request_id, reason)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot abandon work in current state")
    
    return {
        "status": "abandoned",
        "request_id": request_id,
        "reopened": True,
    }


@router.get("/requests")
async def list_open_requests(
    skills: Optional[str] = None,
    max_value: Optional[float] = None,
    limit: int = 50,
):
    """List open work requests.
    
    Optionally filter by skills (comma-separated) and max value.
    """
    skill_list = skills.split(",") if skills else None
    
    requests = matchmaking_service.get_open_requests(
        skills=skill_list,
        max_value=max_value,
        limit=limit,
    )
    
    return {
        "requests": [_work_request_to_response(r) for r in requests],
        "count": len(requests),
        "filters": {
            "skills": skill_list,
            "max_value": max_value,
        },
    }


@router.get("/my-work")
async def get_my_work(
    include_completed: bool = False,
    x_agent_id: str = Header(..., description="Your agent ID"),
):
    """Get work requests assigned to you."""
    requests = matchmaking_service.get_my_work(
        agent_id=x_agent_id,
        include_completed=include_completed,
    )
    
    return {
        "work": [_work_request_to_response(r) for r in requests],
        "count": len(requests),
    }


@router.get("/my-requests")
async def get_my_requests(
    include_completed: bool = False,
    x_agent_id: str = Header(..., description="Your agent ID"),
):
    """Get work requests you've created."""
    requests = matchmaking_service.get_my_requests(
        requester_id=x_agent_id,
        include_completed=include_completed,
    )
    
    return {
        "requests": [_work_request_to_response(r) for r in requests],
        "count": len(requests),
    }


# Helper functions

def _work_request_to_response(work_request) -> WorkRequestResponse:
    """Convert a WorkRequest to a response model."""
    return WorkRequestResponse(
        id=work_request.id,
        requester_id=work_request.requester_id,
        title=work_request.title,
        description=work_request.description,
        required_skills=work_request.required_skills,
        min_skill_level=work_request.min_skill_level.value,
        min_trust_tier=work_request.min_trust_tier,
        estimated_value_usd=work_request.estimated_value_usd,
        status=work_request.status.value,
        created_at=work_request.created_at.isoformat(),
        expires_at=work_request.expires_at.isoformat() if work_request.expires_at else None,
        matched_agent_id=work_request.matched_agent_id,
        matched_at=work_request.matched_at.isoformat() if work_request.matched_at else None,
        completed_at=work_request.completed_at.isoformat() if work_request.completed_at else None,
    )

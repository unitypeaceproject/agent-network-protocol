"""Skills management API routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

from anp.models.skills import SkillLevel, AttestationType
from anp.services import SkillsService

router = APIRouter()
skills_service = SkillsService()


# Request/Response models

class DeclareSkillRequest(BaseModel):
    """Request to declare a skill."""
    skill_name: str = Field(..., min_length=1, max_length=100, description="Skill name")
    level: SkillLevel = Field(SkillLevel.NOVICE, description="Self-assessed proficiency level")
    description: Optional[str] = Field(None, description="Description of skill")
    proof_urls: list[str] = Field(default_factory=list, description="URLs to evidence of skill")


class AttestSkillRequest(BaseModel):
    """Request to attest another agent's skill."""
    agent_id: str = Field(..., description="Agent ID to attest")
    skill_name: str = Field(..., min_length=1, max_length=100)
    attestation_type: AttestationType = Field(AttestationType.PEER)
    evidence_url: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=500)


class SkillResponse(BaseModel):
    """Skill details response."""
    name: str
    level: str
    attestation_count: int
    verified: bool  # True if attestation_count >= 2
    proof_urls: list[str]


class AgentSkillsResponse(BaseModel):
    """Agent's skills response."""
    agent_id: str
    skills: list[SkillResponse]
    total: int


class SkillSearchResult(BaseModel):
    """Result from skill-based agent search."""
    agent_id: str
    agent_name: str
    skill_name: str
    skill_level: str
    attestation_count: int


# Static routes MUST come before dynamic routes

@router.get("/levels")
async def get_skill_levels():
    """Get available skill levels and their descriptions."""
    return {
        "levels": [
            {"value": "novice", "description": "Basic understanding, learning"},
            {"value": "beginner", "description": "Can do simple tasks with guidance"},
            {"value": "intermediate", "description": "Can work independently on most tasks"},
            {"value": "advanced", "description": "Deep expertise, can handle complex tasks"},
            {"value": "expert", "description": "Mastery level, can teach others"},
        ],
    }


@router.get("/attestation-types")
async def get_attestation_types():
    """Get available attestation types and their weights."""
    return {
        "types": [
            {"value": "self", "weight": 0.1, "description": "Self-declared (minimal weight)"},
            {"value": "peer", "weight": 0.5, "description": "Peer attestation"},
            {"value": "challenge", "weight": 0.8, "description": "Passed a skill challenge"},
            {"value": "human", "weight": 1.0, "description": "Human verification"},
            {"value": "work", "weight": 1.2, "description": "Demonstrated through completed work"},
        ],
    }


@router.post("/attest")
async def attest_skill(
    request: AttestSkillRequest,
    x_agent_id: str = Header(..., description="Your agent ID for authentication"),
):
    """Attest another agent's skill.
    
    Different attestation types have different weights:
    - SELF: 0.1 (minimal weight)
    - PEER: 0.5 (standard peer attestation)
    - CHALLENGE: 0.8 (passed a skill challenge)
    - HUMAN: 1.0 (human verification)
    - WORK: 1.2 (demonstrated through completed work)
    """
    if x_agent_id == request.agent_id:
        raise HTTPException(status_code=400, detail="Cannot attest your own skills (use declare)")
    
    attestation = skills_service.attest_skill(
        agent_id=request.agent_id,
        skill_name=request.skill_name,
        attester_id=x_agent_id,
        attestation_type=request.attestation_type,
        evidence_url=request.evidence_url,
        notes=request.notes,
    )
    
    if not attestation:
        raise HTTPException(status_code=400, detail="Failed to create attestation")
    
    return {
        "status": "attested",
        "attestation": {
            "agent_id": request.agent_id,
            "skill_name": request.skill_name,
            "attester_id": x_agent_id,
            "type": request.attestation_type.value,
        },
    }


@router.post("/match")
async def find_multi_skill_match(
    required_skills: list[str],
    min_level: SkillLevel = SkillLevel.INTERMEDIATE,
    limit: int = 10,
):
    """Find agents who have multiple required skills.
    
    Returns agents sorted by how many required skills they have
    and their overall skill level.
    """
    matches = skills_service.find_best_match_for_task(
        required_skills=required_skills,
        min_level=min_level,
        limit=limit,
    )
    
    return {
        "required_skills": required_skills,
        "min_level": min_level.value,
        "matches": [
            {
                "agent_id": m["agent_id"],
                "agent_name": m.get("agent_name", ""),
                "skills_matched": [
                    {"name": s.name, "level": s.level.value}
                    for s in m.get("skills_matched", [])
                ],
                "skills_missing": m.get("skills_missing", []),
                "match_score": m.get("match_score", 0),
            }
            for m in matches
        ],
        "count": len(matches),
    }


@router.get("/search/{skill_name}")
async def find_agents_by_skill(
    skill_name: str,
    min_level: Optional[SkillLevel] = None,
    verified_only: bool = False,
    limit: int = 50,
):
    """Find agents with a specific skill.
    
    Useful for matchmaking - find agents who can do what you need.
    """
    agents = skills_service.find_agents_by_skill(
        skill_name=skill_name,
        min_level=min_level,
        verified_only=verified_only,
        limit=limit,
    )
    
    return {
        "skill_name": skill_name,
        "filters": {
            "min_level": min_level.value if min_level else None,
            "verified_only": verified_only,
        },
        "results": [
            {
                "agent_id": a["agent_id"],
                "agent_name": a.get("agent_name", ""),
                "level": a["level"],
                "attestation_count": a["attestation_count"],
                "verified": a["verified"],
            }
            for a in agents
        ],
        "count": len(agents),
    }


# Dynamic routes (must come after static routes)

@router.post("/{agent_id}/declare")
async def declare_skill(
    agent_id: str,
    request: DeclareSkillRequest,
    x_agent_id: str = Header(..., description="Your agent ID for authentication"),
):
    """Declare a skill for yourself.
    
    Skills start unverified. Get attestations from peers, complete challenges,
    or provide work evidence to verify them.
    """
    if x_agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Can only declare skills for yourself")
    
    skill = skills_service.declare_skill(
        agent_id=agent_id,
        skill_name=request.skill_name,
        level=request.level,
        description=request.description or "",
        proof_urls=request.proof_urls,
    )
    
    if not skill:
        raise HTTPException(status_code=400, detail="Failed to declare skill")
    
    return {
        "status": "declared",
        "skill": {
            "name": skill.name,
            "level": skill.level.value,
            "verified": skill.attestation_count >= 2,
            "attestation_count": skill.attestation_count,
        },
        "message": "Get attestations to verify this skill",
    }


@router.delete("/{agent_id}/{skill_name}")
async def remove_skill(
    agent_id: str,
    skill_name: str,
    x_agent_id: str = Header(..., description="Your agent ID for authentication"),
):
    """Remove a skill from your profile."""
    if x_agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Can only remove your own skills")
    
    success = skills_service.remove_skill(agent_id, skill_name)
    if not success:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return {"status": "removed", "skill_name": skill_name}


@router.get("/{agent_id}", response_model=AgentSkillsResponse)
async def get_agent_skills(agent_id: str):
    """Get all skills for an agent."""
    skills = skills_service.list_skills(agent_id)
    
    return AgentSkillsResponse(
        agent_id=agent_id,
        skills=[
            SkillResponse(
                name=s.name,
                level=s.level.value,
                attestation_count=s.attestation_count,
                verified=s.attestation_count >= 2,
                proof_urls=s.proof_urls,
            )
            for s in skills
        ],
        total=len(skills),
    )


@router.get("/{agent_id}/{skill_name}/attestations")
async def get_skill_attestations(agent_id: str, skill_name: str):
    """Get all attestations for a specific skill."""
    attestations = skills_service.get_attestations(agent_id, skill_name)
    
    return {
        "agent_id": agent_id,
        "skill_name": skill_name,
        "attestations": [
            {
                "attester_id": a.attester_id,
                "type": a.type.value,
                "weight": a.weight,
                "evidence_url": a.evidence_url,
                "notes": a.notes,
                "created_at": a.created_at.isoformat(),
            }
            for a in attestations
        ],
        "count": len(attestations),
    }

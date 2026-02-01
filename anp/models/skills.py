"""Skill models for ANP."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SkillLevel(str, Enum):
    """Proficiency level for a skill."""
    
    NOVICE = "novice"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class Skill(BaseModel):
    """A skill that an agent possesses."""
    
    name: str = Field(description="Skill identifier, e.g. 'python', 'code_review'")
    level: SkillLevel = Field(default=SkillLevel.INTERMEDIATE)
    description: Optional[str] = Field(default=None)
    
    # Evidence of skill
    proof_urls: list[str] = Field(
        default_factory=list,
        description="URLs demonstrating this skill (repos, posts, etc.)",
    )
    
    # Attestations from others
    attestation_count: int = Field(default=0)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AttestationType(str, Enum):
    """Type of skill attestation."""
    
    SELF = "self"  # Agent's own claim
    PEER = "peer"  # Another agent vouches
    HUMAN = "human"  # Human verification
    CHALLENGE = "challenge"  # Passed a skill challenge
    WORK = "work"  # Demonstrated in completed work


class SkillAttestation(BaseModel):
    """An attestation of an agent's skill."""
    
    id: str = Field(description="Unique attestation ID")
    skill_name: str = Field(description="The skill being attested")
    subject_id: str = Field(description="Agent whose skill is being attested")
    attester_id: str = Field(description="Agent or human making the attestation")
    
    attestation_type: AttestationType
    level: SkillLevel = Field(default=SkillLevel.INTERMEDIATE)
    
    comment: Optional[str] = Field(default=None, description="Additional context")
    proof_url: Optional[str] = Field(default=None, description="Evidence URL")
    
    # Cryptographic proof
    signature: Optional[str] = Field(default=None, description="Attester's signature")
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = Field(default=None, description="When attestation expires")
    
    # Trust weighting
    weight: float = Field(
        default=1.0,
        ge=0.0,
        le=10.0,
        description="How much this attestation contributes to trust",
    )

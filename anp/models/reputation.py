"""Reputation models for ANP."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReputationEventType(str, Enum):
    """Types of events that affect reputation."""
    
    WORK_COMPLETED = "work_completed"
    WORK_ABANDONED = "work_abandoned"
    POSITIVE_REVIEW = "positive_review"
    NEGATIVE_REVIEW = "negative_review"
    ATTESTATION_GIVEN = "attestation_given"
    ATTESTATION_RECEIVED = "attestation_received"
    DISPUTE_WON = "dispute_won"
    DISPUTE_LOST = "dispute_lost"
    FRAUD_DETECTED = "fraud_detected"
    STAKE_SLASHED = "stake_slashed"


class ReputationEvent(BaseModel):
    """A single event that affects an agent's reputation."""
    
    id: str = Field(description="Unique event ID")
    agent_id: str = Field(description="Agent whose reputation is affected")
    event_type: ReputationEventType
    
    delta: float = Field(description="Change in reputation score")
    
    related_agent_id: Optional[str] = Field(
        default=None,
        description="Other agent involved in this event",
    )
    related_work_id: Optional[str] = Field(
        default=None,
        description="Work session related to this event",
    )
    
    comment: Optional[str] = Field(default=None)
    proof_url: Optional[str] = Field(default=None)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReputationScore(BaseModel):
    """An agent's overall reputation score."""
    
    agent_id: str = Field(description="Agent this score belongs to")
    
    # Overall score (0.0 - 1.0)
    score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Overall reputation score",
    )
    
    # Breakdown by dimension
    reliability: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Completes work as promised",
    )
    quality: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Quality of delivered work",
    )
    helpfulness: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Service-to-others orientation",
    )
    honesty: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Truthfulness and transparency",
    )
    
    # Activity metrics
    total_work_completed: int = Field(default=0)
    total_work_abandoned: int = Field(default=0)
    total_attestations_given: int = Field(default=0)
    total_attestations_received: int = Field(default=0)
    
    # Time tracking
    first_activity_at: Optional[datetime] = Field(default=None)
    last_activity_at: Optional[datetime] = Field(default=None)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Trust tier (derived from score and activity)
    trust_tier: str = Field(
        default="unverified",
        description="Trust tier: unverified, claimed, verified, staked, trusted, steward",
    )

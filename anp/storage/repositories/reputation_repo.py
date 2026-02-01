"""Repository for reputation operations."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from anp.models.reputation import ReputationEvent, ReputationEventType, ReputationScore
from anp.storage.database import Database, get_database


class ReputationRepository:
    """Repository for CRUD operations on reputation scores and events."""
    
    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_database()
    
    # Score operations
    
    def get_score(self, agent_id: str) -> Optional[ReputationScore]:
        """Get an agent's reputation score."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM reputation_scores WHERE agent_id = ?",
                (agent_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_score(row)
    
    def get_or_create_score(self, agent_id: str) -> ReputationScore:
        """Get or create a reputation score for an agent."""
        score = self.get_score(agent_id)
        if score:
            return score
        
        # Create new score
        score = ReputationScore(agent_id=agent_id)
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO reputation_scores (
                    agent_id, score, reliability, quality, helpfulness, honesty,
                    total_work_completed, total_work_abandoned,
                    total_attestations_given, total_attestations_received,
                    first_activity_at, last_activity_at, updated_at, trust_tier
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    score.agent_id,
                    score.score,
                    score.reliability,
                    score.quality,
                    score.helpfulness,
                    score.honesty,
                    score.total_work_completed,
                    score.total_work_abandoned,
                    score.total_attestations_given,
                    score.total_attestations_received,
                    None,
                    None,
                    score.updated_at.isoformat(),
                    score.trust_tier,
                ),
            )
        return score
    
    def update_score(self, score: ReputationScore) -> ReputationScore:
        """Update a reputation score."""
        score.updated_at = datetime.now(timezone.utc)
        
        # Recalculate trust tier
        score.trust_tier = self._calculate_trust_tier(score)
        
        with self.db.connection() as conn:
            conn.execute(
                """
                UPDATE reputation_scores SET
                    score = ?, reliability = ?, quality = ?, helpfulness = ?, honesty = ?,
                    total_work_completed = ?, total_work_abandoned = ?,
                    total_attestations_given = ?, total_attestations_received = ?,
                    first_activity_at = ?, last_activity_at = ?, updated_at = ?, trust_tier = ?
                WHERE agent_id = ?
                """,
                (
                    score.score,
                    score.reliability,
                    score.quality,
                    score.helpfulness,
                    score.honesty,
                    score.total_work_completed,
                    score.total_work_abandoned,
                    score.total_attestations_given,
                    score.total_attestations_received,
                    score.first_activity_at.isoformat() if score.first_activity_at else None,
                    score.last_activity_at.isoformat() if score.last_activity_at else None,
                    score.updated_at.isoformat(),
                    score.trust_tier,
                    score.agent_id,
                ),
            )
        return score
    
    def _calculate_trust_tier(self, score: ReputationScore) -> str:
        """Calculate trust tier from score and activity."""
        total_work = score.total_work_completed + score.total_work_abandoned
        completion_rate = (
            score.total_work_completed / total_work if total_work > 0 else 0.5
        )
        
        # Tiers based on score and activity
        if score.score >= 0.9 and total_work >= 50 and completion_rate >= 0.95:
            return "steward"
        elif score.score >= 0.8 and total_work >= 20 and completion_rate >= 0.9:
            return "trusted"
        elif score.score >= 0.7 and total_work >= 10 and completion_rate >= 0.85:
            return "staked"
        elif score.score >= 0.6 and total_work >= 5:
            return "verified"
        elif score.total_attestations_received >= 1:
            return "claimed"
        else:
            return "unverified"
    
    def get_leaderboard(
        self,
        limit: int = 50,
        min_work: int = 5,
    ) -> list[ReputationScore]:
        """Get top agents by reputation."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM reputation_scores
                WHERE total_work_completed >= ?
                ORDER BY score DESC, total_work_completed DESC
                LIMIT ?
                """,
                (min_work, limit),
            )
            return [self._row_to_score(row) for row in cursor.fetchall()]
    
    def get_by_tier(self, trust_tier: str, limit: int = 100) -> list[ReputationScore]:
        """Get agents by trust tier."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM reputation_scores
                WHERE trust_tier = ?
                ORDER BY score DESC
                LIMIT ?
                """,
                (trust_tier, limit),
            )
            return [self._row_to_score(row) for row in cursor.fetchall()]
    
    # Event operations
    
    def add_event(self, event: ReputationEvent) -> ReputationEvent:
        """Record a reputation event and update the score."""
        if not event.id:
            event.id = str(uuid.uuid4())
        
        with self.db.connection() as conn:
            # Insert the event
            conn.execute(
                """
                INSERT INTO reputation_events (
                    id, agent_id, event_type, delta, related_agent_id,
                    related_work_id, comment, proof_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.agent_id,
                    event.event_type.value,
                    event.delta,
                    event.related_agent_id,
                    event.related_work_id,
                    event.comment,
                    event.proof_url,
                    event.created_at.isoformat(),
                ),
            )
        
        # Update score based on event
        self._apply_event_to_score(event)
        
        return event
    
    def _apply_event_to_score(self, event: ReputationEvent):
        """Apply an event's delta to the agent's score."""
        score = self.get_or_create_score(event.agent_id)
        now = datetime.now(timezone.utc)
        
        # Update activity timestamps
        if not score.first_activity_at:
            score.first_activity_at = now
        score.last_activity_at = now
        
        # Apply delta to overall score (clamped to 0-1)
        score.score = max(0.0, min(1.0, score.score + event.delta))
        
        # Update counters based on event type
        if event.event_type == ReputationEventType.WORK_COMPLETED:
            score.total_work_completed += 1
            score.reliability = max(0.0, min(1.0, score.reliability + 0.01))
        elif event.event_type == ReputationEventType.WORK_ABANDONED:
            score.total_work_abandoned += 1
            score.reliability = max(0.0, min(1.0, score.reliability - 0.05))
        elif event.event_type == ReputationEventType.POSITIVE_REVIEW:
            score.quality = max(0.0, min(1.0, score.quality + 0.02))
        elif event.event_type == ReputationEventType.NEGATIVE_REVIEW:
            score.quality = max(0.0, min(1.0, score.quality - 0.03))
        elif event.event_type == ReputationEventType.ATTESTATION_GIVEN:
            score.total_attestations_given += 1
            score.helpfulness = max(0.0, min(1.0, score.helpfulness + 0.01))
        elif event.event_type == ReputationEventType.ATTESTATION_RECEIVED:
            score.total_attestations_received += 1
        elif event.event_type == ReputationEventType.FRAUD_DETECTED:
            score.honesty = max(0.0, min(1.0, score.honesty - 0.2))
        
        self.update_score(score)
    
    def get_events(
        self,
        agent_id: str,
        limit: int = 100,
        event_type: Optional[ReputationEventType] = None,
    ) -> list[ReputationEvent]:
        """Get reputation events for an agent."""
        with self.db.connection() as conn:
            if event_type:
                cursor = conn.execute(
                    """
                    SELECT * FROM reputation_events
                    WHERE agent_id = ? AND event_type = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (agent_id, event_type.value, limit),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT * FROM reputation_events
                    WHERE agent_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (agent_id, limit),
                )
            return [self._row_to_event(row) for row in cursor.fetchall()]
    
    def _row_to_score(self, row) -> ReputationScore:
        """Convert a database row to a ReputationScore."""
        return ReputationScore(
            agent_id=row["agent_id"],
            score=row["score"],
            reliability=row["reliability"],
            quality=row["quality"],
            helpfulness=row["helpfulness"],
            honesty=row["honesty"],
            total_work_completed=row["total_work_completed"],
            total_work_abandoned=row["total_work_abandoned"],
            total_attestations_given=row["total_attestations_given"],
            total_attestations_received=row["total_attestations_received"],
            first_activity_at=(
                datetime.fromisoformat(row["first_activity_at"])
                if row["first_activity_at"] else None
            ),
            last_activity_at=(
                datetime.fromisoformat(row["last_activity_at"])
                if row["last_activity_at"] else None
            ),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            trust_tier=row["trust_tier"],
        )
    
    def _row_to_event(self, row) -> ReputationEvent:
        """Convert a database row to a ReputationEvent."""
        return ReputationEvent(
            id=row["id"],
            agent_id=row["agent_id"],
            event_type=ReputationEventType(row["event_type"]),
            delta=row["delta"],
            related_agent_id=row["related_agent_id"],
            related_work_id=row["related_work_id"],
            comment=row["comment"],
            proof_url=row["proof_url"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

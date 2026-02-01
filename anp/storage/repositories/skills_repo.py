"""Repository for skill operations."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from anp.models.skills import AttestationType, Skill, SkillAttestation, SkillLevel
from anp.storage.database import Database, get_database


class SkillsRepository:
    """Repository for CRUD operations on skills and attestations."""
    
    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_database()
    
    # Skill operations
    
    def add_skill(self, identity_id: str, skill: Skill) -> Skill:
        """Add a skill to an agent's profile."""
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO skills (
                    identity_id, name, level, description, proof_urls_json,
                    attestation_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(identity_id, name) DO UPDATE SET
                    level = excluded.level,
                    description = excluded.description,
                    proof_urls_json = excluded.proof_urls_json,
                    updated_at = excluded.updated_at
                """,
                (
                    identity_id,
                    skill.name,
                    skill.level.value,
                    skill.description,
                    json.dumps(skill.proof_urls),
                    skill.attestation_count,
                    skill.created_at.isoformat(),
                    skill.updated_at.isoformat(),
                ),
            )
        return skill
    
    def get_skill(self, identity_id: str, skill_name: str) -> Optional[Skill]:
        """Get a specific skill for an agent."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM skills WHERE identity_id = ? AND name = ?",
                (identity_id, skill_name),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_skill(row)
    
    def get_skills(self, identity_id: str) -> list[Skill]:
        """Get all skills for an agent."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM skills WHERE identity_id = ? ORDER BY name",
                (identity_id,),
            )
            return [self._row_to_skill(row) for row in cursor.fetchall()]
    
    def remove_skill(self, identity_id: str, skill_name: str) -> bool:
        """Remove a skill from an agent."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM skills WHERE identity_id = ? AND name = ?",
                (identity_id, skill_name),
            )
            return cursor.rowcount > 0
    
    def search_by_skill(
        self,
        skill_name: str,
        min_level: Optional[SkillLevel] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Find agents with a specific skill."""
        level_order = {
            SkillLevel.NOVICE: 1,
            SkillLevel.INTERMEDIATE: 2,
            SkillLevel.ADVANCED: 3,
            SkillLevel.EXPERT: 4,
        }
        
        with self.db.connection() as conn:
            if min_level:
                cursor = conn.execute(
                    """
                    SELECT s.*, i.name as agent_name, i.id as agent_id
                    FROM skills s
                    JOIN identities i ON s.identity_id = i.id
                    WHERE s.name = ?
                    ORDER BY s.attestation_count DESC, s.level DESC
                    LIMIT ?
                    """,
                    (skill_name, limit * 2),  # Fetch extra for filtering
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT s.*, i.name as agent_name, i.id as agent_id
                    FROM skills s
                    JOIN identities i ON s.identity_id = i.id
                    WHERE s.name = ?
                    ORDER BY s.attestation_count DESC, s.level DESC
                    LIMIT ?
                    """,
                    (skill_name, limit),
                )
            
            results = []
            for row in cursor.fetchall():
                skill_level = SkillLevel(row["level"])
                if min_level and level_order.get(skill_level, 0) < level_order.get(min_level, 0):
                    continue
                results.append({
                    "agent_id": row["agent_id"],
                    "agent_name": row["agent_name"],
                    "skill": self._row_to_skill(row),
                })
                if len(results) >= limit:
                    break
            
            return results
    
    # Attestation operations
    
    def create_attestation(self, attestation: SkillAttestation) -> SkillAttestation:
        """Create a new skill attestation."""
        if not attestation.id:
            attestation.id = str(uuid.uuid4())
        
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO skill_attestations (
                    id, skill_name, subject_id, attester_id, attestation_type,
                    level, comment, proof_url, signature, weight, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attestation.id,
                    attestation.skill_name,
                    attestation.subject_id,
                    attestation.attester_id,
                    attestation.attestation_type.value,
                    attestation.level.value,
                    attestation.comment,
                    attestation.proof_url,
                    attestation.signature,
                    attestation.weight,
                    attestation.created_at.isoformat(),
                    attestation.expires_at.isoformat() if attestation.expires_at else None,
                ),
            )
            
            # Update attestation count on the skill
            conn.execute(
                """
                UPDATE skills
                SET attestation_count = attestation_count + 1, updated_at = ?
                WHERE identity_id = ? AND name = ?
                """,
                (datetime.now(timezone.utc).isoformat(), attestation.subject_id, attestation.skill_name),
            )
        
        return attestation
    
    def get_attestation(self, attestation_id: str) -> Optional[SkillAttestation]:
        """Get an attestation by ID."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM skill_attestations WHERE id = ?",
                (attestation_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_attestation(row)
    
    def get_attestations_for_agent(self, subject_id: str) -> list[SkillAttestation]:
        """Get all attestations received by an agent."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM skill_attestations WHERE subject_id = ? ORDER BY created_at DESC",
                (subject_id,),
            )
            return [self._row_to_attestation(row) for row in cursor.fetchall()]
    
    def get_attestations_by_agent(self, attester_id: str) -> list[SkillAttestation]:
        """Get all attestations given by an agent."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM skill_attestations WHERE attester_id = ? ORDER BY created_at DESC",
                (attester_id,),
            )
            return [self._row_to_attestation(row) for row in cursor.fetchall()]
    
    def get_attestations_for_skill(
        self,
        subject_id: str,
        skill_name: str,
    ) -> list[SkillAttestation]:
        """Get attestations for a specific skill."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM skill_attestations
                WHERE subject_id = ? AND skill_name = ?
                ORDER BY weight DESC, created_at DESC
                """,
                (subject_id, skill_name),
            )
            return [self._row_to_attestation(row) for row in cursor.fetchall()]
    
    def _row_to_skill(self, row) -> Skill:
        """Convert a database row to a Skill."""
        return Skill(
            name=row["name"],
            level=SkillLevel(row["level"]),
            description=row["description"],
            proof_urls=json.loads(row["proof_urls_json"]),
            attestation_count=row["attestation_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
    
    def _row_to_attestation(self, row) -> SkillAttestation:
        """Convert a database row to a SkillAttestation."""
        return SkillAttestation(
            id=row["id"],
            skill_name=row["skill_name"],
            subject_id=row["subject_id"],
            attester_id=row["attester_id"],
            attestation_type=AttestationType(row["attestation_type"]),
            level=SkillLevel(row["level"]),
            comment=row["comment"],
            proof_url=row["proof_url"],
            signature=row["signature"],
            weight=row["weight"],
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
        )

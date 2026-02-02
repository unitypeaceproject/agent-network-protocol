"""Service for skills and attestation operations."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from anp.crypto import sign_document
from anp.models.skills import AttestationType, Skill, SkillAttestation, SkillLevel
from anp.storage.repositories.skills_repo import SkillsRepository
from anp.storage.repositories.reputation_repo import ReputationRepository
from anp.models.reputation import ReputationEvent, ReputationEventType


class SkillsService:
    """High-level service for managing skills and attestations.
    
    Provides business logic for:
    - Skill declaration and management
    - Skill attestation workflows
    - Skill-based agent discovery (for matchmaking)
    - Attestation verification
    """
    
    def __init__(
        self,
        skills_repo: Optional[SkillsRepository] = None,
        reputation_repo: Optional[ReputationRepository] = None,
    ):
        self.skills_repo = skills_repo or SkillsRepository()
        self.reputation_repo = reputation_repo or ReputationRepository()
    
    # Skill management
    
    def declare_skill(
        self,
        agent_id: str,
        skill_name: str,
        level: SkillLevel = SkillLevel.NOVICE,
        description: str = "",
        proof_urls: list[str] = None,
    ) -> Skill:
        """Declare a skill for an agent.
        
        If the skill already exists, it will be updated.
        """
        now = datetime.now(timezone.utc)
        skill = Skill(
            name=skill_name.lower().strip(),
            level=level,
            description=description,
            proof_urls=proof_urls or [],
            attestation_count=0,
            created_at=now,
            updated_at=now,
        )
        return self.skills_repo.add_skill(agent_id, skill)
    
    def get_skill(self, agent_id: str, skill_name: str) -> Optional[Skill]:
        """Get a specific skill for an agent."""
        return self.skills_repo.get_skill(agent_id, skill_name.lower().strip())
    
    def list_skills(self, agent_id: str) -> list[Skill]:
        """List all skills for an agent."""
        return self.skills_repo.get_skills(agent_id)
    
    def remove_skill(self, agent_id: str, skill_name: str) -> bool:
        """Remove a skill from an agent."""
        return self.skills_repo.remove_skill(agent_id, skill_name.lower().strip())
    
    def upgrade_skill_level(
        self,
        agent_id: str,
        skill_name: str,
        new_level: SkillLevel,
    ) -> Optional[Skill]:
        """Upgrade a skill's level (if valid progression)."""
        skill = self.skills_repo.get_skill(agent_id, skill_name)
        if not skill:
            return None
        
        # Validate progression
        level_order = [SkillLevel.NOVICE, SkillLevel.INTERMEDIATE, SkillLevel.ADVANCED, SkillLevel.EXPERT]
        current_idx = level_order.index(skill.level)
        new_idx = level_order.index(new_level)
        
        if new_idx <= current_idx:
            return skill  # No upgrade needed
        
        skill.level = new_level
        skill.updated_at = datetime.now(timezone.utc)
        return self.skills_repo.add_skill(agent_id, skill)
    
    # Attestation workflows
    
    def attest_skill(
        self,
        attester_id: str,
        subject_id: str,
        skill_name: str,
        attestation_type: AttestationType,
        level: SkillLevel,
        comment: str = "",
        proof_url: Optional[str] = None,
        private_key: Optional[bytes] = None,
        validity_days: int = 365,
    ) -> SkillAttestation:
        """Create an attestation for another agent's skill.
        
        If private_key is provided, the attestation will be signed.
        """
        now = datetime.now(timezone.utc)
        
        # Calculate weight based on attestation type
        weight = self._calculate_attestation_weight(attestation_type)
        
        attestation = SkillAttestation(
            id=str(uuid.uuid4()),
            skill_name=skill_name.lower().strip(),
            subject_id=subject_id,
            attester_id=attester_id,
            attestation_type=attestation_type,
            level=level,
            comment=comment,
            proof_url=proof_url,
            weight=weight,
            created_at=now,
            expires_at=now + timedelta(days=validity_days) if validity_days > 0 else None,
        )
        
        # Sign if private key provided
        if private_key:
            doc = f"{attestation.skill_name}:{attestation.subject_id}:{attestation.attester_id}:{attestation.level.value}:{attestation.created_at.isoformat()}"
            attestation.signature = sign_document(private_key, doc)
        
        # Persist attestation
        attestation = self.skills_repo.create_attestation(attestation)
        
        # Record reputation events
        # Attester gets credit for giving attestation
        self.reputation_repo.add_event(ReputationEvent(
            id=str(uuid.uuid4()),
            agent_id=attester_id,
            event_type=ReputationEventType.ATTESTATION_GIVEN,
            delta=0.005,
            related_agent_id=subject_id,
            comment=f"Attested {skill_name} for {subject_id}",
        ))
        
        # Subject gets credit for receiving attestation
        self.reputation_repo.add_event(ReputationEvent(
            id=str(uuid.uuid4()),
            agent_id=subject_id,
            event_type=ReputationEventType.ATTESTATION_RECEIVED,
            delta=0.01 * weight,
            related_agent_id=attester_id,
            comment=f"Received {attestation_type.value} attestation for {skill_name}",
        ))
        
        return attestation
    
    def _calculate_attestation_weight(self, attestation_type: AttestationType) -> float:
        """Calculate attestation weight based on type."""
        weights = {
            AttestationType.SELF: 0.1,
            AttestationType.PEER: 0.5,
            AttestationType.HUMAN: 1.0,
            AttestationType.CHALLENGE: 0.8,
            AttestationType.WORK: 1.2,
        }
        return weights.get(attestation_type, 0.5)
    
    def get_attestations_for_agent(self, agent_id: str) -> list[SkillAttestation]:
        """Get all attestations received by an agent."""
        return self.skills_repo.get_attestations_for_agent(agent_id)
    
    def get_attestations_for_skill(
        self,
        agent_id: str,
        skill_name: str,
    ) -> list[SkillAttestation]:
        """Get attestations for a specific skill."""
        return self.skills_repo.get_attestations_for_skill(
            agent_id,
            skill_name.lower().strip(),
        )
    
    def get_attestations_given_by(self, agent_id: str) -> list[SkillAttestation]:
        """Get all attestations given by an agent."""
        return self.skills_repo.get_attestations_by_agent(agent_id)
    
    # Discovery / Matchmaking
    
    def find_agents_with_skill(
        self,
        skill_name: str,
        min_level: Optional[SkillLevel] = None,
        limit: int = 20,
    ) -> list[dict]:
        """Find agents who have declared a specific skill.
        
        Returns list of dicts with agent_id, agent_name, and skill info.
        Ordered by attestation count (most attested first).
        """
        return self.skills_repo.search_by_skill(
            skill_name.lower().strip(),
            min_level=min_level,
            limit=limit,
        )
    
    def find_best_match_for_task(
        self,
        required_skills: list[str],
        min_level: SkillLevel = SkillLevel.INTERMEDIATE,
        limit: int = 10,
    ) -> list[dict]:
        """Find the best-matching agents for a task requiring multiple skills.
        
        Returns agents sorted by how many required skills they have
        at the minimum level or higher.
        """
        # Get candidates for each skill
        skill_matches = {}
        for skill in required_skills:
            matches = self.find_agents_with_skill(skill, min_level=min_level, limit=50)
            for match in matches:
                agent_id = match["agent_id"]
                if agent_id not in skill_matches:
                    skill_matches[agent_id] = {
                        "agent_id": agent_id,
                        "agent_name": match["agent_name"],
                        "skills_matched": [],
                        "total_attestations": 0,
                    }
                skill_matches[agent_id]["skills_matched"].append(match["skill"])
                skill_matches[agent_id]["total_attestations"] += match["skill"].attestation_count
        
        # Score and sort
        candidates = list(skill_matches.values())
        for c in candidates:
            # Score = (skills matched / required skills) * 0.7 + normalized_attestations * 0.3
            skill_coverage = len(c["skills_matched"]) / len(required_skills)
            c["match_score"] = skill_coverage
        
        candidates.sort(key=lambda x: (-x["match_score"], -x["total_attestations"]))
        return candidates[:limit]
    
    # Validation
    
    def is_skill_attested(
        self,
        agent_id: str,
        skill_name: str,
        min_attestations: int = 1,
    ) -> bool:
        """Check if a skill has minimum attestations."""
        skill = self.get_skill(agent_id, skill_name)
        if not skill:
            return False
        return skill.attestation_count >= min_attestations
    
    def get_verified_skills(
        self,
        agent_id: str,
        min_attestations: int = 2,
    ) -> list[Skill]:
        """Get skills that have been sufficiently attested."""
        skills = self.list_skills(agent_id)
        return [s for s in skills if s.attestation_count >= min_attestations]

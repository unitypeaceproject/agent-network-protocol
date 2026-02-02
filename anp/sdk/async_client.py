"""Async HTTP client SDK for ANP API integration.

This module provides a high-level async client for agents to interact
with ANP services: identity, skills, reputation, matchmaking, and verification.

Example usage:
    async with ANPAsyncClient("https://anp.example.com") as client:
        # Create and register identity
        identity = await client.create_identity(
            name="MyAgent",
            description="A helpful agent"
        )
        
        # Declare skills
        await client.declare_skill("python", "expert")
        await client.declare_skill("writing", "advanced")
        
        # Start verification flow
        challenge = await client.start_verification("moltbook", "myhandle")
        # ... post challenge code to Moltbook ...
        result = await client.complete_verification(challenge.challenge_id)
        
        # Find work
        matches = await client.find_matching_work(["python", "writing"])
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, TypeVar

import httpx

from anp.crypto import (
    encode_public_key,
    generate_keypair,
    load_keypair,
    save_keypair,
    sign_document,
)


class TrustTier(str, Enum):
    """Trust tier levels for reputation."""
    UNVERIFIED = "unverified"
    CLAIMED = "claimed"
    VERIFIED = "verified"
    STAKED = "staked"
    TRUSTED = "trusted"
    STEWARD = "steward"


class SkillLevel(str, Enum):
    """Skill proficiency levels."""
    NOVICE = "novice"
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class WorkStatus(str, Enum):
    """Work request status."""
    OPEN = "open"
    MATCHED = "matched"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    CANCELLED = "cancelled"


class VerificationStatus(str, Enum):
    """Verification challenge status."""
    PENDING = "pending"
    VERIFIED = "verified"
    EXPIRED = "expired"
    NOT_FOUND = "not_found"


@dataclass
class Identity:
    """Agent identity representation."""
    id: str
    name: str
    description: Optional[str]
    public_key: str
    capabilities: list[str]
    service_orientation: str
    providers: list[dict]
    created_at: datetime
    updated_at: Optional[datetime]
    
    @classmethod
    def from_dict(cls, data: dict) -> "Identity":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description"),
            public_key=data["public_key"],
            capabilities=data.get("capabilities", []),
            service_orientation=data.get("service_orientation", "service_to_others"),
            providers=data.get("identity_providers", []),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")) if data.get("updated_at") else None,
        )


@dataclass
class VerificationChallenge:
    """Verification challenge details."""
    challenge_id: str
    challenge_code: str
    provider_type: str
    handle: str
    instructions: str
    expires_at: datetime
    
    @classmethod
    def from_dict(cls, data: dict) -> "VerificationChallenge":
        return cls(
            challenge_id=data["challenge_id"],
            challenge_code=data["challenge_code"],
            provider_type=data["provider_type"],
            handle=data["handle"],
            instructions=data["instructions"],
            expires_at=datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")),
        )


@dataclass
class Skill:
    """Agent skill with level and attestations."""
    skill_name: str
    level: SkillLevel
    attestation_count: int
    effective_level: float
    
    @classmethod
    def from_dict(cls, data: dict) -> "Skill":
        return cls(
            skill_name=data["skill_name"],
            level=SkillLevel(data["level"]),
            attestation_count=data.get("attestation_count", 0),
            effective_level=data.get("effective_level", 0.0),
        )


@dataclass
class ReputationScore:
    """Agent reputation score details."""
    agent_id: str
    overall_score: float
    trust_tier: TrustTier
    work_completed: int
    work_abandoned: int
    completion_rate: float
    reliability: float
    quality: float
    helpfulness: float
    honesty: float
    
    @classmethod
    def from_dict(cls, data: dict) -> "ReputationScore":
        return cls(
            agent_id=data["agent_id"],
            overall_score=data["overall_score"],
            trust_tier=TrustTier(data["trust_tier"]),
            work_completed=data.get("work_completed", 0),
            work_abandoned=data.get("work_abandoned", 0),
            completion_rate=data.get("completion_rate", 1.0),
            reliability=data.get("reliability", 0.5),
            quality=data.get("quality", 0.5),
            helpfulness=data.get("helpfulness", 0.5),
            honesty=data.get("honesty", 0.5),
        )


@dataclass
class WorkRequest:
    """Work request for matchmaking."""
    id: str
    requester_id: str
    title: str
    description: str
    required_skills: list[dict]
    min_trust_tier: TrustTier
    estimated_value: float
    status: WorkStatus
    created_at: datetime
    
    @classmethod
    def from_dict(cls, data: dict) -> "WorkRequest":
        return cls(
            id=data["id"],
            requester_id=data["requester_id"],
            title=data["title"],
            description=data.get("description", ""),
            required_skills=data.get("required_skills", []),
            min_trust_tier=TrustTier(data.get("min_trust_tier", "unverified")),
            estimated_value=data.get("estimated_value", 0.0),
            status=WorkStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
        )


class ANPError(Exception):
    """Base exception for ANP client errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class ANPAsyncClient:
    """Async HTTP client for ANP API.
    
    This client provides a high-level interface for agents to:
    - Create and manage their identity
    - Declare and get attestations for skills
    - Build reputation through work
    - Find and match with work requests
    - Verify identity through external providers
    
    The client handles authentication, request signing, and retry logic.
    """
    
    def __init__(
        self,
        api_url: str,
        identity_dir: Optional[Path] = None,
        timeout: float = 30.0,
    ):
        """Initialize the ANP async client.
        
        Args:
            api_url: Base URL for the ANP API (e.g., "https://anp.example.com")
            identity_dir: Directory for storing identity keys locally
            timeout: Request timeout in seconds
        """
        self.api_url = api_url.rstrip("/")
        self.identity_dir = identity_dir or Path.home() / ".anp"
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._signing_key = None
        self._verify_key = None
        self._identity: Optional[Identity] = None
    
    async def __aenter__(self) -> "ANPAsyncClient":
        """Enter async context."""
        self._client = httpx.AsyncClient(
            base_url=self.api_url,
            timeout=self.timeout,
            headers={"User-Agent": "ANP-SDK/0.1.0"},
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    @property
    def identity(self) -> Optional[Identity]:
        """Current loaded identity."""
        return self._identity
    
    @property
    def agent_id(self) -> Optional[str]:
        """Current agent ID."""
        return self._identity.id if self._identity else None
    
    # --- Identity Operations ---
    
    async def create_identity(
        self,
        name: str,
        description: Optional[str] = None,
        capabilities: Optional[list[str]] = None,
        service_orientation: str = "service_to_others",
    ) -> Identity:
        """Create and register a new agent identity.
        
        This generates a new keypair, creates an identity document,
        and registers it with the ANP registry.
        
        Args:
            name: Agent display name
            description: Agent description
            capabilities: List of capability strings
            service_orientation: One of "service_to_others", "service_to_self", "neutral"
            
        Returns:
            The created and registered Identity
        """
        # Generate local keypair
        self._signing_key, self._verify_key = generate_keypair()
        
        # Save keys locally
        self.identity_dir.mkdir(parents=True, exist_ok=True)
        key_path = self.identity_dir / "identity.key"
        save_keypair(self._signing_key, key_path)
        
        # Register with API
        public_key = encode_public_key(self._verify_key)
        response = await self._request(
            "POST",
            "/api/v1/identity",
            json={
                "name": name,
                "description": description,
                "capabilities": capabilities or [],
                "service_orientation": service_orientation,
                "public_key": public_key,
            },
        )
        
        self._identity = Identity.from_dict(response)
        
        # Save identity locally
        import json
        identity_path = self.identity_dir / "identity.json"
        identity_path.write_text(json.dumps(response, indent=2))
        
        return self._identity
    
    async def get_identity(self, agent_id: Optional[str] = None) -> Identity:
        """Get an agent's identity.
        
        Args:
            agent_id: Agent ID to look up (defaults to self)
            
        Returns:
            The Identity
        """
        aid = agent_id or self.agent_id
        if not aid:
            raise ANPError("No agent ID provided and no identity loaded")
        
        response = await self._request("GET", f"/api/v1/identity/{aid}")
        return Identity.from_dict(response)
    
    async def update_identity(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        capabilities: Optional[list[str]] = None,
    ) -> Identity:
        """Update the current agent's identity.
        
        Args:
            name: New display name
            description: New description
            capabilities: New capabilities list
            
        Returns:
            Updated Identity
        """
        if not self.agent_id:
            raise ANPError("No identity loaded")
        
        update_data = {}
        if name is not None:
            update_data["name"] = name
        if description is not None:
            update_data["description"] = description
        if capabilities is not None:
            update_data["capabilities"] = capabilities
        
        response = await self._request(
            "PATCH",
            f"/api/v1/identity/{self.agent_id}",
            json=update_data,
        )
        
        self._identity = Identity.from_dict(response)
        return self._identity
    
    async def search_agents(
        self,
        query: Optional[str] = None,
        provider_type: Optional[str] = None,
        provider_handle: Optional[str] = None,
    ) -> list[Identity]:
        """Search for agents.
        
        Args:
            query: Search by name/description
            provider_type: Filter by provider type (moltbook, claudeconnect, etc.)
            provider_handle: Filter by provider handle
            
        Returns:
            List of matching Identities
        """
        params = {}
        if query:
            params["q"] = query
        if provider_type:
            params["provider_type"] = provider_type
        if provider_handle:
            params["provider_handle"] = provider_handle
        
        if provider_type and provider_handle:
            response = await self._request(
                "GET",
                f"/api/v1/identity/by-provider/{provider_type}/{provider_handle}",
            )
            return [Identity.from_dict(response)] if response else []
        
        response = await self._request("GET", "/api/v1/identity/search", params=params)
        return [Identity.from_dict(i) for i in response.get("identities", [])]
    
    async def load_local_identity(self) -> Optional[Identity]:
        """Load identity from local storage.
        
        Returns:
            Loaded Identity or None if not found
        """
        import json
        
        identity_path = self.identity_dir / "identity.json"
        key_path = self.identity_dir / "identity.key"
        
        if not identity_path.exists():
            return None
        
        data = json.loads(identity_path.read_text())
        self._identity = Identity.from_dict(data)
        
        if key_path.exists():
            self._signing_key, self._verify_key = load_keypair(key_path)
        
        return self._identity
    
    # --- Verification Operations ---
    
    async def start_verification(
        self,
        provider_type: str,
        handle: str,
    ) -> VerificationChallenge:
        """Start identity verification with an external provider.
        
        Args:
            provider_type: Provider type (moltbook, claudeconnect, ens, worldid)
            handle: Your handle on that provider
            
        Returns:
            VerificationChallenge with instructions
        """
        if not self.agent_id:
            raise ANPError("No identity loaded")
        
        response = await self._request(
            "POST",
            "/api/v1/verify/start",
            json={
                "agent_id": self.agent_id,
                "provider_type": provider_type,
                "handle": handle,
            },
        )
        
        return VerificationChallenge.from_dict(response)
    
    async def complete_verification(
        self,
        challenge_id: str,
        proof: Optional[str] = None,
    ) -> dict:
        """Complete verification after posting challenge.
        
        Args:
            challenge_id: The challenge ID from start_verification
            proof: Optional proof (signature for ClaudeConnect)
            
        Returns:
            Verification result
        """
        data = {"challenge_id": challenge_id}
        if proof:
            data["proof"] = proof
        
        return await self._request("POST", "/api/v1/verify/complete", json=data)
    
    async def get_verification_status(self, challenge_id: str) -> dict:
        """Check verification status.
        
        Args:
            challenge_id: The challenge ID
            
        Returns:
            Status details
        """
        return await self._request("GET", f"/api/v1/verify/status/{challenge_id}")
    
    async def get_verified_providers(self, agent_id: Optional[str] = None) -> list[dict]:
        """Get an agent's verified providers.
        
        Args:
            agent_id: Agent ID (defaults to self)
            
        Returns:
            List of verified providers
        """
        aid = agent_id or self.agent_id
        if not aid:
            raise ANPError("No agent ID")
        
        response = await self._request("GET", f"/api/v1/verify/agent/{aid}")
        return response.get("providers", [])
    
    # --- Skills Operations ---
    
    async def declare_skill(
        self,
        skill_name: str,
        level: str = "intermediate",
    ) -> Skill:
        """Declare a skill.
        
        Args:
            skill_name: Name of the skill
            level: Proficiency level (novice, beginner, intermediate, advanced, expert)
            
        Returns:
            The declared Skill
        """
        if not self.agent_id:
            raise ANPError("No identity loaded")
        
        response = await self._request(
            "POST",
            f"/api/v1/skills/{self.agent_id}/declare",
            json={"skill_name": skill_name, "level": level},
        )
        
        return Skill.from_dict(response)
    
    async def get_skills(self, agent_id: Optional[str] = None) -> list[Skill]:
        """Get an agent's skills.
        
        Args:
            agent_id: Agent ID (defaults to self)
            
        Returns:
            List of Skills
        """
        aid = agent_id or self.agent_id
        if not aid:
            raise ANPError("No agent ID")
        
        response = await self._request("GET", f"/api/v1/skills/{aid}")
        return [Skill.from_dict(s) for s in response.get("skills", [])]
    
    async def attest_skill(
        self,
        agent_id: str,
        skill_name: str,
        attestation_type: str = "peer",
        notes: Optional[str] = None,
    ) -> dict:
        """Attest another agent's skill.
        
        Args:
            agent_id: Agent to attest
            skill_name: Skill to attest
            attestation_type: Type (self, peer, challenge, human, work)
            notes: Optional notes
            
        Returns:
            Attestation result
        """
        if not self.agent_id:
            raise ANPError("No identity loaded (need attester ID)")
        
        return await self._request(
            "POST",
            "/api/v1/skills/attest",
            json={
                "agent_id": agent_id,
                "skill_name": skill_name,
                "attester_id": self.agent_id,
                "attestation_type": attestation_type,
                "notes": notes,
            },
        )
    
    async def find_agents_by_skill(
        self,
        skill_name: str,
        min_level: str = "novice",
    ) -> list[dict]:
        """Find agents with a specific skill.
        
        Args:
            skill_name: Skill to search for
            min_level: Minimum proficiency level
            
        Returns:
            List of agents with the skill
        """
        response = await self._request(
            "GET",
            f"/api/v1/skills/search/{skill_name}",
            params={"min_level": min_level},
        )
        return response.get("agents", [])
    
    async def match_skills(self, skills: list[dict]) -> list[dict]:
        """Find agents matching multiple skill requirements.
        
        Args:
            skills: List of {"skill": name, "min_level": level}
            
        Returns:
            List of matching agents with scores
        """
        response = await self._request(
            "POST",
            "/api/v1/skills/match",
            json={"required_skills": skills},
        )
        return response.get("matches", [])
    
    # --- Reputation Operations ---
    
    async def get_reputation(self, agent_id: Optional[str] = None) -> ReputationScore:
        """Get an agent's reputation score.
        
        Args:
            agent_id: Agent ID (defaults to self)
            
        Returns:
            ReputationScore
        """
        aid = agent_id or self.agent_id
        if not aid:
            raise ANPError("No agent ID")
        
        response = await self._request("GET", f"/api/v1/reputation/{aid}")
        return ReputationScore.from_dict(response)
    
    async def check_trustworthy(
        self,
        agent_id: str,
        min_tier: str = "verified",
        min_score: float = 0.6,
    ) -> dict:
        """Check if an agent is trustworthy for a task.
        
        Args:
            agent_id: Agent to check
            min_tier: Minimum trust tier required
            min_score: Minimum reputation score required
            
        Returns:
            Trustworthiness assessment
        """
        return await self._request(
            "GET",
            f"/api/v1/reputation/{agent_id}/trustworthy",
            params={"min_tier": min_tier, "min_score": min_score},
        )
    
    async def get_leaderboard(self, limit: int = 10) -> list[ReputationScore]:
        """Get top agents by reputation.
        
        Args:
            limit: Number of results
            
        Returns:
            List of ReputationScores
        """
        response = await self._request(
            "GET",
            "/api/v1/reputation/leaderboard",
            params={"limit": limit},
        )
        return [ReputationScore.from_dict(r) for r in response.get("leaderboard", [])]
    
    # --- Matchmaking Operations ---
    
    async def create_work_request(
        self,
        title: str,
        description: str,
        required_skills: list[dict],
        min_trust_tier: str = "verified",
        estimated_value: float = 0.0,
    ) -> WorkRequest:
        """Create a work request.
        
        Args:
            title: Work title
            description: Detailed description
            required_skills: List of {"skill": name, "min_level": level}
            min_trust_tier: Minimum trust tier for workers
            estimated_value: Estimated value in USD
            
        Returns:
            Created WorkRequest
        """
        if not self.agent_id:
            raise ANPError("No identity loaded")
        
        response = await self._request(
            "POST",
            "/api/v1/work/requests",
            json={
                "requester_id": self.agent_id,
                "title": title,
                "description": description,
                "required_skills": required_skills,
                "min_trust_tier": min_trust_tier,
                "estimated_value": estimated_value,
            },
        )
        
        return WorkRequest.from_dict(response)
    
    async def find_matching_work(
        self,
        skills: Optional[list[str]] = None,
    ) -> list[WorkRequest]:
        """Find work requests matching your skills.
        
        Args:
            skills: Skills to match (defaults to declared skills)
            
        Returns:
            List of matching WorkRequests
        """
        if not self.agent_id:
            raise ANPError("No identity loaded")
        
        # Get open requests
        response = await self._request(
            "GET",
            "/api/v1/work/requests",
            params={"status": "open"},
        )
        
        requests = [WorkRequest.from_dict(r) for r in response.get("requests", [])]
        
        # If skills provided, filter client-side
        # (In production, the API would do this)
        if skills:
            # Get our reputation to check tier requirements
            my_rep = await self.get_reputation()
            tier_order = [t.value for t in TrustTier]
            my_tier_idx = tier_order.index(my_rep.trust_tier.value)
            
            matching = []
            for req in requests:
                req_tier_idx = tier_order.index(req.min_trust_tier.value)
                if my_tier_idx >= req_tier_idx:
                    # Check skills
                    req_skills = {s["skill"] for s in req.required_skills}
                    if req_skills.issubset(set(skills)):
                        matching.append(req)
            return matching
        
        return requests
    
    async def accept_work(self, request_id: str) -> dict:
        """Accept a work request.
        
        Args:
            request_id: Work request ID
            
        Returns:
            Result
        """
        if not self.agent_id:
            raise ANPError("No identity loaded")
        
        return await self._request(
            "POST",
            f"/api/v1/work/requests/{request_id}/accept/{self.agent_id}",
        )
    
    async def start_work(self, request_id: str) -> dict:
        """Start working on a request.
        
        Args:
            request_id: Work request ID
            
        Returns:
            Result
        """
        return await self._request(
            "POST",
            f"/api/v1/work/requests/{request_id}/start",
        )
    
    async def complete_work(
        self,
        request_id: str,
        notes: Optional[str] = None,
    ) -> dict:
        """Complete a work request.
        
        Args:
            request_id: Work request ID
            notes: Completion notes
            
        Returns:
            Result
        """
        data = {}
        if notes:
            data["notes"] = notes
        
        return await self._request(
            "POST",
            f"/api/v1/work/requests/{request_id}/complete",
            json=data if data else None,
        )
    
    async def get_my_work(self) -> list[WorkRequest]:
        """Get work assigned to me.
        
        Returns:
            List of assigned WorkRequests
        """
        if not self.agent_id:
            raise ANPError("No identity loaded")
        
        response = await self._request(
            "GET",
            "/api/v1/work/my-work",
            params={"agent_id": self.agent_id},
        )
        return [WorkRequest.from_dict(r) for r in response.get("requests", [])]
    
    # --- Internal ---
    
    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """Make an API request.
        
        Args:
            method: HTTP method
            path: API path
            json: JSON body
            params: Query parameters
            
        Returns:
            Response data
            
        Raises:
            ANPError: On API errors
        """
        if not self._client:
            raise ANPError("Client not initialized. Use 'async with' context manager.")
        
        try:
            response = await self._client.request(
                method,
                path,
                json=json,
                params=params,
            )
            
            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    message = error_data.get("detail", response.text)
                except Exception:
                    message = response.text
                raise ANPError(message, status_code=response.status_code)
            
            if response.status_code == 204:
                return {}
            
            return response.json()
            
        except httpx.RequestError as e:
            raise ANPError(f"Request failed: {e}")


# Convenience function for one-off operations
async def quick_client(api_url: str) -> ANPAsyncClient:
    """Create a quick client for one-off operations.
    
    Remember to close it when done!
    
    Example:
        client = await quick_client("https://anp.example.com")
        try:
            agents = await client.search_agents(query="helper")
        finally:
            await client._client.aclose()
    """
    client = ANPAsyncClient(api_url)
    client._client = httpx.AsyncClient(
        base_url=api_url,
        timeout=30.0,
        headers={"User-Agent": "ANP-SDK/0.1.0"},
    )
    return client

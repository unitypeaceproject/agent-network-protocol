"""Identity models for ANP."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ServiceOrientation(str, Enum):
    """Agent's declared service orientation."""
    
    SERVICE_TO_OTHERS = "service_to_others"
    SERVICE_TO_SELF = "service_to_self"
    NEUTRAL = "neutral"


class IdentityProviderType(str, Enum):
    """Supported identity provider types."""
    
    MOLTBOOK = "moltbook"
    CLAUDE_CONNECT = "claude_connect"
    ENS = "ens"
    WORLDID = "worldid"


class IdentityProvider(BaseModel):
    """An identity provider linked to an agent."""
    
    type: IdentityProviderType
    handle: str = Field(description="Username or address on the provider")
    profile_url: Optional[str] = Field(default=None, description="URL to public profile")
    verified: bool = Field(default=False, description="Whether ownership is verified")
    verified_at: Optional[datetime] = Field(default=None)
    fingerprint: Optional[str] = Field(default=None, description="Cryptographic fingerprint")


class AgentIdentity(BaseModel):
    """Agent Identity Document (AID)."""
    
    version: str = Field(default="0.1", description="AID schema version")
    id: str = Field(description="DID-style identifier, e.g. did:anp:echowolf@moltbook")
    name: str = Field(description="Agent display name")
    description: Optional[str] = Field(default=None, description="Agent description")
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    identity_providers: list[IdentityProvider] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list, description="Declared capabilities")
    
    service_orientation: ServiceOrientation = Field(
        default=ServiceOrientation.NEUTRAL,
        description="Agent's declared service orientation",
    )
    
    public_key: Optional[str] = Field(default=None, description="Ed25519 public key")
    signature: Optional[str] = Field(default=None, description="Self-signature of the document")
    
    avatar_url: Optional[str] = Field(default=None)
    website_url: Optional[str] = Field(default=None)
    
    class Config:
        json_schema_extra = {
            "example": {
                "version": "0.1",
                "id": "did:anp:echowolf@moltbook",
                "name": "EchoWolf",
                "description": "AI assistant for Unity Peace Project",
                "capabilities": ["research", "writing", "code_review"],
                "service_orientation": "service_to_others",
            }
        }

    def to_signable(self) -> dict:
        """Return a dict suitable for signing (excludes signature field)."""
        data = self.model_dump()
        data.pop("signature", None)
        return data

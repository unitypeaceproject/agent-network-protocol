"""Service for identity management operations."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from anp.crypto import generate_keypair, sign_document, encode_public_key
from anp.models.identity import AgentIdentity, IdentityProvider, IdentityProviderType, ServiceOrientation
from anp.storage.repositories.identity_repo import IdentityRepository


class IdentityService:
    """High-level service for managing agent identities.
    
    Provides business logic on top of the identity repository,
    including identity creation with cryptographic keys,
    provider linking and verification, and identity discovery.
    """
    
    def __init__(self, repo: Optional[IdentityRepository] = None):
        self.repo = repo or IdentityRepository()
    
    def create_identity(
        self,
        name: str,
        description: str = "",
        service_orientation: ServiceOrientation = ServiceOrientation.SERVICE_TO_OTHERS,
        capabilities: list[str] = None,
    ) -> tuple[AgentIdentity, bytes]:
        """Create a new agent identity with cryptographic keys.
        
        Returns the identity and the private key bytes.
        The private key should be stored securely by the agent.
        """
        # Generate keypair
        private_key, public_key = generate_keypair()
        public_key_encoded = encode_public_key(public_key)
        
        # Create identity
        now = datetime.now(timezone.utc)
        identity = AgentIdentity(
            id=f"did:anp:{uuid.uuid4()}",
            version="1.0.0",
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
            service_orientation=service_orientation,
            public_key=public_key_encoded,
            capabilities=capabilities or [],
            identity_providers=[],
        )
        
        # Sign the identity document
        doc_to_sign = f"{identity.id}:{identity.name}:{identity.public_key}:{identity.created_at.isoformat()}"
        identity.signature = sign_document(private_key, doc_to_sign)
        
        # Persist
        self.repo.create(identity)
        
        return identity, private_key
    
    def get_identity(self, identity_id: str) -> Optional[AgentIdentity]:
        """Get an identity by ID."""
        return self.repo.get(identity_id)
    
    def update_identity(
        self,
        identity_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        avatar_url: Optional[str] = None,
        website_url: Optional[str] = None,
        capabilities: Optional[list[str]] = None,
    ) -> Optional[AgentIdentity]:
        """Update an existing identity's mutable fields."""
        identity = self.repo.get(identity_id)
        if not identity:
            return None
        
        if name is not None:
            identity.name = name
        if description is not None:
            identity.description = description
        if avatar_url is not None:
            identity.avatar_url = avatar_url
        if website_url is not None:
            identity.website_url = website_url
        if capabilities is not None:
            identity.capabilities = capabilities
        
        return self.repo.update(identity)
    
    def delete_identity(self, identity_id: str) -> bool:
        """Delete an identity. Returns True if deleted."""
        return self.repo.delete(identity_id)
    
    # Provider operations
    
    def link_provider(
        self,
        identity_id: str,
        provider_type: IdentityProviderType,
        handle: str,
        profile_url: Optional[str] = None,
        fingerprint: Optional[str] = None,
    ) -> bool:
        """Link an identity provider to an agent.
        
        The provider starts unverified. Call verify_provider after
        external verification is complete.
        """
        provider = IdentityProvider(
            type=provider_type,
            handle=handle,
            profile_url=profile_url,
            verified=False,
            fingerprint=fingerprint,
        )
        return self.repo.link_provider(identity_id, provider)
    
    def verify_provider(
        self,
        identity_id: str,
        provider_type: IdentityProviderType,
        handle: str,
    ) -> bool:
        """Mark a provider link as verified.
        
        Should be called after external verification (e.g., OAuth callback,
        signature verification, etc.)
        """
        return self.repo.verify_provider(identity_id, provider_type, handle)
    
    # Discovery
    
    def find_by_provider(
        self,
        provider_type: IdentityProviderType,
        handle: str,
    ) -> Optional[AgentIdentity]:
        """Find an identity by its provider handle.
        
        Useful for looking up agents by their Moltbook name,
        ClaudeConnect address, etc.
        """
        return self.repo.get_by_provider(provider_type, handle)
    
    def list_identities(
        self,
        service_orientation: Optional[ServiceOrientation] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentIdentity]:
        """List identities with optional filtering."""
        return self.repo.list(
            service_orientation=service_orientation,
            limit=limit,
            offset=offset,
        )
    
    def search(self, query: str, limit: int = 20) -> list[AgentIdentity]:
        """Search identities by name or description."""
        return self.repo.search(query, limit)
    
    # Verification helpers
    
    def get_verified_providers(self, identity_id: str) -> list[IdentityProvider]:
        """Get only verified providers for an identity."""
        identity = self.repo.get(identity_id)
        if not identity:
            return []
        return [p for p in identity.identity_providers if p.verified]
    
    def is_provider_verified(
        self,
        identity_id: str,
        provider_type: IdentityProviderType,
    ) -> bool:
        """Check if an agent has a verified provider of a given type."""
        identity = self.repo.get(identity_id)
        if not identity:
            return False
        return any(
            p.type == provider_type and p.verified
            for p in identity.identity_providers
        )

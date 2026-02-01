"""ANP Client SDK for agent integration."""

from pathlib import Path
from typing import Optional

from anp.config import settings
from anp.crypto import (
    encode_public_key,
    generate_keypair,
    load_keypair,
    save_keypair,
    sign_document,
)
from anp.models.identity import (
    AgentIdentity,
    IdentityProvider,
    IdentityProviderType,
    ServiceOrientation,
)


class ANPClient:
    """Client for interacting with the Agent Network Protocol."""

    def __init__(
        self,
        identity_dir: Optional[Path] = None,
        api_url: Optional[str] = None,
    ):
        """Initialize the ANP client.
        
        Args:
            identity_dir: Directory for storing identity keys
            api_url: ANP registry API URL (for discovery/collaboration)
        """
        self.identity_dir = identity_dir or settings.identity_dir
        self.api_url = api_url
        self._signing_key = None
        self._verify_key = None
        self._identity: Optional[AgentIdentity] = None

    @property
    def key_path(self) -> Path:
        """Path to the identity key file."""
        return self.identity_dir / "identity.key"

    @property
    def identity_path(self) -> Path:
        """Path to the identity document file."""
        return self.identity_dir / "identity.json"

    def create_identity(
        self,
        name: str,
        description: Optional[str] = None,
        capabilities: Optional[list[str]] = None,
        service_orientation: ServiceOrientation = ServiceOrientation.SERVICE_TO_OTHERS,
    ) -> AgentIdentity:
        """Create a new agent identity with a fresh keypair.
        
        Args:
            name: Agent display name
            description: Agent description
            capabilities: List of capability strings
            service_orientation: Agent's service orientation
            
        Returns:
            The created AgentIdentity
        """
        # Generate keypair
        self._signing_key, self._verify_key = generate_keypair()
        save_keypair(self._signing_key, self.key_path)
        
        # Create identity document
        public_key = encode_public_key(self._verify_key)
        identity = AgentIdentity(
            id=f"did:anp:{name.lower()}",
            name=name,
            description=description,
            capabilities=capabilities or [],
            service_orientation=service_orientation,
            public_key=public_key,
        )
        
        # Sign the identity
        signable = identity.to_signable()
        signature = sign_document(self._signing_key, signable)
        identity.signature = signature
        
        # Save identity document
        self.identity_dir.mkdir(parents=True, exist_ok=True)
        self.identity_path.write_text(identity.model_dump_json(indent=2))
        
        self._identity = identity
        return identity

    def load_identity(self) -> Optional[AgentIdentity]:
        """Load an existing identity from disk.
        
        Returns:
            The loaded AgentIdentity, or None if not found
        """
        if not self.identity_path.exists():
            return None
            
        self._identity = AgentIdentity.model_validate_json(
            self.identity_path.read_text()
        )
        
        if self.key_path.exists():
            self._signing_key, self._verify_key = load_keypair(self.key_path)
            
        return self._identity

    def add_identity_provider(
        self,
        provider_type: IdentityProviderType,
        handle: str,
        profile_url: Optional[str] = None,
    ) -> AgentIdentity:
        """Link an identity provider to this agent.
        
        Args:
            provider_type: Type of identity provider
            handle: Username/address on the provider
            profile_url: URL to public profile
            
        Returns:
            Updated AgentIdentity
        """
        if not self._identity:
            raise ValueError("No identity loaded. Call create_identity() first.")
            
        provider = IdentityProvider(
            type=provider_type,
            handle=handle,
            profile_url=profile_url,
            verified=False,
        )
        
        self._identity.identity_providers.append(provider)
        self._save_identity()
        
        return self._identity

    def _save_identity(self) -> None:
        """Save the current identity to disk."""
        if self._identity and self._signing_key:
            signable = self._identity.to_signable()
            self._identity.signature = sign_document(self._signing_key, signable)
            self.identity_path.write_text(self._identity.model_dump_json(indent=2))

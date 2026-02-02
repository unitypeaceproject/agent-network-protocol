"""Identity management API routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

from nacl.encoding import Base64Encoder

from anp.models.identity import ServiceOrientation, IdentityProviderType
from anp.services import IdentityService

router = APIRouter()
identity_service = IdentityService()


# Request/Response models

class CreateIdentityRequest(BaseModel):
    """Request to create a new agent identity."""
    name: str = Field(..., min_length=1, max_length=100, description="Agent name")
    description: str = Field("", max_length=500, description="Agent description")
    service_orientation: ServiceOrientation = Field(
        ServiceOrientation.SERVICE_TO_OTHERS,
        description="Agent's orientation toward service"
    )
    capabilities: list[str] = Field(
        default_factory=list,
        description="List of agent capabilities"
    )


class CreateIdentityResponse(BaseModel):
    """Response after creating an identity."""
    id: str
    name: str
    public_key: str
    private_key_hex: str  # Hex-encoded private key - store securely!
    message: str = "Store your private key securely. It cannot be recovered."


class UpdateIdentityRequest(BaseModel):
    """Request to update identity fields."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = None
    website_url: Optional[str] = None
    capabilities: Optional[list[str]] = None


class LinkProviderRequest(BaseModel):
    """Request to link an identity provider."""
    provider_type: IdentityProviderType
    handle: str = Field(..., min_length=1, max_length=100)
    profile_url: Optional[str] = None
    fingerprint: Optional[str] = None


class IdentityResponse(BaseModel):
    """Identity details response."""
    id: str
    name: str
    description: str
    service_orientation: str
    public_key: str
    capabilities: list[str]
    providers: list[dict]
    created_at: str
    updated_at: str


class IdentityListResponse(BaseModel):
    """List of identities."""
    identities: list[IdentityResponse]
    total: int


# Routes

@router.post("", response_model=CreateIdentityResponse)
async def create_identity(request: CreateIdentityRequest):
    """Create a new agent identity with cryptographic keys.
    
    Returns the identity ID and private key. Store the private key securely -
    it cannot be recovered if lost.
    """
    identity, private_key = identity_service.create_identity(
        name=request.name,
        description=request.description,
        service_orientation=request.service_orientation,
        capabilities=request.capabilities,
    )
    
    return CreateIdentityResponse(
        id=identity.id,
        name=identity.name,
        public_key=identity.public_key,
        private_key_hex=private_key.encode(encoder=Base64Encoder).decode(),
    )


@router.get("/{identity_id}", response_model=IdentityResponse)
async def get_identity(identity_id: str):
    """Get an identity by ID."""
    identity = identity_service.get_identity(identity_id)
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found")
    
    return IdentityResponse(
        id=identity.id,
        name=identity.name,
        description=identity.description,
        service_orientation=identity.service_orientation.value,
        public_key=identity.public_key,
        capabilities=identity.capabilities,
        providers=[
            {
                "type": p.type.value,
                "handle": p.handle,
                "profile_url": p.profile_url,
                "verified": p.verified,
            }
            for p in identity.identity_providers
        ],
        created_at=identity.created_at.isoformat(),
        updated_at=identity.updated_at.isoformat(),
    )


@router.patch("/{identity_id}", response_model=IdentityResponse)
async def update_identity(
    identity_id: str,
    request: UpdateIdentityRequest,
    x_agent_id: str = Header(..., description="Your agent ID for authentication"),
):
    """Update an identity's mutable fields.
    
    Requires authentication via X-Agent-ID header.
    """
    if x_agent_id != identity_id:
        raise HTTPException(status_code=403, detail="Can only update your own identity")
    
    identity = identity_service.update_identity(
        identity_id=identity_id,
        name=request.name,
        description=request.description,
        avatar_url=request.avatar_url,
        website_url=request.website_url,
        capabilities=request.capabilities,
    )
    
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found")
    
    return IdentityResponse(
        id=identity.id,
        name=identity.name,
        description=identity.description,
        service_orientation=identity.service_orientation.value,
        public_key=identity.public_key,
        capabilities=identity.capabilities,
        providers=[
            {
                "type": p.type.value,
                "handle": p.handle,
                "profile_url": p.profile_url,
                "verified": p.verified,
            }
            for p in identity.identity_providers
        ],
        created_at=identity.created_at.isoformat(),
        updated_at=identity.updated_at.isoformat(),
    )


@router.delete("/{identity_id}")
async def delete_identity(
    identity_id: str,
    x_agent_id: str = Header(..., description="Your agent ID for authentication"),
):
    """Delete an identity.
    
    This is irreversible. All associated data will be removed.
    """
    if x_agent_id != identity_id:
        raise HTTPException(status_code=403, detail="Can only delete your own identity")
    
    success = identity_service.delete_identity(identity_id)
    if not success:
        raise HTTPException(status_code=404, detail="Identity not found")
    
    return {"status": "deleted", "identity_id": identity_id}


@router.post("/{identity_id}/providers")
async def link_provider(
    identity_id: str,
    request: LinkProviderRequest,
    x_agent_id: str = Header(..., description="Your agent ID for authentication"),
):
    """Link an identity provider (Moltbook, ClaudeConnect, etc.)
    
    The provider link starts unverified. Complete the verification flow
    to mark it as verified.
    """
    if x_agent_id != identity_id:
        raise HTTPException(status_code=403, detail="Can only modify your own identity")
    
    success = identity_service.link_provider(
        identity_id=identity_id,
        provider_type=request.provider_type,
        handle=request.handle,
        profile_url=request.profile_url,
        fingerprint=request.fingerprint,
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to link provider")
    
    return {
        "status": "linked",
        "provider_type": request.provider_type.value,
        "handle": request.handle,
        "verified": False,
        "message": "Complete verification to mark as verified",
    }


@router.post("/{identity_id}/providers/{provider_type}/verify")
async def verify_provider(
    identity_id: str,
    provider_type: IdentityProviderType,
    handle: str,
    x_agent_id: str = Header(..., description="Your agent ID for authentication"),
):
    """Mark a provider link as verified.
    
    This should be called after external verification is complete
    (e.g., OAuth callback, signature verification).
    
    In production, this endpoint would verify proof of ownership.
    """
    if x_agent_id != identity_id:
        raise HTTPException(status_code=403, detail="Can only modify your own identity")
    
    success = identity_service.verify_provider(
        identity_id=identity_id,
        provider_type=provider_type,
        handle=handle,
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to verify provider")
    
    return {
        "status": "verified",
        "provider_type": provider_type.value,
        "handle": handle,
    }


@router.get("", response_model=IdentityListResponse)
async def list_identities(
    service_orientation: Optional[ServiceOrientation] = None,
    limit: int = 100,
    offset: int = 0,
):
    """List identities with optional filtering."""
    identities = identity_service.list_identities(
        service_orientation=service_orientation,
        limit=limit,
        offset=offset,
    )
    
    return IdentityListResponse(
        identities=[
            IdentityResponse(
                id=i.id,
                name=i.name,
                description=i.description,
                service_orientation=i.service_orientation.value,
                public_key=i.public_key,
                capabilities=i.capabilities,
                providers=[
                    {
                        "type": p.type.value,
                        "handle": p.handle,
                        "profile_url": p.profile_url,
                        "verified": p.verified,
                    }
                    for p in i.identity_providers
                ],
                created_at=i.created_at.isoformat(),
                updated_at=i.updated_at.isoformat(),
            )
            for i in identities
        ],
        total=len(identities),
    )


@router.get("/search")
async def search_identities(query: str, limit: int = 20):
    """Search identities by name or description."""
    identities = identity_service.search(query, limit)
    
    return {
        "query": query,
        "results": [
            {
                "id": i.id,
                "name": i.name,
                "description": i.description,
                "service_orientation": i.service_orientation.value,
            }
            for i in identities
        ],
        "count": len(identities),
    }


@router.get("/by-provider/{provider_type}/{handle}")
async def get_by_provider(provider_type: IdentityProviderType, handle: str):
    """Find an identity by its provider handle.
    
    Useful for looking up agents by their Moltbook name,
    ClaudeConnect address, etc.
    """
    identity = identity_service.find_by_provider(provider_type, handle)
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found for this provider")
    
    return {
        "id": identity.id,
        "name": identity.name,
        "provider": {
            "type": provider_type.value,
            "handle": handle,
        },
    }

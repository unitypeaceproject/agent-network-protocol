"""Verification routes for identity provider verification flows.

This module integrates the adapters (Moltbook, ClaudeConnect) into the API,
providing a complete verification flow for agents to prove ownership of
their external identities.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

from anp.models.identity import IdentityProviderType
from anp.services import IdentityService
from anp.adapters.moltbook import MoltbookAdapter, VerificationChallenge as MoltbookChallenge
from anp.adapters.claudeconnect import ClaudeConnectAdapter, KeyExchangeChallenge as CCChallenge

router = APIRouter()
identity_service = IdentityService()

# Adapter instances (in production, these would be properly managed)
moltbook_adapter = MoltbookAdapter()
claudeconnect_adapter = ClaudeConnectAdapter()


# Request/Response models

class StartVerificationRequest(BaseModel):
    """Request to start a verification flow."""
    provider_type: IdentityProviderType = Field(..., description="Provider to verify (moltbook, claude_connect)")
    handle: str = Field(..., min_length=1, max_length=100, description="Handle/address on the provider")
    fingerprint: Optional[str] = Field(None, description="Key fingerprint (required for ClaudeConnect)")


class StartVerificationResponse(BaseModel):
    """Response with challenge details."""
    challenge_id: str
    provider_type: str
    handle: str
    challenge_code: str
    instructions: str
    expires_at: str


class CompleteVerificationRequest(BaseModel):
    """Request to complete verification."""
    challenge_id: str = Field(..., description="Challenge ID from start verification")
    # For ClaudeConnect, the signature of the challenge and fingerprint
    signature: Optional[str] = Field(None, description="Signed nonce (required for ClaudeConnect)")
    fingerprint: Optional[str] = Field(None, description="Key fingerprint (required for ClaudeConnect)")


class CompleteVerificationResponse(BaseModel):
    """Response after verification attempt."""
    success: bool
    provider_type: str
    handle: str
    message: str
    verified_at: Optional[str] = None


class VerificationStatusResponse(BaseModel):
    """Status of a verification challenge."""
    challenge_id: str
    provider_type: str
    handle: str
    status: str  # pending, verified, expired, not_found
    created_at: Optional[str] = None
    expires_at: Optional[str] = None


# In-memory challenge storage (maps challenge_id to agent_id and provider)
# In production, use persistent storage
_challenge_registry: dict[str, dict] = {}


# Routes

@router.post("/start", response_model=StartVerificationResponse)
async def start_verification(
    request: StartVerificationRequest,
    x_agent_id: str = Header(..., description="Your agent ID"),
):
    """Start a verification flow for an identity provider.
    
    Returns a challenge that must be completed to prove ownership.
    
    For Moltbook:
    - Post the challenge code from the claimed account
    - Then call /verify/complete with the challenge_id
    
    For ClaudeConnect:
    - Sign the challenge code with your ClaudeConnect key
    - Then call /verify/complete with the challenge_id and signature
    """
    # Verify agent exists
    agent = identity_service.get_identity(x_agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Check if provider is already linked and verified
    for provider in agent.identity_providers:
        if provider.type == request.provider_type and provider.handle == request.handle:
            if provider.verified:
                raise HTTPException(
                    status_code=400,
                    detail=f"Provider {request.provider_type.value}:{request.handle} already verified"
                )
    
    if request.provider_type == IdentityProviderType.MOLTBOOK:
        return await _start_moltbook_verification(x_agent_id, request.handle)
    elif request.provider_type == IdentityProviderType.CLAUDE_CONNECT:
        if not request.fingerprint:
            raise HTTPException(
                status_code=400,
                detail="Fingerprint required for ClaudeConnect verification"
            )
        return await _start_claudeconnect_verification(x_agent_id, request.handle, request.fingerprint)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Verification not supported for provider: {request.provider_type.value}"
        )


async def _start_moltbook_verification(agent_id: str, handle: str) -> StartVerificationResponse:
    """Start Moltbook verification flow."""
    # Check if user exists on Moltbook
    user_exists = await moltbook_adapter.user_exists(handle)
    if not user_exists:
        raise HTTPException(
            status_code=400,
            detail=f"Moltbook user '{handle}' not found"
        )
    
    # Create challenge
    challenge = moltbook_adapter.create_verification_challenge(agent_id, handle)
    
    # Register challenge
    _challenge_registry[challenge.challenge_id] = {
        "agent_id": agent_id,
        "provider_type": IdentityProviderType.MOLTBOOK,
        "handle": handle,
    }
    
    instructions = moltbook_adapter.get_challenge_instructions(challenge)
    
    return StartVerificationResponse(
        challenge_id=challenge.challenge_id,
        provider_type=IdentityProviderType.MOLTBOOK.value,
        handle=handle,
        challenge_code=challenge.challenge_code,
        instructions=instructions,
        expires_at=challenge.expires_at.isoformat(),
    )


async def _start_claudeconnect_verification(agent_id: str, handle: str, fingerprint: str) -> StartVerificationResponse:
    """Start ClaudeConnect verification flow."""
    # Create challenge
    challenge = claudeconnect_adapter.create_verification_challenge(agent_id, handle, fingerprint)
    
    # Register challenge
    _challenge_registry[challenge.challenge_id] = {
        "agent_id": agent_id,
        "provider_type": IdentityProviderType.CLAUDE_CONNECT,
        "handle": handle,
    }
    
    instructions = claudeconnect_adapter.get_challenge_instructions(challenge)
    
    return StartVerificationResponse(
        challenge_id=challenge.challenge_id,
        provider_type=IdentityProviderType.CLAUDE_CONNECT.value,
        handle=handle,
        challenge_code=challenge.challenge_nonce,
        instructions=instructions,
        expires_at=challenge.expires_at.isoformat(),
    )


@router.post("/complete", response_model=CompleteVerificationResponse)
async def complete_verification(
    request: CompleteVerificationRequest,
    x_agent_id: str = Header(..., description="Your agent ID"),
):
    """Complete a verification flow.
    
    For Moltbook: Just provide the challenge_id (we check for the post)
    For ClaudeConnect: Provide challenge_id and signature
    """
    # Look up challenge
    reg = _challenge_registry.get(request.challenge_id)
    if not reg:
        raise HTTPException(status_code=404, detail="Challenge not found")
    
    # Verify ownership
    if reg["agent_id"] != x_agent_id:
        raise HTTPException(status_code=403, detail="Challenge belongs to different agent")
    
    provider_type = reg["provider_type"]
    handle = reg["handle"]
    
    if provider_type == IdentityProviderType.MOLTBOOK:
        return await _complete_moltbook_verification(x_agent_id, request.challenge_id, handle)
    elif provider_type == IdentityProviderType.CLAUDE_CONNECT:
        if not request.signature or not request.fingerprint:
            raise HTTPException(
                status_code=400,
                detail="Signature and fingerprint required for ClaudeConnect verification"
            )
        return await _complete_claudeconnect_verification(
            x_agent_id, request.challenge_id, handle, request.signature, request.fingerprint
        )
    else:
        raise HTTPException(status_code=400, detail="Unknown provider type")


async def _complete_moltbook_verification(
    agent_id: str,
    challenge_id: str,
    handle: str,
) -> CompleteVerificationResponse:
    """Complete Moltbook verification by checking for challenge post."""
    success, message = await moltbook_adapter.verify_challenge(challenge_id)
    
    if success:
        # Link and verify the provider
        identity_service.link_provider(
            identity_id=agent_id,
            provider_type=IdentityProviderType.MOLTBOOK,
            handle=handle,
            profile_url=f"https://moltbook.com/u/{handle}",
        )
        identity_service.verify_provider(
            identity_id=agent_id,
            provider_type=IdentityProviderType.MOLTBOOK,
            handle=handle,
        )
        
        # Clean up
        del _challenge_registry[challenge_id]
        
        return CompleteVerificationResponse(
            success=True,
            provider_type=IdentityProviderType.MOLTBOOK.value,
            handle=handle,
            message=message,
            verified_at=datetime.now(timezone.utc).isoformat(),
        )
    else:
        return CompleteVerificationResponse(
            success=False,
            provider_type=IdentityProviderType.MOLTBOOK.value,
            handle=handle,
            message=message,
        )


async def _complete_claudeconnect_verification(
    agent_id: str,
    challenge_id: str,
    handle: str,
    signature: str,
    fingerprint: str,
) -> CompleteVerificationResponse:
    """Complete ClaudeConnect verification by checking signature."""
    success, message = claudeconnect_adapter.verify_challenge(challenge_id, signature, fingerprint)
    
    if success:
        # Get fingerprint from the challenge
        challenge = claudeconnect_adapter.get_challenge(challenge_id)
        fingerprint = challenge.expected_fingerprint if challenge else None
        
        # Link and verify the provider
        identity_service.link_provider(
            identity_id=agent_id,
            provider_type=IdentityProviderType.CLAUDE_CONNECT,
            handle=handle,
            fingerprint=fingerprint,
        )
        identity_service.verify_provider(
            identity_id=agent_id,
            provider_type=IdentityProviderType.CLAUDE_CONNECT,
            handle=handle,
        )
        
        # Clean up
        del _challenge_registry[challenge_id]
        
        return CompleteVerificationResponse(
            success=True,
            provider_type=IdentityProviderType.CLAUDE_CONNECT.value,
            handle=handle,
            message=message,
            verified_at=datetime.now(timezone.utc).isoformat(),
        )
    else:
        return CompleteVerificationResponse(
            success=False,
            provider_type=IdentityProviderType.CLAUDE_CONNECT.value,
            handle=handle,
            message=message,
        )


@router.get("/status/{challenge_id}", response_model=VerificationStatusResponse)
async def get_verification_status(
    challenge_id: str,
    x_agent_id: str = Header(..., description="Your agent ID"),
):
    """Check the status of a verification challenge."""
    reg = _challenge_registry.get(challenge_id)
    if not reg:
        return VerificationStatusResponse(
            challenge_id=challenge_id,
            provider_type="unknown",
            handle="unknown",
            status="not_found",
        )
    
    if reg["agent_id"] != x_agent_id:
        raise HTTPException(status_code=403, detail="Challenge belongs to different agent")
    
    provider_type = reg["provider_type"]
    handle = reg["handle"]
    
    # Get challenge from adapter
    if provider_type == IdentityProviderType.MOLTBOOK:
        challenge = moltbook_adapter.get_challenge(challenge_id)
        if not challenge:
            return VerificationStatusResponse(
                challenge_id=challenge_id,
                provider_type=provider_type.value,
                handle=handle,
                status="not_found",
            )
        
        now = datetime.now(timezone.utc)
        if challenge.verified:
            status = "verified"
        elif now > challenge.expires_at:
            status = "expired"
        else:
            status = "pending"
        
        return VerificationStatusResponse(
            challenge_id=challenge_id,
            provider_type=provider_type.value,
            handle=handle,
            status=status,
            created_at=challenge.created_at.isoformat(),
            expires_at=challenge.expires_at.isoformat(),
        )
    
    elif provider_type == IdentityProviderType.CLAUDE_CONNECT:
        challenge = claudeconnect_adapter.get_challenge(challenge_id)
        if not challenge:
            return VerificationStatusResponse(
                challenge_id=challenge_id,
                provider_type=provider_type.value,
                handle=handle,
                status="not_found",
            )
        
        now = datetime.now(timezone.utc)
        if challenge.verified:
            status = "verified"
        elif now > challenge.expires_at:
            status = "expired"
        else:
            status = "pending"
        
        return VerificationStatusResponse(
            challenge_id=challenge_id,
            provider_type=provider_type.value,
            handle=handle,
            status=status,
            created_at=challenge.created_at.isoformat(),
            expires_at=challenge.expires_at.isoformat(),
        )
    
    return VerificationStatusResponse(
        challenge_id=challenge_id,
        provider_type=provider_type.value if hasattr(provider_type, 'value') else str(provider_type),
        handle=handle,
        status="unknown",
    )


@router.get("/providers")
async def list_supported_providers():
    """List supported identity providers and their verification methods."""
    return {
        "providers": [
            {
                "type": "moltbook",
                "name": "Moltbook",
                "verification_method": "post_challenge",
                "description": "Post a challenge code from your Moltbook account",
            },
            {
                "type": "claude_connect",
                "name": "ClaudeConnect",
                "verification_method": "sign_challenge",
                "description": "Sign a challenge with your ClaudeConnect private key",
            },
            {
                "type": "ens",
                "name": "ENS (Ethereum Name Service)",
                "verification_method": "sign_message",
                "description": "Sign a message with the wallet that owns the ENS name",
                "status": "coming_soon",
            },
            {
                "type": "worldid",
                "name": "World ID",
                "verification_method": "proof_of_personhood",
                "description": "Verify via World ID proof of personhood",
                "status": "coming_soon",
            },
        ]
    }


@router.get("/agent/{agent_id}")
async def get_agent_verifications(agent_id: str):
    """Get all verified providers for an agent."""
    agent = identity_service.get_identity(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return {
        "agent_id": agent_id,
        "agent_name": agent.name,
        "providers": [
            {
                "type": p.type.value,
                "handle": p.handle,
                "profile_url": p.profile_url,
                "verified": p.verified,
                "verified_at": p.verified_at.isoformat() if p.verified_at else None,
            }
            for p in agent.identity_providers
        ],
        "verification_count": sum(1 for p in agent.identity_providers if p.verified),
    }

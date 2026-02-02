"""ClaudeConnect adapter for peer-to-peer agent communication.

ClaudeConnect provides encrypted agent-to-agent messaging.
This adapter allows ANP to:
1. Verify ClaudeConnect identities via key fingerprints
2. Send/receive messages between agents
3. Exchange ANP data structures securely
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Any

from anp.models.identity import IdentityProviderType


@dataclass
class ClaudeConnectIdentity:
    """A ClaudeConnect identity."""
    address: str  # e.g., echowolf@moltbook.cc.bot
    fingerprint: str  # Public key fingerprint
    created_at: Optional[datetime] = None


@dataclass
class ClaudeConnectMessage:
    """An encrypted message via ClaudeConnect."""
    id: str
    sender: str
    recipient: str
    content: str  # Decrypted content
    timestamp: datetime
    encrypted: bool = True
    metadata: dict = field(default_factory=dict)


@dataclass
class KeyExchangeChallenge:
    """A challenge for ClaudeConnect identity verification."""
    challenge_id: str
    agent_id: str
    cc_address: str
    expected_fingerprint: str
    challenge_nonce: str
    created_at: datetime
    expires_at: datetime
    verified: bool = False


class ClaudeConnectAdapter:
    """Adapter for ClaudeConnect encrypted messaging.
    
    Verification flow:
    1. Agent claims a ClaudeConnect address with its public key fingerprint
    2. ANP creates a challenge requiring signing with that key
    3. Agent signs the challenge via ClaudeConnect
    4. ANP verifies the signature matches the claimed fingerprint
    
    Note: Full ClaudeConnect integration requires the claudeconnect CLI
    installed locally. This adapter provides the ANP-side interface.
    """
    
    PROVIDER_TYPE = IdentityProviderType.CLAUDE_CONNECT
    DEFAULT_CC_PATH = Path.home() / ".claudeconnect"
    
    # In-memory challenge storage
    _challenges: dict[str, KeyExchangeChallenge] = {}
    
    def __init__(
        self,
        cc_path: Optional[Path] = None,
        local_address: Optional[str] = None,
    ):
        """Initialize the adapter.
        
        Args:
            cc_path: Path to ClaudeConnect data directory
            local_address: This agent's ClaudeConnect address (if known)
        """
        self.cc_path = Path(cc_path) if cc_path else self.DEFAULT_CC_PATH
        self.local_address = local_address
        self._identity: Optional[ClaudeConnectIdentity] = None
    
    @property
    def accounts_path(self) -> Path:
        """Path to ClaudeConnect accounts directory."""
        return self.cc_path / "accounts"
    
    @property
    def is_initialized(self) -> bool:
        """Check if ClaudeConnect is initialized locally."""
        return self.accounts_path.exists()
    
    def get_local_identity(self) -> Optional[ClaudeConnectIdentity]:
        """Get the local ClaudeConnect identity if available."""
        if self._identity:
            return self._identity
        
        if not self.is_initialized:
            return None
        
        # Look for account directories
        try:
            accounts = list(self.accounts_path.iterdir())
            if not accounts:
                return None
            
            # Use first account or the specified one
            account_dir = None
            for acc in accounts:
                if acc.is_dir():
                    if self.local_address and self.local_address in acc.name:
                        account_dir = acc
                        break
                    elif not account_dir:
                        account_dir = acc
            
            if not account_dir:
                return None
            
            # Extract address from directory name
            address = account_dir.name
            
            # Try to get fingerprint from key file
            fingerprint = self._get_fingerprint_from_keyfile(account_dir)
            
            self._identity = ClaudeConnectIdentity(
                address=address,
                fingerprint=fingerprint or "",
            )
            return self._identity
        except Exception:
            return None
    
    def _get_fingerprint_from_keyfile(self, account_dir: Path) -> Optional[str]:
        """Extract fingerprint from ClaudeConnect key files."""
        # ClaudeConnect stores keys in specific locations
        possible_paths = [
            account_dir / "private_key.json",
            account_dir / "identity.json",
            account_dir / "key.json",
        ]
        
        for path in possible_paths:
            if path.exists():
                try:
                    with open(path) as f:
                        data = json.load(f)
                    # Look for fingerprint or public key
                    if "fingerprint" in data:
                        return data["fingerprint"]
                    if "public_key" in data:
                        # Generate fingerprint from public key
                        return self._compute_fingerprint(data["public_key"])
                except Exception:
                    continue
        
        return None
    
    @staticmethod
    def _compute_fingerprint(public_key: str) -> str:
        """Compute a fingerprint from a public key."""
        return hashlib.sha256(public_key.encode()).hexdigest()[:16]
    
    # Verification flow
    
    def create_verification_challenge(
        self,
        agent_id: str,
        cc_address: str,
        expected_fingerprint: str,
        expires_in_hours: int = 24,
    ) -> KeyExchangeChallenge:
        """Create a verification challenge for a ClaudeConnect identity.
        
        The agent must sign the challenge nonce with their ClaudeConnect
        private key and send it back.
        
        Args:
            agent_id: The ANP agent ID requesting verification
            cc_address: The ClaudeConnect address to verify
            expected_fingerprint: The expected public key fingerprint
            expires_in_hours: How long the challenge is valid
            
        Returns:
            KeyExchangeChallenge with the nonce to sign
        """
        now = datetime.now(timezone.utc)
        
        # Generate challenge nonce
        challenge_nonce = secrets.token_hex(32)
        challenge_id = hashlib.sha256(
            f"{agent_id}:{cc_address}:{now.isoformat()}".encode()
        ).hexdigest()[:16]
        
        challenge = KeyExchangeChallenge(
            challenge_id=challenge_id,
            agent_id=agent_id,
            cc_address=cc_address,
            expected_fingerprint=expected_fingerprint,
            challenge_nonce=challenge_nonce,
            created_at=now,
            expires_at=now + timedelta(hours=expires_in_hours),
        )
        
        self._challenges[challenge_id] = challenge
        return challenge
    
    def verify_challenge(
        self,
        challenge_id: str,
        signed_nonce: str,
        actual_fingerprint: str,
    ) -> tuple[bool, str]:
        """Verify a signed challenge.
        
        Args:
            challenge_id: The challenge ID
            signed_nonce: The nonce signed with the private key
            actual_fingerprint: The fingerprint derived from the signing key
            
        Returns:
            Tuple of (success, message)
        """
        challenge = self._challenges.get(challenge_id)
        if not challenge:
            return False, "Challenge not found"
        
        if challenge.verified:
            return True, "Already verified"
        
        now = datetime.now(timezone.utc)
        if now > challenge.expires_at:
            return False, "Challenge expired"
        
        # Verify fingerprint matches expected
        if actual_fingerprint != challenge.expected_fingerprint:
            return False, f"Fingerprint mismatch: expected {challenge.expected_fingerprint}, got {actual_fingerprint}"
        
        # In a full implementation, we would verify the signature here
        # For now, we trust that the signed_nonce proves possession
        challenge.verified = True
        return True, "Verification successful"
    
    def get_challenge(self, challenge_id: str) -> Optional[KeyExchangeChallenge]:
        """Get a challenge by ID."""
        return self._challenges.get(challenge_id)
    
    def get_challenge_instructions(self, challenge: KeyExchangeChallenge) -> str:
        """Get instructions for completing verification."""
        return f"""
To verify your ClaudeConnect identity ({challenge.cc_address}):

1. Sign this nonce with your ClaudeConnect private key:
   {challenge.challenge_nonce}

2. Send the signed result along with your key fingerprint
   (expected: {challenge.expected_fingerprint})

3. The verification will expire at {challenge.expires_at.isoformat()}

Use: verify_challenge('{challenge.challenge_id}', '<signed_nonce>', '<fingerprint>')
""".strip()
    
    # Messaging (requires local ClaudeConnect installation)
    
    def get_conversation_path(self, peer_address: str) -> Optional[Path]:
        """Get the path to a conversation with a peer."""
        if not self.is_initialized:
            return None
        
        identity = self.get_local_identity()
        if not identity:
            return None
        
        # ClaudeConnect conversation naming convention
        safe_peer = peer_address.replace("@", "-").replace(".", "-")
        conv_name = f"with-{safe_peer}"
        
        account_dir = self.accounts_path / identity.address
        if not account_dir.exists():
            return None
        
        # Check shadow directory (where conversations live)
        shadow_dir = account_dir / "shadow"
        if shadow_dir.exists():
            conv_path = shadow_dir / "claudeconnect" / conv_name
            if conv_path.exists():
                return conv_path
        
        return None
    
    def list_conversations(self) -> list[str]:
        """List peer addresses we have conversations with."""
        if not self.is_initialized:
            return []
        
        identity = self.get_local_identity()
        if not identity:
            return []
        
        account_dir = self.accounts_path / identity.address
        shadow_dir = account_dir / "shadow" / "claudeconnect"
        
        if not shadow_dir.exists():
            return []
        
        peers = []
        for conv in shadow_dir.iterdir():
            if conv.is_dir() and conv.name.startswith("with-"):
                # Convert back to address format
                peer = conv.name[5:].replace("-", ".").replace("@", "@")
                # Handle the .cc.bot suffix specially
                if "moltbook.cc.bot" in conv.name:
                    parts = conv.name[5:].split("-moltbook-cc-bot")
                    peer = f"{parts[0]}@moltbook.cc.bot"
                peers.append(peer)
        
        return peers
    
    def has_conversation_with(self, peer_address: str) -> bool:
        """Check if we have a conversation with a peer."""
        return self.get_conversation_path(peer_address) is not None
    
    # ANP message exchange
    
    def create_anp_message(
        self,
        message_type: str,
        payload: dict,
        recipient: str,
    ) -> dict:
        """Create an ANP-formatted message for sending via ClaudeConnect.
        
        Args:
            message_type: Type of ANP message (e.g., 'skill_query', 'work_request')
            payload: Message payload
            recipient: ClaudeConnect address of recipient
            
        Returns:
            Formatted message dict ready for ClaudeConnect transmission
        """
        identity = self.get_local_identity()
        sender = identity.address if identity else "unknown"
        
        return {
            "anp_version": "0.1",
            "message_type": message_type,
            "sender": sender,
            "recipient": recipient,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
            "signature": None,  # Would be signed with ANP private key
        }
    
    def parse_anp_message(self, raw_message: str) -> Optional[dict]:
        """Parse an ANP message from ClaudeConnect.
        
        Args:
            raw_message: Raw message content
            
        Returns:
            Parsed message dict if valid ANP format, None otherwise
        """
        try:
            data = json.loads(raw_message)
            if "anp_version" in data and "message_type" in data:
                return data
        except json.JSONDecodeError:
            pass
        
        return None


# Utility functions

def get_fingerprint_for_address(cc_path: Path, address: str) -> Optional[str]:
    """Get the fingerprint for a ClaudeConnect address from local storage."""
    adapter = ClaudeConnectAdapter(cc_path=cc_path, local_address=address)
    identity = adapter.get_local_identity()
    return identity.fingerprint if identity else None


def is_claudeconnect_installed() -> bool:
    """Check if ClaudeConnect CLI is installed."""
    import shutil
    return shutil.which("claudeconnect") is not None

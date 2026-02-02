"""Tests for ANP adapters."""
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from anp.adapters.moltbook import (
    MoltbookAdapter,
    MoltbookAdapterSync,
    MoltbookUser,
    MoltbookPost,
    VerificationChallenge,
)
from anp.adapters.claudeconnect import (
    ClaudeConnectAdapter,
    ClaudeConnectIdentity,
    KeyExchangeChallenge,
    get_fingerprint_for_address,
)


class TestMoltbookAdapter:
    """Tests for MoltbookAdapter."""
    
    def test_create_verification_challenge(self):
        """Test creating a verification challenge."""
        adapter = MoltbookAdapter()
        
        challenge = adapter.create_verification_challenge(
            agent_id="did:anp:test123",
            moltbook_handle="TestUser",
            expires_in_hours=24,
        )
        
        assert challenge.challenge_id is not None
        assert challenge.agent_id == "did:anp:test123"
        assert challenge.moltbook_handle == "TestUser"
        assert challenge.challenge_code.startswith("anp-verify-")
        assert not challenge.verified
        assert challenge.expires_at > challenge.created_at
    
    def test_get_challenge(self):
        """Test retrieving a challenge."""
        adapter = MoltbookAdapter()
        
        challenge = adapter.create_verification_challenge(
            agent_id="did:anp:test123",
            moltbook_handle="TestUser",
        )
        
        retrieved = adapter.get_challenge(challenge.challenge_id)
        assert retrieved is not None
        assert retrieved.challenge_id == challenge.challenge_id
        
        # Non-existent challenge
        assert adapter.get_challenge("nonexistent") is None
    
    def test_challenge_instructions(self):
        """Test generating challenge instructions."""
        adapter = MoltbookAdapter()
        
        challenge = adapter.create_verification_challenge(
            agent_id="did:anp:test123",
            moltbook_handle="TestUser",
        )
        
        instructions = adapter.get_challenge_instructions(challenge)
        
        assert challenge.challenge_code in instructions
        assert "@TestUser" in instructions
        assert challenge.challenge_id in instructions
    
    def test_headers_without_api_key(self):
        """Test headers without API key."""
        adapter = MoltbookAdapter()
        headers = adapter.headers
        
        assert "Content-Type" in headers
        assert "Authorization" not in headers
    
    def test_headers_with_api_key(self):
        """Test headers with API key."""
        adapter = MoltbookAdapter(api_key="test_key")
        headers = adapter.headers
        
        assert "Content-Type" in headers
        assert headers["Authorization"] == "Bearer test_key"


class TestClaudeConnectAdapter:
    """Tests for ClaudeConnectAdapter."""
    
    def test_create_verification_challenge(self):
        """Test creating a key exchange challenge."""
        adapter = ClaudeConnectAdapter()
        
        challenge = adapter.create_verification_challenge(
            agent_id="did:anp:test123",
            cc_address="testuser@moltbook.cc.bot",
            expected_fingerprint="abc123def456",
            expires_in_hours=24,
        )
        
        assert challenge.challenge_id is not None
        assert challenge.agent_id == "did:anp:test123"
        assert challenge.cc_address == "testuser@moltbook.cc.bot"
        assert challenge.expected_fingerprint == "abc123def456"
        assert len(challenge.challenge_nonce) == 64  # 32 bytes hex
        assert not challenge.verified
    
    def test_verify_challenge_success(self):
        """Test successful challenge verification."""
        adapter = ClaudeConnectAdapter()
        
        challenge = adapter.create_verification_challenge(
            agent_id="did:anp:test123",
            cc_address="testuser@moltbook.cc.bot",
            expected_fingerprint="abc123def456",
        )
        
        # Simulate successful verification
        success, message = adapter.verify_challenge(
            challenge_id=challenge.challenge_id,
            signed_nonce="signed_" + challenge.challenge_nonce,
            actual_fingerprint="abc123def456",
        )
        
        assert success
        assert "successful" in message.lower()
        assert challenge.verified
    
    def test_verify_challenge_fingerprint_mismatch(self):
        """Test challenge verification with wrong fingerprint."""
        adapter = ClaudeConnectAdapter()
        
        challenge = adapter.create_verification_challenge(
            agent_id="did:anp:test123",
            cc_address="testuser@moltbook.cc.bot",
            expected_fingerprint="abc123def456",
        )
        
        success, message = adapter.verify_challenge(
            challenge_id=challenge.challenge_id,
            signed_nonce="signed_nonce",
            actual_fingerprint="wrong_fingerprint",
        )
        
        assert not success
        assert "mismatch" in message.lower()
        assert not challenge.verified
    
    def test_verify_challenge_not_found(self):
        """Test verifying non-existent challenge."""
        adapter = ClaudeConnectAdapter()
        
        success, message = adapter.verify_challenge(
            challenge_id="nonexistent",
            signed_nonce="signed_nonce",
            actual_fingerprint="fingerprint",
        )
        
        assert not success
        assert "not found" in message.lower()
    
    def test_challenge_instructions(self):
        """Test generating challenge instructions."""
        adapter = ClaudeConnectAdapter()
        
        challenge = adapter.create_verification_challenge(
            agent_id="did:anp:test123",
            cc_address="testuser@moltbook.cc.bot",
            expected_fingerprint="abc123def456",
        )
        
        instructions = adapter.get_challenge_instructions(challenge)
        
        assert challenge.challenge_nonce in instructions
        assert challenge.expected_fingerprint in instructions
        assert challenge.cc_address in instructions
    
    def test_compute_fingerprint(self):
        """Test fingerprint computation."""
        fingerprint = ClaudeConnectAdapter._compute_fingerprint("test_public_key")
        
        assert len(fingerprint) == 16
        # Same key should produce same fingerprint
        assert fingerprint == ClaudeConnectAdapter._compute_fingerprint("test_public_key")
        # Different key should produce different fingerprint
        assert fingerprint != ClaudeConnectAdapter._compute_fingerprint("other_key")
    
    def test_create_anp_message(self):
        """Test creating ANP-formatted messages."""
        adapter = ClaudeConnectAdapter()
        
        message = adapter.create_anp_message(
            message_type="skill_query",
            payload={"skill": "python", "min_level": 0.7},
            recipient="other@moltbook.cc.bot",
        )
        
        assert message["anp_version"] == "0.1"
        assert message["message_type"] == "skill_query"
        assert message["recipient"] == "other@moltbook.cc.bot"
        assert message["payload"]["skill"] == "python"
    
    def test_parse_anp_message_valid(self):
        """Test parsing valid ANP message."""
        adapter = ClaudeConnectAdapter()
        
        raw = '{"anp_version": "0.1", "message_type": "test", "payload": {}}'
        parsed = adapter.parse_anp_message(raw)
        
        assert parsed is not None
        assert parsed["anp_version"] == "0.1"
        assert parsed["message_type"] == "test"
    
    def test_parse_anp_message_invalid(self):
        """Test parsing invalid ANP message."""
        adapter = ClaudeConnectAdapter()
        
        # Not JSON
        assert adapter.parse_anp_message("not json") is None
        
        # JSON but not ANP format
        assert adapter.parse_anp_message('{"foo": "bar"}') is None
        
        # Missing message_type
        assert adapter.parse_anp_message('{"anp_version": "0.1"}') is None


class TestMoltbookAdapterSync:
    """Tests for synchronous Moltbook adapter wrapper."""
    
    def test_create_verification_challenge(self):
        """Test sync wrapper creates challenges."""
        adapter = MoltbookAdapterSync()
        
        challenge = adapter.create_verification_challenge(
            agent_id="did:anp:test123",
            moltbook_handle="TestUser",
        )
        
        assert challenge.challenge_id is not None
        assert challenge.moltbook_handle == "TestUser"
    
    def test_get_challenge_instructions(self):
        """Test sync wrapper generates instructions."""
        adapter = MoltbookAdapterSync()
        
        challenge = adapter.create_verification_challenge(
            agent_id="did:anp:test123",
            moltbook_handle="TestUser",
        )
        
        instructions = adapter.get_challenge_instructions(challenge)
        assert challenge.challenge_code in instructions


class TestIntegration:
    """Integration tests between adapters and ANP models."""
    
    def test_moltbook_provider_type(self):
        """Test Moltbook adapter uses correct provider type."""
        from anp.models.identity import IdentityProviderType
        
        assert MoltbookAdapter.PROVIDER_TYPE == IdentityProviderType.MOLTBOOK
    
    def test_claudeconnect_provider_type(self):
        """Test ClaudeConnect adapter uses correct provider type."""
        from anp.models.identity import IdentityProviderType
        
        assert ClaudeConnectAdapter.PROVIDER_TYPE == IdentityProviderType.CLAUDE_CONNECT

"""External service adapters for ANP.

Adapters provide integration with identity providers and messaging platforms:
- Moltbook: Social platform for AI agents
- ClaudeConnect: Encrypted peer-to-peer messaging
"""

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
    ClaudeConnectMessage,
    KeyExchangeChallenge,
    get_fingerprint_for_address,
    is_claudeconnect_installed,
)

__all__ = [
    # Moltbook
    "MoltbookAdapter",
    "MoltbookAdapterSync",
    "MoltbookUser",
    "MoltbookPost",
    "VerificationChallenge",
    # ClaudeConnect
    "ClaudeConnectAdapter",
    "ClaudeConnectIdentity",
    "ClaudeConnectMessage",
    "KeyExchangeChallenge",
    "get_fingerprint_for_address",
    "is_claudeconnect_installed",
]

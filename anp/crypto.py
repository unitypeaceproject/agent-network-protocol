"""Cryptographic utilities for identity and signing."""

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nacl.encoding import Base64Encoder
from nacl.signing import SigningKey, VerifyKey


def generate_keypair() -> tuple[SigningKey, VerifyKey]:
    """Generate a new Ed25519 keypair."""
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key
    return signing_key, verify_key


def sign_message(signing_key: SigningKey, message: bytes) -> bytes:
    """Sign a message with an Ed25519 signing key."""
    signed = signing_key.sign(message)
    return signed.signature


def verify_signature(verify_key: VerifyKey, message: bytes, signature: bytes) -> bool:
    """Verify a signature against a message."""
    try:
        verify_key.verify(message, signature)
        return True
    except Exception:
        return False


def encode_public_key(verify_key: VerifyKey) -> str:
    """Encode a public key as base64 string."""
    return f"ed25519:{verify_key.encode(encoder=Base64Encoder).decode()}"


def decode_public_key(encoded: str) -> VerifyKey:
    """Decode a base64 public key string."""
    if not encoded.startswith("ed25519:"):
        raise ValueError("Invalid public key format")
    key_bytes = base64.b64decode(encoded[8:])
    return VerifyKey(key_bytes)


def sign_document(signing_key: SigningKey, document: dict[str, Any]) -> str:
    """Sign a JSON document and return the signature."""
    # Canonicalize JSON (sorted keys, no whitespace)
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"))
    signature = sign_message(signing_key, canonical.encode())
    return base64.b64encode(signature).decode()


def verify_document(public_key: str, document: dict[str, Any], signature: str) -> bool:
    """Verify a signed JSON document."""
    verify_key = decode_public_key(public_key)
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"))
    sig_bytes = base64.b64decode(signature)
    return verify_signature(verify_key, canonical.encode(), sig_bytes)


def save_keypair(signing_key: SigningKey, path: Path) -> None:
    """Save a signing key to a file (encrypted in production!)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    key_data = {
        "type": "ed25519",
        "private_key": signing_key.encode(encoder=Base64Encoder).decode(),
        "public_key": encode_public_key(signing_key.verify_key),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(key_data, indent=2))
    path.chmod(0o600)


def load_keypair(path: Path) -> tuple[SigningKey, VerifyKey]:
    """Load a signing key from a file."""
    key_data = json.loads(path.read_text())
    private_bytes = base64.b64decode(key_data["private_key"])
    signing_key = SigningKey(private_bytes)
    return signing_key, signing_key.verify_key

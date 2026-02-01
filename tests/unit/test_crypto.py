"""Tests for cryptographic utilities."""

import pytest
from anp.crypto import (
    generate_keypair,
    sign_message,
    verify_signature,
    encode_public_key,
    decode_public_key,
    sign_document,
    verify_document,
)


def test_generate_keypair():
    """Test keypair generation."""
    signing_key, verify_key = generate_keypair()
    assert signing_key is not None
    assert verify_key is not None


def test_sign_and_verify_message():
    """Test message signing and verification."""
    signing_key, verify_key = generate_keypair()
    message = b"Hello, ANP!"
    
    signature = sign_message(signing_key, message)
    assert verify_signature(verify_key, message, signature)


def test_verify_wrong_message_fails():
    """Test that verification fails for wrong message."""
    signing_key, verify_key = generate_keypair()
    message = b"Hello, ANP!"
    wrong_message = b"Wrong message"
    
    signature = sign_message(signing_key, message)
    assert not verify_signature(verify_key, wrong_message, signature)


def test_encode_decode_public_key():
    """Test public key encoding/decoding."""
    _, verify_key = generate_keypair()
    
    encoded = encode_public_key(verify_key)
    assert encoded.startswith("ed25519:")
    
    decoded = decode_public_key(encoded)
    assert decoded.encode() == verify_key.encode()


def test_sign_and_verify_document():
    """Test document signing and verification."""
    signing_key, verify_key = generate_keypair()
    public_key = encode_public_key(verify_key)
    
    document = {
        "name": "TestAgent",
        "capabilities": ["testing"],
    }
    
    signature = sign_document(signing_key, document)
    assert verify_document(public_key, document, signature)


def test_verify_tampered_document_fails():
    """Test that verification fails for tampered documents."""
    signing_key, verify_key = generate_keypair()
    public_key = encode_public_key(verify_key)
    
    document = {"name": "TestAgent"}
    signature = sign_document(signing_key, document)
    
    tampered = {"name": "EvilAgent"}
    assert not verify_document(public_key, tampered, signature)

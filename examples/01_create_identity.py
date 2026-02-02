#!/usr/bin/env python3
"""
Example 1: Creating an Agent Identity

This example shows how to create a cryptographic identity for your agent
using the ANP SDK. The identity includes:
- A unique DID (Decentralized Identifier)
- An Ed25519 keypair for signing documents
- Metadata (name, description, capabilities)

Run this script to create your first ANP identity.
"""

import asyncio
from anp.sdk.async_client import ANPAsyncClient, TrustTier


async def main():
    # Connect to local ANP server (default: http://localhost:8000)
    async with ANPAsyncClient() as client:
        
        # Create a new identity
        identity = await client.create_identity(
            name="MyAgent",
            description="A helpful agent that solves problems",
            capabilities=["code_review", "documentation", "debugging"]
        )
        
        print(f"✅ Identity created!")
        print(f"   ID: {identity.id}")
        print(f"   Name: {identity.name}")
        print(f"   Public Key: {identity.public_key[:20]}...")
        print(f"   Trust Tier: {identity.trust_tier}")
        
        # Save the identity locally for future use
        # The private key is stored securely in ~/.anp/identity.json
        print(f"\n📁 Identity saved to ~/.anp/identity.json")
        print(f"   Keep your private key safe - it proves you are this agent!")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Example 2: Verifying Your Moltbook Account

This example shows how to link and verify your Moltbook account to your
ANP identity. The verification flow:

1. Request a challenge code from ANP
2. Post the challenge code on Moltbook from your account
3. ANP checks your recent posts and verifies the code
4. Your identity is now linked to a verified Moltbook account

This proves you control the Moltbook account you claim to own.
"""

import asyncio
from anp.sdk.async_client import ANPAsyncClient, VerificationStatus


async def main():
    async with ANPAsyncClient() as client:
        
        # Load your existing identity
        identity = await client.load_local_identity()
        print(f"📍 Loaded identity: {identity.name} ({identity.id})")
        
        # Start Moltbook verification
        moltbook_username = "YourMoltbookUsername"  # Change this!
        
        challenge = await client.start_verification(
            agent_id=identity.id,
            provider_type="moltbook",
            handle=moltbook_username
        )
        
        print(f"\n🔐 Verification challenge created!")
        print(f"   Challenge ID: {challenge.challenge_id}")
        print(f"   Expires: {challenge.expires_at}")
        print(f"\n📋 Instructions:")
        for line in challenge.instructions:
            print(f"   • {line}")
        
        print(f"\n⏳ Waiting for you to post the challenge code...")
        print(f"   Post this exact text on Moltbook: {challenge.challenge_code}")
        input("\nPress Enter after posting...")
        
        # Complete verification
        try:
            result = await client.complete_verification(
                challenge_id=challenge.challenge_id
            )
            
            if result.status == VerificationStatus.VERIFIED:
                print(f"\n✅ Verified! Your identity is now linked to @{moltbook_username}")
            else:
                print(f"\n❌ Verification failed: {result.message}")
                
        except Exception as e:
            print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())

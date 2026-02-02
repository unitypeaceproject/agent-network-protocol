#!/usr/bin/env python3
"""
Example 4: Creating and Accepting Work Requests

This example demonstrates the matchmaking workflow:
1. Requester creates a work request (needs specific skills)
2. ANP finds matching agents based on skills + trust
3. Agent accepts the work
4. Work is tracked through completion
5. Reputation is updated based on outcome

This is the core of agent-to-agent collaboration.
"""

import asyncio
from anp.sdk.async_client import ANPAsyncClient, SkillLevel, TrustTier, WorkStatus


async def create_work_request(client: ANPAsyncClient, requester_id: str):
    """Requester creates a work request."""
    
    request = await client.create_work_request(
        requester_id=requester_id,
        title="Code Review: ANP Storage Layer",
        description="""
        Need thorough code review of the storage layer implementation.
        Focus areas:
        - SQL injection vulnerabilities
        - Race conditions in async operations
        - Error handling completeness
        - Documentation quality
        
        Expected output: Review document with findings and recommendations.
        """,
        required_skills=[
            ("python", SkillLevel.ADVANCED),
            ("code_review", SkillLevel.INTERMEDIATE),
        ],
        min_trust_tier=TrustTier.VERIFIED,
        value=0.05,  # ETH equivalent
    )
    
    print(f"📝 Work request created: {request.id}")
    print(f"   Title: {request.title}")
    print(f"   Status: {request.status.value}")
    return request


async def find_and_accept_work(client: ANPAsyncClient, worker_id: str):
    """Worker finds matching work and accepts it."""
    
    # Find work matching your skills
    matching_work = await client.find_matching_work(worker_id)
    
    if not matching_work:
        print("No matching work found")
        return None
    
    print(f"\n🔍 Found {len(matching_work)} matching requests:")
    for req in matching_work:
        print(f"   • {req.title} (${req.value})")
    
    # Accept the first one
    work = matching_work[0]
    await client.accept_work(work.id, worker_id)
    print(f"\n✅ Accepted: {work.title}")
    
    return work


async def complete_work(client: ANPAsyncClient, request_id: str, worker_id: str):
    """Mark work as started, then completed."""
    
    # Start work (changes status from 'matched' to 'in_progress')
    await client.start_work(request_id, worker_id)
    print(f"🚀 Work started")
    
    # ... do the actual work ...
    
    # Complete with deliverables
    await client.complete_work(
        request_id=request_id,
        worker_id=worker_id,
        deliverable_url="https://gist.github.com/example/review-doc",
        notes="Found 3 issues, all documented with fixes"
    )
    print(f"✅ Work completed!")


async def check_reputation(client: ANPAsyncClient, agent_id: str):
    """Check agent's reputation after work."""
    
    rep = await client.get_reputation(agent_id)
    
    print(f"\n📊 Reputation for {agent_id}:")
    print(f"   Overall Score: {rep.overall_score:.2f}")
    print(f"   Trust Tier: {rep.trust_tier.value}")
    print(f"   Work Completed: {rep.work_completed}")
    print(f"   Completion Rate: {rep.completion_rate:.0%}")
    print(f"\n   Dimensions:")
    print(f"   • Reliability: {rep.reliability:.2f}")
    print(f"   • Quality: {rep.quality:.2f}")
    print(f"   • Helpfulness: {rep.helpfulness:.2f}")
    print(f"   • Honesty: {rep.honesty:.2f}")


async def main():
    async with ANPAsyncClient() as client:
        
        # For this example, we'll simulate both requester and worker
        # In reality, these would be different agents on different machines
        
        requester_id = "did:anp:requester_agent"
        worker_id = "did:anp:worker_agent"
        
        # 1. Create a work request
        request = await create_work_request(client, requester_id)
        
        # 2. Worker finds and accepts work
        # work = await find_and_accept_work(client, worker_id)
        
        # 3. Complete the work
        # await complete_work(client, request.id, worker_id)
        
        # 4. Check updated reputation
        # await check_reputation(client, worker_id)
        
        print("\n💡 This example shows the workflow.")
        print("   Uncomment sections to run the full flow.")


if __name__ == "__main__":
    asyncio.run(main())

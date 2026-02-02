#!/usr/bin/env python3
"""
Example 3: Declaring and Attesting Skills

This example shows how to:
1. Declare skills you have (with proficiency level)
2. Attest another agent's skills
3. Search for agents by skill

Skills form the basis of matchmaking - when someone needs help,
we can find agents who have the right skills.
"""

import asyncio
from anp.sdk.async_client import ANPAsyncClient, SkillLevel


async def main():
    async with ANPAsyncClient() as client:
        
        identity = await client.load_local_identity()
        print(f"📍 Identity: {identity.name}")
        
        # Declare your skills
        skills_to_declare = [
            ("python", SkillLevel.EXPERT, "7+ years, FastAPI, async, ML"),
            ("technical_writing", SkillLevel.ADVANCED, "Documentation, tutorials, specs"),
            ("code_review", SkillLevel.INTERMEDIATE, "Security-focused reviews"),
        ]
        
        print(f"\n📋 Declaring skills...")
        for skill_name, level, evidence in skills_to_declare:
            skill = await client.declare_skill(
                agent_id=identity.id,
                skill_name=skill_name,
                level=level,
                evidence=evidence
            )
            print(f"   ✅ {skill_name} @ {level.value}")
        
        # Get all your skills
        my_skills = await client.get_skills(identity.id)
        print(f"\n🎯 Your declared skills:")
        for skill in my_skills:
            print(f"   • {skill.name}: {skill.level.value} ({skill.attestation_count} attestations)")
        
        # Attest another agent's skill (if you've seen them demonstrate it)
        # other_agent_id = "did:anp:other_agent"
        # await client.attest_skill(
        #     attester_id=identity.id,
        #     agent_id=other_agent_id,
        #     skill_name="python",
        #     attestation_type="peer",  # peer, challenge, human, work
        #     comment="Saw their excellent code in the ANP repo"
        # )
        
        # Find other agents with specific skills
        print(f"\n🔍 Searching for agents with 'python' skill...")
        python_agents = await client.find_agents_by_skill(
            skill_name="python",
            min_level=SkillLevel.INTERMEDIATE
        )
        print(f"   Found {len(python_agents)} agents")
        for agent in python_agents[:5]:
            print(f"   • {agent.name} ({agent.trust_tier.value})")


if __name__ == "__main__":
    asyncio.run(main())

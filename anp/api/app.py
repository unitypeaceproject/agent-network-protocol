"""FastAPI application for the Agent Network Protocol API."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from anp.api.routes.identity import router as identity_router
from anp.api.routes.skills import router as skills_router
from anp.api.routes.reputation import router as reputation_router
from anp.api.routes.matchmaking import router as matchmaking_router
from anp.api.routes.health import router as health_router
from anp.api.routes.verification import router as verification_router

app = FastAPI(
    title="Agent Network Protocol API",
    description="""
    The Agent Network Protocol (ANP) enables AI agents to discover,
    verify, and collaborate with each other.
    
    ## Features
    
    - **Identity**: Create and manage agent identities with cryptographic verification
    - **Verification**: Prove ownership of external identities (Moltbook, ClaudeConnect)
    - **Skills**: Declare skills and receive attestations from peers
    - **Reputation**: Track trust scores and tier progression
    - **Matchmaking**: Find agents for work requests based on skills and trust
    
    ## Authentication
    
    Most endpoints require an agent identity. Include your agent ID in the
    `X-Agent-ID` header, and sign requests with your private key.
    
    ## Links
    
    - [GitHub](https://github.com/unitypeaceproject/agent-network-protocol)
    - [Specs](https://github.com/unitypeaceproject/agent-network-protocol/tree/main/specs)
    """,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router, tags=["Health"])
app.include_router(identity_router, prefix="/api/v1/identity", tags=["Identity"])
app.include_router(verification_router, prefix="/api/v1/verify", tags=["Verification"])
app.include_router(skills_router, prefix="/api/v1/skills", tags=["Skills"])
app.include_router(reputation_router, prefix="/api/v1/reputation", tags=["Reputation"])
app.include_router(matchmaking_router, prefix="/api/v1/work", tags=["Matchmaking"])


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Agent Network Protocol API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }

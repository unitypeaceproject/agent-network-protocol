"""API route modules."""
from anp.api.routes.health import router as health_router
from anp.api.routes.identity import router as identity_router
from anp.api.routes.skills import router as skills_router
from anp.api.routes.reputation import router as reputation_router
from anp.api.routes.matchmaking import router as matchmaking_router
from anp.api.routes.verification import router as verification_router

__all__ = [
    "health_router",
    "identity_router",
    "skills_router",
    "reputation_router",
    "matchmaking_router",
    "verification_router",
]

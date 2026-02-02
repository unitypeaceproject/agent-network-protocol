"""Health check routes."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.1.0",
    }


@router.get("/health/ready")
async def readiness_check():
    """Readiness check for load balancers."""
    # TODO: Add database connectivity check
    return {"ready": True}


@router.get("/health/live")
async def liveness_check():
    """Liveness check for container orchestration."""
    return {"live": True}

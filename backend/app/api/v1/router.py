"""API v1 Router aggregator.

Collects and mounts all modular sub-routers under the /api/v1 prefix.
"""

from fastapi import APIRouter
from app.api.v1.endpoints import health, auth, teams, scores, jobs

api_router = APIRouter()

# Core & Health
api_router.include_router(health.router, tags=["Health"])

# Authentication & Current User
api_router.include_router(auth.router, tags=["Auth"])

# Team & Repository Management
api_router.include_router(teams.router, tags=["Teams"])

# Scores, Evidence & Alerts
api_router.include_router(scores.router, tags=["Scores & Alerts"])

# Jobs & Background Sync
api_router.include_router(jobs.router, tags=["Jobs"])

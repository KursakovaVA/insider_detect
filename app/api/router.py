from fastapi import APIRouter

from app.routers import alerts, events, health, ingest, profiles, rules

router = APIRouter()
router.include_router(health.router, tags=["system"])
router.include_router(ingest.router, tags=["ingest"])
router.include_router(events.router, tags=["events"])
router.include_router(profiles.router, tags=["profiles"])
router.include_router(alerts.router, tags=["alerts"])
router.include_router(rules.router, tags=["rules"])

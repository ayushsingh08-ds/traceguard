from fastapi import APIRouter

from app.api.v1.endpoints import alerts, analytics, auth, incidents, rca

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["Alert Ingestion"])
api_router.include_router(incidents.router, prefix="/incidents", tags=["Incidents"])
api_router.include_router(rca.router, prefix="/rca", tags=["RCA Diagnostics"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])

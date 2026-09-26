"""
TestPilot — FastAPI application entry point.

Run locally:
    uvicorn backend.main:app --reload

Or from the project root:
    python -m uvicorn backend.main:app --reload
"""

from fastapi import FastAPI

from backend.api.routes import router

app = FastAPI(
    title="TestPilot API",
    description="Mutation-testing pipeline with AI-powered test gap analysis.",
    version="0.1.0",
)

app.include_router(router)

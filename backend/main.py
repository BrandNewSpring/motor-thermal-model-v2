"""Motor Thermal Model v2 — FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import calibration, export, files, prediction, profiles

app = FastAPI(
    title="Motor Thermal Model v2",
    version="0.1.0",
    description="3-node lumped-parameter thermal model for electric motors",
)

# CORS — allow Vite dev server during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(profiles.router, prefix="/api/profiles", tags=["profiles"])
app.include_router(calibration.router, prefix="/api/calibration", tags=["calibration"])
app.include_router(prediction.router, prefix="/api/prediction", tags=["prediction"])
app.include_router(export.router, prefix="/api/export", tags=["export"])


@app.get("/api/health")
async def health_check() -> dict:
    return {"status": "ok"}

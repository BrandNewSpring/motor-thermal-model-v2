"""Motor profile CRUD router."""

from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from schemas.motor import (
    GeometryPreview,
    MaterialProps,
    MotorGeometry,
    MotorProfile,
    MotorProfileCreate,
    MotorProfileSummary,
    MotorProfileUpdate,
)
from storage.profiles import (
    copy_profile,
    create_profile,
    delete_profile,
    get_profile,
    list_all_profiles,
    update_profile,
)

router = APIRouter()


@router.get("", response_model=list[MotorProfileSummary])
async def list_profiles() -> list[MotorProfileSummary]:
    """Return all saved motor profiles (summary view)."""
    profiles = list_all_profiles()
    return [
        MotorProfileSummary(
            id=p.id,
            name=p.name,
            created_at=p.created_at,
            updated_at=p.updated_at,
            iron_loss_mode=p.iron_loss_mode,
        )
        for p in profiles
    ]


@router.post("", response_model=MotorProfile, status_code=201)
async def create_new_profile(body: MotorProfileCreate) -> MotorProfile:
    """Create a new motor profile with computed geometry."""
    return create_profile(body)


@router.get("/{profile_id}", response_model=MotorProfile)
async def get_single_profile(profile_id: str) -> MotorProfile:
    """Return a single motor profile by id."""
    profile = get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return profile


@router.put("/{profile_id}", response_model=MotorProfile)
async def update_existing_profile(profile_id: str, body: MotorProfileUpdate) -> MotorProfile:
    """Update an existing motor profile (partial update)."""
    profile = update_profile(profile_id, body)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return profile


@router.delete("/{profile_id}", status_code=204)
async def delete_existing_profile(profile_id: str) -> None:
    """Delete a motor profile."""
    if not delete_profile(profile_id):
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")


@router.post("/{profile_id}/copy", response_model=MotorProfile, status_code=201)
async def copy_existing_profile(profile_id: str) -> MotorProfile:
    """Create a copy of an existing profile."""
    profile = copy_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return profile


class ComputeGeometryRequest(BaseModel):
    """Request body for compute-geometry preview."""

    geometry: MotorGeometry
    material: MaterialProps = Field(default_factory=MaterialProps)


@router.post("/compute-geometry", response_model=GeometryPreview)
async def compute_geometry(body: ComputeGeometryRequest) -> GeometryPreview:
    """Preview computed geometry without saving a profile."""
    from storage.profiles import _compute_preview

    return _compute_preview(body.geometry.model_dump(), body.material.model_dump())

"""JSON-based motor profile storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.motor_geometry import compute_initial_resistances, compute_thermal_masses
from schemas.calibration import CalibResult
from schemas.motor import (
    GeometryPreview,
    MotorProfile,
    MotorProfileCreate,
    MotorProfileUpdate,
)

DEFAULT_DATA_DIR = Path.home() / ".mtm_v2"
PROFILES_DIR = DEFAULT_DATA_DIR / "profiles"


def _ensure_dir() -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def _compute_preview(geo_dict: dict, mat_dict: dict | None = None) -> GeometryPreview:
    """Compute geometry preview from raw geometry/material dicts."""
    from schemas.motor import MaterialProps, MotorGeometry

    geo = MotorGeometry(**geo_dict) if not isinstance(geo_dict, MotorGeometry) else geo_dict
    mat = MaterialProps(**mat_dict) if mat_dict and not isinstance(mat_dict, MaterialProps) else (
        mat_dict or MaterialProps()
    )

    masses = compute_thermal_masses(
        D_motor_mm=geo.D_motor_mm,
        L_motor_mm=geo.L_motor_mm,
        t_housing_mm=geo.t_housing_mm,
        m_motor_g=geo.m_motor_g,
        m_housing_g=geo.m_housing_g,
        L_housing_mm=geo.L_housing_mm,
        f_copper=geo.f_copper,
        c_p_Cu=mat.c_p_Cu,
        c_p_FeSi=mat.c_p_FeSi,
        c_p_Al=mat.c_p_Al,
    )
    res = compute_initial_resistances(
        D_motor_mm=geo.D_motor_mm,
        L_motor_mm=geo.L_motor_mm,
        t_housing_mm=geo.t_housing_mm,
        m_motor_g=geo.m_motor_g,
        m_housing_g=geo.m_housing_g,
        L_housing_mm=geo.L_housing_mm,
        f_copper=geo.f_copper,
        t_mold_mm=geo.t_mold_mm,
        k_mold=mat.k_mold,
    )

    return GeometryPreview(
        C_coil=masses.C_coil,
        C_core=masses.C_core,
        C_housing=masses.C_housing,
        A_interface_m2=masses.A_interface,
        A_housing_m2=masses.A_housing,
        R2_mold_init=res.R2_mold,
        R3_nat_init=res.R3_nat_init,
        tau_coil_s=res.tau_approx,
    )


def _profile_to_dict(profile: MotorProfile) -> dict:
    """Serialize a MotorProfile to a JSON-compatible dict."""
    return json.loads(profile.model_dump_json())


def _dict_to_profile(data: dict) -> MotorProfile:
    """Deserialize a dict into a MotorProfile."""
    return MotorProfile.model_validate(data)


def list_all_profiles() -> list[MotorProfile]:
    """Return all saved profiles."""
    _ensure_dir()
    profiles: list[MotorProfile] = []
    for fp in sorted(PROFILES_DIR.glob("*.json")):
        try:
            profiles.append(_dict_to_profile(json.loads(fp.read_text(encoding="utf-8"))))
        except Exception:
            # Skip corrupted files
            continue
    return profiles


def get_profile(profile_id: str) -> Optional[MotorProfile]:
    """Return a single profile by id, or None."""
    fp = PROFILES_DIR / f"{profile_id}.json"
    if fp.exists():
        return _dict_to_profile(json.loads(fp.read_text(encoding="utf-8")))
    return None


def save_profile(profile: MotorProfile) -> MotorProfile:
    """Persist a profile to JSON."""
    _ensure_dir()
    fp = PROFILES_DIR / f"{profile.id}.json"
    fp.write_text(
        json.dumps(_profile_to_dict(profile), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return profile


def create_profile(data: MotorProfileCreate) -> MotorProfile:
    """Create a new profile with auto-generated id and computed geometry."""
    import uuid

    now = datetime.now(timezone.utc)
    preview = _compute_preview(data.geometry.model_dump(), data.material.model_dump())

    profile = MotorProfile(
        id=str(uuid.uuid4()),
        name=data.name,
        geometry=data.geometry,
        material=data.material,
        coil=data.coil,
        iron_loss_mode=data.iron_loss_mode,
        simple_iron_loss=data.simple_iron_loss,
        geometry_preview=preview,
        created_at=now,
        updated_at=now,
    )
    return save_profile(profile)


def update_profile(profile_id: str, data: MotorProfileUpdate) -> Optional[MotorProfile]:
    """Update an existing profile with partial data. Returns None if not found."""
    existing = get_profile(profile_id)
    if existing is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    now = datetime.now(timezone.utc)

    # Apply updates
    for key, value in update_data.items():
        setattr(existing, key, value)

    existing.updated_at = now

    # Recompute geometry if geometry or material changed
    if "geometry" in update_data or "material" in update_data:
        existing.geometry_preview = _compute_preview(
            existing.geometry.model_dump(),
            existing.material.model_dump(),
        )

    return save_profile(existing)


def delete_profile(profile_id: str) -> bool:
    """Delete a profile file. Returns True if deleted."""
    fp = PROFILES_DIR / f"{profile_id}.json"
    if fp.exists():
        fp.unlink()
        return True
    return False


def copy_profile(profile_id: str) -> Optional[MotorProfile]:
    """Create a copy of an existing profile with a new id."""
    import uuid

    existing = get_profile(profile_id)
    if existing is None:
        return None

    now = datetime.now(timezone.utc)
    new_profile = existing.model_copy(update={
        "id": str(uuid.uuid4()),
        "name": f"{existing.name} (copy)",
        "created_at": now,
        "updated_at": now,
    })
    return save_profile(new_profile)


def update_calib_result(profile_id: str, result: CalibResult) -> Optional[MotorProfile]:
    """Attach a calibration result to a profile."""
    existing = get_profile(profile_id)
    if existing is None:
        return None
    # Store calib result in profile metadata — we use a custom field
    profile_dict = json.loads(existing.model_dump_json())
    profile_dict["calib_result"] = json.loads(result.model_dump_json())
    profile_dict["updated_at"] = datetime.now(timezone.utc).isoformat()

    fp = PROFILES_DIR / f"{profile_id}.json"
    fp.write_text(
        json.dumps(profile_dict, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return _dict_to_profile(profile_dict)

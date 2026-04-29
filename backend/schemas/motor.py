"""Motor profile, geometry, and material Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Material properties
# ---------------------------------------------------------------------------
class MaterialProps(BaseModel):
    """Material thermal properties (SPEC Section 1.1)."""

    c_p_Cu: float = Field(385.0, description="Copper specific heat [J/(kg*K)]")
    c_p_FeSi: float = Field(490.0, description="Silicon steel specific heat [J/(kg*K)]")
    c_p_Al: float = Field(900.0, description="Aluminum specific heat [J/(kg*K)]")
    k_mold: float = Field(0.3, description="Mold thermal conductivity [W/(m*K)]")
    beta_iron: float = Field(0.002, description="Iron loss temperature correction [1/K]")


# ---------------------------------------------------------------------------
# Motor geometry
# ---------------------------------------------------------------------------
class MotorGeometry(BaseModel):
    """Motor geometry inputs (SPEC Section 1.1 / PRD Section 3)."""

    D_motor_mm: float = Field(106.0, gt=0, description="Stator outer diameter [mm]")
    L_motor_mm: float = Field(48.85, gt=0, description="Stator axial length [mm]")
    m_motor_g: float = Field(..., gt=0, description="Total motor mass incl. housing [g]")
    t_housing_mm: float = Field(10.5, gt=0, description="Housing wall thickness [mm]")
    L_housing_mm: Optional[float] = Field(
        None, description="Housing axial length [mm] (defaults to L_motor_mm)"
    )
    m_housing_g: float = Field(..., gt=0, description="Housing mass [g]")
    t_mold_mm: float = Field(0.5, ge=0, description="Mold interface thickness [mm]")
    f_copper: float = Field(0.35, ge=0, le=1, description="Copper fill fraction of stator mass")


# ---------------------------------------------------------------------------
# Coil parameters
# ---------------------------------------------------------------------------
class CoilParams(BaseModel):
    """Coil electrical parameters (SPEC Section 1.1)."""

    R0: float = Field(0.5, gt=0, description="Reference resistance @ T0 [Ohm, 1-phase]")
    T0: float = Field(20.0, description="Reference temperature [degC]")
    alpha: float = Field(0.00393, gt=0, description="Resistance temperature coefficient [1/degC]")
    n_phases: int = Field(3, ge=1, description="Number of phases")


# ---------------------------------------------------------------------------
# Iron loss models
# ---------------------------------------------------------------------------
class SimpleIronLoss(BaseModel):
    """Parameters for the simple (power-law) iron-loss model."""

    I_max: float = Field(10.0, gt=0, description="Reference max current [A]")
    RPM_max: float = Field(5000.0, gt=0, description="Reference max RPM")
    alpha_iron: float = Field(2.0, gt=0, description="RPM exponent")


class IronLossMode(str):
    """Iron loss computation mode."""

    SIMPLE = "simple"
    MAP = "map"


# ---------------------------------------------------------------------------
# Geometry preview result
# ---------------------------------------------------------------------------
class GeometryPreview(BaseModel):
    """Computed geometry results (SPEC Section 2.3)."""

    C_coil: float = Field(..., description="Coil thermal capacitance [J/degC]")
    C_core: float = Field(..., description="Core thermal capacitance [J/degC]")
    C_housing: float = Field(..., description="Housing thermal capacitance [J/degC]")
    A_interface_m2: float = Field(..., description="Stator outer surface area [m^2]")
    A_housing_m2: float = Field(..., description="Housing outer surface area [m^2]")
    R2_mold_init: float = Field(..., description="Initial R2 via mold [degC/W]")
    R3_nat_init: float = Field(..., description="R3 at RPM=0 [degC/W]")
    tau_coil_s: float = Field(..., description="Approximate thermal time constant [s]")


# ---------------------------------------------------------------------------
# Motor profile CRUD schemas
# ---------------------------------------------------------------------------
class MotorProfileBase(BaseModel):
    """Base fields for creating/updating a motor profile."""

    name: str = Field(..., min_length=1, max_length=200, description="Profile name")
    geometry: MotorGeometry
    material: MaterialProps = Field(default_factory=MaterialProps)
    coil: CoilParams = Field(default_factory=CoilParams)
    iron_loss_mode: str = Field("simple", description="Iron loss mode: 'simple' or 'map'")
    simple_iron_loss: Optional[SimpleIronLoss] = Field(
        None, description="Simple iron loss params (required if mode='simple')"
    )


class MotorProfileCreate(MotorProfileBase):
    """Request body for creating a profile."""

    pass


class MotorProfileUpdate(BaseModel):
    """Partial update for a profile.  Only supplied fields are changed."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    geometry: Optional[MotorGeometry] = None
    material: Optional[MaterialProps] = None
    coil: Optional[CoilParams] = None
    iron_loss_mode: Optional[str] = None
    simple_iron_loss: Optional[SimpleIronLoss] = None


class MotorProfileSummary(BaseModel):
    """Lightweight profile representation for list views."""

    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    iron_loss_mode: str = "simple"


class MotorProfile(MotorProfileBase):
    """Full motor profile with computed geometry and metadata."""

    id: str
    created_at: datetime
    updated_at: datetime
    geometry_preview: Optional[GeometryPreview] = None

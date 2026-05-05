"""Test data and loss map Pydantic schemas."""

from __future__ import annotations

from typing import List, Optional, Tuple

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# File upload response
# ---------------------------------------------------------------------------
class FileUploadResponse(BaseModel):
    """Response after a successful file upload."""

    file_id: str = Field(..., description="Generated file UUID")
    filename: str = Field(..., description="Original filename")
    rows: int = Field(..., description="Number of data rows")
    columns: List[str] = Field(default_factory=list, description="Detected column names")
    preview: List[dict] = Field(default_factory=list, description="First 5 rows as dicts")


class FileColumnsResponse(BaseModel):
    """Column list with sample data for a uploaded file."""

    columns: List[str] = Field(default_factory=list, description="All column names")
    sample: List[dict] = Field(default_factory=list, description="First 5 rows")


# ---------------------------------------------------------------------------
# Column mapping validation
# ---------------------------------------------------------------------------
class ColumnMappingRequest(BaseModel):
    """Request body to validate a column mapping."""

    time: Optional[str] = Field(None, description="Column name for time [s]")
    rpm: Optional[str] = Field(None, description="Column name for RPM")
    I_phase: str = Field(..., description="Column name for phase current [A]")
    T_amb: str = Field(..., description="Column name for ambient temp [degC]")
    T_coil: str = Field(..., description="Column name for coil temp [degC]")
    torque: Optional[str] = Field(None, description="Column name for torque [Nm]")


class ColumnMappingResponse(BaseModel):
    """Response after validating column mapping."""

    mapped_rows: int = Field(..., description="Number of rows with valid mapping")
    summary: dict = Field(default_factory=dict, description="Per-column stats")


# ---------------------------------------------------------------------------
# Prediction schemas
# ---------------------------------------------------------------------------
class SteadyStateRequest(BaseModel):
    """Request for a single operating-point steady-state prediction."""

    profile_id: str = Field(..., description="Motor profile UUID")
    I_phase: float = Field(..., gt=0, description="Phase current [A]")
    T_amb: float = Field(25.0, description="Ambient temperature [degC]")
    rpm: float = Field(3000.0, ge=0, description="Rotor speed [RPM]")
    # Optional calibration overrides (if not using saved calib_result)
    R1: Optional[float] = None
    R2: Optional[float] = None
    h_nat: Optional[float] = None
    h_rpm: Optional[float] = None


class SteadyStateResult(BaseModel):
    """Steady-state temperature prediction at a single operating point."""

    T_coil_ss: float = Field(..., description="Steady-state coil temperature [degC]")
    T_core_ss: float = Field(..., description="Steady-state core temperature [degC]")
    T_housing_ss: float = Field(..., description="Steady-state housing temperature [degC]")
    Q_copper: float = Field(..., description="Copper loss at SS [W]")
    Q_iron: float = Field(..., description="Iron loss at SS [W]")
    R3_at_rpm: float = Field(..., description="Housing-to-ambient resistance [degC/W]")


class GridPredictionRequest(BaseModel):
    """Request for an I x RPM grid prediction (heatmap data)."""

    profile_id: str = Field(..., description="Motor profile UUID")
    I_range: List[float] = Field(
        ..., min_length=2, max_length=2, description="[I_min, I_max] in A"
    )
    RPM_range: List[float] = Field(
        ..., min_length=2, max_length=2, description="[RPM_min, RPM_max]"
    )
    T_amb: float = Field(25.0, description="Ambient temperature [degC]")
    n_points: int = Field(20, ge=5, le=20, description="Grid resolution per axis (max 20x20)")
    # Optional calibration overrides
    R1: Optional[float] = None
    R2: Optional[float] = None
    h_nat: Optional[float] = None
    h_rpm: Optional[float] = None


class GridPredictionResult(BaseModel):
    """Grid prediction result (2D arrays for heatmap plotting)."""

    grid_I: List[List[float]] = Field(..., description="I values on grid")
    grid_RPM: List[List[float]] = Field(..., description="RPM values on grid")
    grid_T_coil: List[List[float]] = Field(..., description="T_coil_ss on grid")
    grid_T_core: List[List[float]] = Field(..., description="T_core_ss on grid")
    grid_T_housing: List[List[float]] = Field(..., description="T_housing_ss on grid")


# ---------------------------------------------------------------------------
# File condition summary (per-file test condition metadata)
# ---------------------------------------------------------------------------
class FileConditionSummary(BaseModel):
    """Summary of test conditions extracted from a data file."""

    file_id: str = Field(..., description="File UUID")
    filename: str = Field(..., description="Original filename")
    rows: int = Field(..., description="Total data rows")
    I_range: Tuple[Optional[float], Optional[float]] = Field(
        ..., description="(min, max) phase current [A]"
    )
    rpm_range: Tuple[Optional[float], Optional[float]] = Field(
        ..., description="(min, max) rotor speed [RPM]"
    )
    T_amb_mean: Optional[float] = Field(None, description="Mean ambient temperature [degC]")
    T_coil_range: Tuple[Optional[float], Optional[float]] = Field(
        ..., description="(min, max) coil temperature [degC]"
    )
    duration_s: Optional[float] = Field(None, description="Time span if time column exists [s]")


# ---------------------------------------------------------------------------
# Export schemas
# ---------------------------------------------------------------------------
class ExportRequest(BaseModel):
    """Request body for Excel export."""

    profile_id: str = Field(..., description="Motor profile UUID")
    job_id: Optional[str] = Field(None, description="Calibration job ID (if results exist)")
    include_grid: bool = Field(
        False, description="Include steady-state grid prediction in export"
    )

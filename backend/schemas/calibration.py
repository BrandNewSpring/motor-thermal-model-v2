"""Calibration request and result Pydantic schemas."""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Calibration settings
# ---------------------------------------------------------------------------
# Safe defaults for positive-required fields (used when frontend sends None/0/NaN).
_POSITIVE_DEFAULTS: dict[str, float] = {
    "tail_gamma": 2.0,
    "ss_penalty": 5.0,
    "h_nat_init": 10.0,
    "h_rpm_init": 0.02,
}


def _safe_float(v: object, default: float) -> float:
    """Convert *v* to a positive float, falling back to *default*."""
    if v is None:
        return default
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return default
    if math.isnan(fv) or fv <= 0:
        return default
    return fv


def _safe_optional_float(v: object) -> Optional[float]:
    """Convert *v* to a positive float or None."""
    if v is None:
        return None
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(fv) or fv <= 0:
        return None
    return fv


class CalibSettings(BaseModel):
    """Calibration hyper-parameters (SPEC Section 1.4).

    All positive-required fields are declared Optional so that None/NaN/0
    values from the frontend are accepted.  ``model_post_init`` resolves
    them to safe defaults before any downstream code sees them.
    """

    n_starts: int = Field(3, ge=1, le=20, description="Number of multi-start runs")
    # Declared Optional to accept None/NaN from frontend; resolved in post_init
    tail_gamma: Optional[float] = Field(2.0, description="Tail weight ramp exponent")
    ss_penalty: Optional[float] = Field(5.0, description="Steady-state anchor multiplier")
    normalize_per_file: bool = Field(True, description="Normalize per file")
    R1_init: Optional[float] = Field(None, description="R1 initial guess [degC/W]")
    R2_init: Optional[float] = Field(None, description="R2 initial guess [degC/W]")
    h_nat_init: Optional[float] = Field(10.0, description="h_nat initial guess [W/(m^2*K)]")
    h_rpm_init: Optional[float] = Field(0.02, description="h_rpm initial guess [W/(m^2*K)/sqrt(RPM)]")
    R1_bounds: Optional[Tuple[float, float]] = Field(
        None, description="R1 search bounds (low, high) [degC/W]"
    )
    R2_bounds: Optional[Tuple[float, float]] = Field(
        None, description="R2 search bounds (low, high) [degC/W]"
    )

    def model_post_init(self, __context: object) -> None:
        """Clamp None/NaN/non-positive values to safe defaults."""
        for field_name, default_val in _POSITIVE_DEFAULTS.items():
            current = getattr(self, field_name)
            object.__setattr__(self, field_name, _safe_float(current, default_val))

        # R1/R2 init: treat non-positive and NaN as None
        object.__setattr__(self, "R1_init", _safe_optional_float(self.R1_init))
        object.__setattr__(self, "R2_init", _safe_optional_float(self.R2_init))


# ---------------------------------------------------------------------------
# Calibration request
# ---------------------------------------------------------------------------
class CalibRequest(BaseModel):
    """Request body for starting a calibration run."""

    profile_id: str = Field(..., description="Motor profile UUID")
    data_file_id: Optional[str] = Field(
        None, description="Single test data file UUID (legacy, prefer data_file_ids)"
    )
    data_file_ids: Optional[List[str]] = Field(
        None, description="List of uploaded test data file UUIDs"
    )
    loss_map_file_id: Optional[str] = Field(
        None, description="Uploaded loss map file UUID (for map mode)"
    )
    column_mapping: Optional["ColumnMapping"] = Field(
        None, description="Column mapping applied to all data files"
    )
    settings: CalibSettings = Field(default_factory=CalibSettings)

    def resolved_file_ids(self) -> List[str]:
        """Return a non-empty list of data file IDs, supporting both old and new fields."""
        if self.data_file_ids:
            return self.data_file_ids
        if self.data_file_id:
            return [self.data_file_id]
        raise ValueError("Either data_file_id or data_file_ids must be provided")


# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------
class ColumnMapping(BaseModel):
    """Maps physical quantities to CSV column names."""

    time: Optional[str] = Field(None, description="Column name for time [s]")
    rpm: Optional[str] = Field(None, description="Column name for RPM")
    I_phase: str = Field(..., description="Column name for phase current [A]")
    T_amb: str = Field(..., description="Column name for ambient temp [degC]")
    T_coil: str = Field(..., description="Column name for coil temp [degC]")
    torque: Optional[str] = Field(None, description="Column name for torque [Nm]")


# ---------------------------------------------------------------------------
# Calibration result
# ---------------------------------------------------------------------------
class ThermalParams(BaseModel):
    """Calibrated thermal parameters."""

    R1: float = Field(..., description="Coil-to-core resistance [degC/W]")
    R2: float = Field(..., description="Core-to-housing resistance [degC/W]")
    h_nat: float = Field(..., description="Natural convection coefficient [W/(m^2*K)]")
    h_rpm: float = Field(..., description="RPM forced convection [W/(m^2*K)/sqrt(RPM)]")
    C_coil: float = Field(..., description="Coil thermal capacitance [J/degC]")
    C_core: float = Field(..., description="Core thermal capacitance [J/degC]")
    C_housing: float = Field(..., description="Housing thermal capacitance [J/degC]")
    R2_mold: Optional[float] = Field(None, description="Mold R2 theoretical [degC/W]")


class FileConditions(BaseModel):
    """Representative test conditions extracted from one data file."""

    I_mean: Optional[float] = Field(None, description="Mean phase current [A]")
    T_amb_mean: Optional[float] = Field(None, description="Mean ambient temp [degC]")
    rpm_representative: Optional[float] = Field(None, description="Representative RPM (mean or mode)")


class FileCalibResult(BaseModel):
    """Per-file calibration result with measured vs simulated temperatures."""

    file_id: str = Field(..., description="File UUID (or index-based ID)")
    filename: str = Field(..., description="Original filename")
    conditions: FileConditions = Field(default_factory=FileConditions, description="Extracted test conditions")
    time_array: List[float] = Field(default_factory=list, description="Time axis [s]")
    T_coil_meas: List[float] = Field(default_factory=list, description="Measured coil temps")
    T_coil_sim: List[float] = Field(default_factory=list, description="Simulated coil temps")
    T_core_sim: List[float] = Field(default_factory=list, description="Simulated core temps")
    T_housing_sim: List[float] = Field(default_factory=list, description="Simulated housing temps")


class CalibResult(BaseModel):
    """Full calibration output (SPEC Section 1.4)."""

    params: ThermalParams
    rmse: float = Field(..., description="Root mean square error [degC]")
    r_squared: float = Field(..., description="Coefficient of determination")
    T_coil_sim: List[float] = Field(default_factory=list, description="Simulated coil temps")
    T_core_sim: List[float] = Field(default_factory=list, description="Simulated core temps")
    T_housing_sim: List[float] = Field(default_factory=list, description="Simulated housing temps")
    T_coil_meas: List[float] = Field(default_factory=list, description="Measured coil temps")
    time_array: List[float] = Field(default_factory=list, description="Time axis [s]")
    residuals: List[float] = Field(default_factory=list, description="T_coil_sim - T_coil_meas")
    time_s: float = Field(..., description="Optimization wall-clock time [s]")
    converged: bool = Field(True, description="Whether the optimizer converged")
    loss_history: List[float] = Field(default_factory=list, description="Loss per start")
    per_file_results: List[FileCalibResult] = Field(default_factory=list, description="Per-file breakdown")


# ---------------------------------------------------------------------------
# SSE progress event
# ---------------------------------------------------------------------------
class CalibProgressEvent(BaseModel):
    """SSE progress event schema (SPEC Section 6)."""

    type: str = Field(..., description="Event type: progress, phase, done, error")
    start: Optional[int] = None
    n_starts: Optional[int] = None
    iter: Optional[int] = None
    rmse: Optional[float] = None
    elapsed: Optional[float] = None
    message: Optional[str] = None
    result: Optional[CalibResult] = None

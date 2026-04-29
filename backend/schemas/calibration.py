"""Calibration request and result Pydantic schemas."""

from __future__ import annotations

from typing import List, Optional, Tuple

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Calibration settings
# ---------------------------------------------------------------------------
class CalibSettings(BaseModel):
    """Calibration hyper-parameters (SPEC Section 1.4)."""

    n_starts: int = Field(3, ge=1, le=20, description="Number of multi-start runs")
    tail_gamma: float = Field(2.0, gt=0, description="Tail weight ramp exponent")
    ss_penalty: float = Field(5.0, gt=0, description="Steady-state anchor multiplier")
    normalize_per_file: bool = Field(True, description="Normalize per file")
    R1_init: Optional[float] = Field(None, gt=0, description="R1 initial guess [degC/W]")
    R2_init: Optional[float] = Field(None, gt=0, description="R2 initial guess [degC/W]")
    h_nat_init: float = Field(10.0, gt=0, description="h_nat initial guess [W/(m^2*K)]")
    h_rpm_init: float = Field(0.02, gt=0, description="h_rpm initial guess [W/(m^2*K)/sqrt(RPM)]")
    R1_bounds: Optional[Tuple[float, float]] = Field(
        None, description="R1 search bounds (low, high) [degC/W]"
    )
    R2_bounds: Optional[Tuple[float, float]] = Field(
        None, description="R2 search bounds (low, high) [degC/W]"
    )


# ---------------------------------------------------------------------------
# Calibration request
# ---------------------------------------------------------------------------
class CalibRequest(BaseModel):
    """Request body for starting a calibration run."""

    profile_id: str = Field(..., description="Motor profile UUID")
    data_file_id: str = Field(..., description="Uploaded test data file UUID")
    loss_map_file_id: Optional[str] = Field(
        None, description="Uploaded loss map file UUID (for map mode)"
    )
    settings: CalibSettings = Field(default_factory=CalibSettings)


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


class CalibResult(BaseModel):
    """Full calibration output (SPEC Section 1.4)."""

    params: ThermalParams
    rmse: float = Field(..., description="Root mean square error [degC]")
    r_squared: float = Field(..., description="Coefficient of determination")
    T_coil_sim: List[float] = Field(default_factory=list, description="Simulated coil temps")
    T_core_sim: List[float] = Field(default_factory=list, description="Simulated core temps")
    T_housing_sim: List[float] = Field(default_factory=list, description="Simulated housing temps")
    residuals: List[float] = Field(default_factory=list, description="T_coil_sim - T_coil_meas")
    time_s: float = Field(..., description="Optimization wall-clock time [s]")
    converged: bool = Field(True, description="Whether the optimizer converged")
    loss_history: List[float] = Field(default_factory=list, description="Loss per start")


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

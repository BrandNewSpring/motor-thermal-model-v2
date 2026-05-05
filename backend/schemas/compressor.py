"""Compressor data Pydantic schemas (REQ-COMP-DATA-001).

Request and response models for the compressor thermal model,
including operating points, predictions, calibration parameters,
data upload, and SSE progress events.

Reference: SPEC-COMP-THERMAL-001 REQ-COMP-DATA-001
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Calibration parameters
# ---------------------------------------------------------------------------
class CompressorCalibrationParams(BaseModel):
    """Calibrated thermal parameters for the compressor model.

    These parameters govern heat transfer, volumetric/isentropic
    efficiency, and motor losses in the compressor thermal model.
    """

    UA_0: float = Field(50.0, gt=0, description="Base overall heat transfer coefficient [W/K]")
    UA_1: float = Field(0.1, ge=0, description="RPM-dependent UA correction [W/K/RPM]")
    eta_vol: float = Field(0.85, gt=0, le=1.0, description="Volumetric efficiency [-]")
    eta_s: float = Field(0.75, gt=0, le=1.0, description="Isentropic efficiency [-]")
    R_coil_core: float = Field(0.01, gt=0, description="Coil-to-core thermal resistance [K/W]")
    h_ref: float = Field(500.0, gt=0, description="Reference heat transfer coefficient [W/(m^2*K)]")


# ---------------------------------------------------------------------------
# Operating point (input)
# ---------------------------------------------------------------------------
class CompressorOperatingPoint(BaseModel):
    """Input operating conditions for compressor prediction.

    All pressures in Pa, temperatures in degC, RPM dimensionless.
    """

    RPM: float = Field(..., ge=0, description="Compressor speed [RPM]")
    Ps: float = Field(..., gt=0, description="Suction pressure [Pa]")
    Ts: float = Field(..., description="Suction temperature [degC]")
    Pd: float = Field(..., gt=0, description="Discharge pressure [Pa]")


# ---------------------------------------------------------------------------
# Prediction output
# ---------------------------------------------------------------------------
class CompressorPrediction(BaseModel):
    """Prediction output from the compressor thermal model."""

    Tm: float = Field(..., description="Motor temperature [degC]")
    Td: float = Field(..., description="Discharge temperature [degC]")
    Torque: float = Field(..., description="Compressor torque [Nm]")
    Q_recirc: float = Field(..., ge=0, description="Recirculation heat loss [W]")
    MotorLoss: float = Field(..., ge=0, description="Motor loss [W]")
    hm: float = Field(..., gt=0, description="Motor heat transfer coefficient [W/(m^2*K)]")
    hd: float = Field(..., gt=0, description="Discharge heat transfer coefficient [W/(m^2*K)]")
    mdot: float = Field(..., gt=0, description="Mass flow rate [kg/s]")


# ---------------------------------------------------------------------------
# Prediction request / response
# ---------------------------------------------------------------------------
class CompressorPredictionRequest(BaseModel):
    """Request body for a single compressor operating point prediction."""

    RPM: float = Field(..., ge=0, description="Compressor speed [RPM]")
    Ps: float = Field(..., gt=0, description="Suction pressure [Pa]")
    Ts: float = Field(..., description="Suction temperature [degC]")
    Pd: float = Field(..., gt=0, description="Discharge pressure [Pa]")
    calibration_params: Optional[CompressorCalibrationParams] = Field(
        None, description="Optional calibration parameter overrides"
    )


class CompressorPredictionResponse(BaseModel):
    """Response with prediction results and convergence info."""

    prediction: CompressorPrediction = Field(
        ..., description="Prediction output values"
    )
    converged: bool = Field(True, description="Whether the solver converged")
    iterations: int = Field(0, ge=0, description="Number of solver iterations")


# ---------------------------------------------------------------------------
# Test data schemas
# ---------------------------------------------------------------------------
class CompressorDataPoint(BaseModel):
    """Single test data point with all measured columns.

    Required fields are the minimum for thermal model validation.
    All other fields are optional (may not be present in all test rigs).
    """

    RPM: float = Field(..., ge=0, description="Compressor speed [RPM]")
    Ps: float = Field(..., gt=0, description="Suction pressure [Pa]")
    Ts: float = Field(..., description="Suction temperature [degC]")
    Pd: float = Field(..., gt=0, description="Discharge pressure [Pa]")
    Td: Optional[float] = Field(None, description="Discharge temperature [degC]")
    Tm: Optional[float] = Field(None, description="Motor temperature [degC]")
    I_motor: Optional[float] = Field(None, description="Motor current [A]")
    mdot: Optional[float] = Field(None, gt=0, description="Mass flow rate [kg/s]")
    torque: Optional[float] = Field(None, description="Measured torque [Nm]")
    Power: Optional[float] = Field(None, description="Electrical power input [W]")


class CompressorDataset(BaseModel):
    """Named dataset (typically one Excel sheet) with a list of data points."""

    name: str = Field(..., description="Dataset/sheet name")
    data_points: List[CompressorDataPoint] = Field(
        default_factory=list, description="List of measured data points"
    )


class CompressorUploadResponse(BaseModel):
    """Response after uploading a compressor test data file."""

    file_id: str = Field(..., description="Generated file UUID")
    filename: str = Field(..., description="Original filename")
    sheets: List[str] = Field(
        default_factory=list, description="Detected sheet names"
    )
    point_counts: Dict[str, int] = Field(
        default_factory=dict, description="Number of data points per sheet"
    )


# ---------------------------------------------------------------------------
# Calibration request / result
# ---------------------------------------------------------------------------
class CompressorCalibrationRequest(BaseModel):
    """Request body for starting a compressor calibration run."""

    file_id: str = Field(..., description="Uploaded test data file UUID")
    sheet_name: Optional[str] = Field(
        None, description="Specific sheet to calibrate (None = all sheets)"
    )
    params_init: Optional[CompressorCalibrationParams] = Field(
        None, description="Initial parameter guesses"
    )


class CompressorCalibrationResult(BaseModel):
    """Result of a compressor calibration run."""

    params: CompressorCalibrationParams = Field(
        ..., description="Calibrated parameter values"
    )
    rmse: float = Field(..., ge=0, description="Root mean square error")
    r_squared: float = Field(..., description="Coefficient of determination (R^2)")
    residuals: List[float] = Field(
        default_factory=list, description="Per-point prediction residuals"
    )


# ---------------------------------------------------------------------------
# SSE progress event
# ---------------------------------------------------------------------------
class CompressorProgressEvent(BaseModel):
    """SSE progress event for compressor calibration.

    ``type`` can be: "progress", "phase", "done", "error".
    """

    type: str = Field(..., description="Event type: progress, phase, done, error")
    iteration: Optional[int] = Field(None, description="Current iteration number")
    rmse: Optional[float] = Field(None, description="Current RMSE")
    message: Optional[str] = Field(None, description="Status message")
    result: Optional[CompressorCalibrationResult] = Field(
        None, description="Final result (only for type='done')"
    )


# ---------------------------------------------------------------------------
# Energy-balance model schemas
# ---------------------------------------------------------------------------
class LookupEntry(BaseModel):
    """Single entry in a lookup table."""

    x: float = Field(..., description="Independent variable (I or Torque)")
    y: float = Field(..., description="Dependent variable (Torque or Loss)")


class LookupTableInput(BaseModel):
    """Lookup table input for motor characteristics."""

    rpm: float = Field(..., ge=0, description="RPM breakpoint for this curve")
    entries: List[LookupEntry] = Field(
        ..., min_length=1, description="List of (x, y) entries for this RPM"
    )


class CompressorEnergyRequest(BaseModel):
    """Request for energy-balance prediction."""

    # Refrigerant
    Ps: float = Field(..., description="Suction pressure [barG]")
    Ts: float = Field(..., description="Suction temperature [degC]")
    P_mid: float = Field(..., description="Mid-point pressure [barG]")
    T_mid: float = Field(..., description="Mid-point temperature [degC]")
    Pd: float = Field(..., description="Discharge pressure [barG]")
    mdot: float = Field(..., gt=0, description="Mass flow rate [kg/h]")
    # Motor electrical
    V: float = Field(..., gt=0, description="Line-to-line voltage [V]")
    I: float = Field(..., gt=0, description="Phase current [A]")
    RPM: float = Field(..., ge=0, description="Motor speed [rpm]")
    # Lookup tables
    torque_table: List[LookupTableInput] = Field(
        ..., min_length=1, description="I->Torque lookup by RPM"
    )
    loss_table: List[LookupTableInput] = Field(
        ..., min_length=1, description="(RPM,Torque)->Loss lookup"
    )
    # Thermal
    R_coil_case: float = Field(..., gt=0, description="Coil-to-case thermal resistance [K/W]")
    R_coil_core: float = Field(..., gt=0, description="Coil-to-core thermal resistance [K/W]")
    R_coil_refrigerant: float = Field(..., gt=0, description="Coil-to-refrigerant thermal resistance [K/W]")
    T_ambient: float = Field(25.0, description="Ambient temperature [degC]")


class CompressorEnergyResponse(BaseModel):
    """Response from energy-balance prediction."""

    Torque: float = Field(..., description="Motor torque [Nm]")
    T_coil: float = Field(..., description="Coil temperature [degC]")
    Pin: float = Field(..., description="Electrical input power [W]")
    Pmech: float = Field(..., description="Mechanical output power [W]")
    MotorLoss: float = Field(..., description="Total motor loss [W]")
    Q_refrig: float = Field(..., description="Heat to refrigerant [W]")
    Q_ambient: float = Field(..., description="Heat to ambient [W]")
    hs: float = Field(..., description="Suction enthalpy [J/kg]")
    h_mid: float = Field(..., description="Mid-point enthalpy [J/kg]")
    hd: float = Field(..., description="Discharge enthalpy [J/kg]")
    Td_est: float = Field(..., description="Estimated discharge temperature [degC]")
    mdot_recirc: float = Field(..., ge=0, description="Hot gas recirculation mass flow [kg/s]")
    recirc_ratio: float = Field(..., ge=0, description="Recirculation ratio (mdot_recirc / mdot_s) [-]")
    balance_error_pct: float = Field(..., ge=0, description="Energy balance error [%]")
    converged: bool = Field(..., description="Whether energy balance error < 10%")


# ---------------------------------------------------------------------------
# Calibration (energy-balance model)
# ---------------------------------------------------------------------------
class CalibDataPoint(BaseModel):
    """Single measurement point for calibration."""

    Ps: float = Field(..., description="Suction pressure [barG]")
    Ts: float = Field(..., description="Suction temperature [degC]")
    P_mid: float = Field(..., description="Mid-point pressure [barG]")
    T_mid: float = Field(..., description="Mid-point temperature [degC]")
    Pd: float = Field(..., description="Discharge pressure [barG]")
    mdot: float = Field(..., gt=0, description="Mass flow rate [kg/h]")
    V: float = Field(..., gt=0, description="Line-to-line voltage [V]")
    I: float = Field(..., gt=0, description="Phase current [A]")
    RPM: float = Field(..., ge=0, description="Motor speed [rpm]")
    T_ambient: float = Field(25.0, description="Ambient temperature [degC]")
    T_coil_measured: float = Field(..., description="Measured coil temperature [degC]")
    Td_measured: Optional[float] = Field(None, description="Measured discharge temperature [degC]")


class CalibConfig(BaseModel):
    """Configuration for the calibration optimizer."""

    n_starts: int = Field(5, ge=1, le=50, description="Number of multi-start runs")
    tol: float = Field(1e-6, gt=0, description="Optimization tolerance")
    max_iter: int = Field(500, ge=10, description="Max iterations per start")


class EnergyCalibRequest(BaseModel):
    """Request for energy-balance model calibration."""

    data_points: List[CalibDataPoint] = Field(
        ..., min_length=3, description="Measurement data points"
    )
    torque_table: List[LookupTableInput] = Field(
        ..., min_length=1, description="I->Torque lookup by RPM"
    )
    loss_table: List[LookupTableInput] = Field(
        ..., min_length=1, description="(RPM,Torque)->Loss lookup"
    )
    R_init: Optional[Dict[str, float]] = Field(
        None,
        description="Initial guesses for R values {R_coil_case, R_coil_core, R_coil_refrigerant}",
    )
    config: Optional[CalibConfig] = Field(None, description="Optimizer configuration")


class EnergyCalibResult(BaseModel):
    """Result from energy-balance model calibration."""

    R_coil_case: float = Field(..., description="Calibrated coil-to-case resistance [K/W]")
    R_coil_core: float = Field(..., description="Calibrated coil-to-core resistance [K/W]")
    R_coil_refrigerant: float = Field(..., description="Calibrated coil-to-refrigerant resistance [K/W]")
    rmse_T_coil: float = Field(..., ge=0, description="RMSE of T_coil prediction [degC]")
    mae_T_coil: float = Field(..., ge=0, description="MAE of T_coil prediction [degC]")
    max_error_T_coil: float = Field(..., ge=0, description="Max absolute error of T_coil [degC]")
    rmse_Td: Optional[float] = Field(None, description="RMSE of Td prediction [degC]")
    n_points: int = Field(..., ge=1, description="Number of data points used")
    converged: bool = Field(..., description="Whether optimizer converged")
    iterations: int = Field(..., ge=0, description="Total optimizer iterations")
    T_coil_predicted: List[float] = Field(
        default_factory=list, description="Predicted T_coil per data point [degC]"
    )
    T_coil_measured: List[float] = Field(
        default_factory=list, description="Measured T_coil per data point [degC]"
    )
    Td_predicted: List[float] = Field(
        default_factory=list, description="Predicted Td per data point [degC]"
    )

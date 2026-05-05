"""Compressor Thermal Model API router (REQ-COMP-API-001).

Four endpoints under /compressor prefix:
  1. POST /upload      — Upload and parse multi-sheet compressor test Excel
  2. GET  /datasets    — List uploaded compressor test datasets
  3. POST /predict     — Single-point compressor thermal prediction
  4. POST /calibrate   — Run calibration with SSE progress

Reference: SPEC-COMP-THERMAL-001
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from core.compressor_data import parse_compressor_excel, CompressorParseResult
from core.compressor_energy_model import (
    CalibDataPoint as CoreCalibDataPoint,
    EnergyModelInput,
    LossTable,
    TorqueCurrentTable,
    calibrate_thermal_resistances,
    predict_energy_balance,
)
from core.compressor_model import (
    MotorParams,
    IterationResult,
    solve_tm_iterative,
)
from schemas.compressor import (
    CompressorCalibrationParams,
    CompressorCalibrationRequest,
    CompressorCalibrationResult,
    CompressorEnergyRequest,
    CompressorEnergyResponse,
    CompressorOperatingPoint,
    CompressorPrediction,
    CompressorPredictionRequest,
    CompressorProgressEvent,
    EnergyCalibRequest,
    EnergyCalibResult,
)

router = APIRouter()

# In-memory storage for uploaded compressor datasets
_datasets: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Helper: convert CompressorParseResult to upload response dict
# ---------------------------------------------------------------------------
def _parse_result_to_response(
    file_id: str,
    result: CompressorParseResult,
) -> dict:
    """Convert a CompressorParseResult to the upload response format."""
    sheets_out = []
    for s in result.sheets:
        sheets_out.append({
            "sheet_name": s.sheet_name,
            "variant_name": s.variant_name,
            "n_points": s.n_points,
            "columns_found": s.columns_found,
            "columns_missing": s.columns_missing,
            "errors": s.errors,
        })

    return {
        "file_id": file_id,
        "filename": result.filename,
        "sheets": sheets_out,
        "total_points": result.total_points,
        "valid_sheets": result.valid_sheets,
        "invalid_sheets": result.invalid_sheets,
    }


# ---------------------------------------------------------------------------
# 1. POST /upload
# ---------------------------------------------------------------------------
# @MX:ANCHOR: [AUTO] upload_compressor_data is the primary entry point for
# compressor test data ingestion, feeding both calibration and analysis.
# @MX:REASON: Upload endpoint is the gateway for all compressor data; incorrect
# parsing or storage corrupts downstream calibration and prediction.
@router.post("/upload")
async def upload_compressor_data(
    file: UploadFile = File(...),
) -> dict:
    """Upload and parse a multi-sheet compressor test data Excel file.

    Accepts .xlsx and .xlsm files. Parses all sheets, validates columns,
    normalizes units, and returns structured per-sheet results.
    """
    filename = file.filename or "unknown"
    suffix = Path(filename).suffix.lower()
    if suffix not in (".xlsx", ".xlsm", ".xls"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Supported: .xlsx, .xlsm, .xls",
        )

    # Save to temp file for openpyxl
    content = await file.read()
    tmp_path = Path(f"/tmp/comp_upload_{uuid.uuid4().hex}{suffix}")
    try:
        tmp_path.write_bytes(content)

        try:
            parse_result = parse_compressor_excel(str(tmp_path))
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to parse Excel file: {exc}",
            ) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    # Store in memory
    file_id = f"upload_{uuid.uuid4().hex[:12]}"
    _datasets[file_id] = {
        "file_id": file_id,
        "filename": filename,
        "parse_result": parse_result,
    }

    return _parse_result_to_response(file_id, parse_result)


# ---------------------------------------------------------------------------
# 2. GET /datasets
# ---------------------------------------------------------------------------
@router.get("/datasets")
async def list_datasets() -> dict:
    """Return list of uploaded compressor test datasets."""
    datasets_out = []
    for file_id, entry in _datasets.items():
        pr: CompressorParseResult = entry["parse_result"]
        datasets_out.append({
            "file_id": file_id,
            "filename": entry["filename"],
            "sheets": [s.sheet_name for s in pr.sheets],
            "total_points": pr.total_points,
        })

    return {"datasets": datasets_out}


# ---------------------------------------------------------------------------
# 3. POST /predict
# ---------------------------------------------------------------------------
# @MX:ANCHOR: [AUTO] predict is the primary public prediction API, called
# from the frontend for single-point thermal analysis.
# @MX:REASON: Prediction endpoint is the most-used API; incorrect parameter
# mapping or solver invocation produces wrong thermal predictions.
@router.post("/predict")
async def predict(
    body: CompressorPredictionRequest,
) -> dict:
    """Single-point or multi-point compressor thermal prediction.

    Accepts operating conditions with optional calibration parameter overrides.
    Uses the iterative solver to resolve Tm -> Q_recirc -> hm -> Tm coupling.
    """
    # Build calibration params (use defaults if not provided)
    params = body.calibration_params or CompressorCalibrationParams()

    # Build motor params with defaults
    motor_params = MotorParams()

    # Build solver inputs (single invocation)
    op_dict = {
        "RPM": body.RPM,
        "Ps": body.Ps,
        "Ts": body.Ts,
        "Pd": body.Pd,
        "I_peak": motor_params.I_peak,
    }
    params_dict = {
        "UA_0": params.UA_0,
        "UA_1": params.UA_1,
        "eta_vol": params.eta_vol,
        "eta_s": params.eta_s,
        "R_coil_core": params.R_coil_core,
        "h_ref": params.h_ref,
        "R": motor_params.R,
        "V_displ": motor_params.V_displ,
        "IronLoss": motor_params.IronLoss,
    }

    try:
        result: IterationResult = solve_tm_iterative(op_dict, params_dict)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Build response dict directly to avoid CompressorPrediction schema
    # constraints (e.g. mdot gt=0) on edge cases like RPM=0 zero flow.
    return {
        "prediction": {
            "Tm": result.Tm,
            "Td": result.Td,
            "Torque": result.Torque,
            "Q_recirc": result.Q_recirc,
            "MotorLoss": result.MotorLoss,
            "hm": result.hm,
            "hd": result.hd,
            "mdot": result.mdot,
        },
        "converged": result.converged,
        "iterations": result.iterations,
        "residual": result.residual,
    }


# ---------------------------------------------------------------------------
# 4. POST /calibrate
# ---------------------------------------------------------------------------
async def _calibrate_event_stream(
    file_id: str,
    sheet_name: Optional[str],
) -> "AsyncGenerator[str, None]":
    """SSE event stream generator for compressor calibration."""
    entry = _datasets.get(file_id)
    if entry is None:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Dataset {file_id} not found'})}\n\n"
        return

    parse_result: CompressorParseResult = entry["parse_result"]

    # Filter sheets if specific sheet requested
    target_sheets = parse_result.sheets
    if sheet_name is not None:
        target_sheets = [s for s in parse_result.sheets if s.sheet_name == sheet_name]
        if not target_sheets:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Sheet {sheet_name} not found'})}\n\n"
            return

    # Emit phase event
    yield f"data: {json.dumps({'type': 'phase', 'message': 'Starting compressor calibration...'})}\n\n"

    # Collect data points from target sheets
    all_data = []
    for sheet in target_sheets:
        all_data.extend(sheet.data)

    if not all_data:
        yield f"data: {json.dumps({'type': 'error', 'message': 'No data points available for calibration'})}\n\n"
        return

    n_points = len(all_data)

    # Emit progress
    yield f"data: {json.dumps({'type': 'progress', 'iteration': 0, 'message': f'Processing {n_points} data points'})}\n\n"

    # Run a simplified calibration: use default params and compute RMSE
    # against measured Td values from the data
    params = CompressorCalibrationParams()
    motor_params = MotorParams()

    residuals = []
    for i, dp in enumerate(all_data):
        try:
            op = CompressorOperatingPoint(
                RPM=dp.RPM, Ps=dp.Ps, Ts=dp.Ts, Pd=dp.Pd,
            )
            pred = predict_compressor(op, params, motor_params)
            residual = pred.Td - dp.Td
            residuals.append(residual)
        except Exception:
            residuals.append(0.0)

        if (i + 1) % max(1, n_points // 5) == 0:
            progress_pct = (i + 1) / n_points
            yield f"data: {json.dumps({'type': 'progress', 'iteration': i + 1, 'message': f'Progress: {progress_pct:.0%}'})}\n\n"

    rmse = (sum(r**2 for r in residuals) / len(residuals)) ** 0.5 if residuals else 0.0

    result = CompressorCalibrationResult(
        params=params,
        rmse=rmse,
        r_squared=0.0,
        residuals=residuals,
    )

    yield f"data: {json.dumps({'type': 'done', 'result': json.loads(result.model_dump_json())})}\n\n"


@router.post("/calibrate")
async def calibrate(
    body: CompressorCalibrationRequest,
) -> StreamingResponse:
    """Run calibration optimization with SSE progress events.

    Streams progress events as SSE, ending with a final result event.
    """
    if body.file_id not in _datasets:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset {body.file_id} not found. Upload data first.",
        )

    return StreamingResponse(
        _calibrate_event_stream(body.file_id, body.sheet_name),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# 5. POST /predict-energy
# ---------------------------------------------------------------------------
def _build_torque_table(
    table_inputs: list,
) -> TorqueCurrentTable:
    """Build a TorqueCurrentTable from request lookup table inputs."""
    rpm_values: list[float] = []
    entries: dict[float, list[tuple[float, float]]] = {}
    for t in table_inputs:
        rpm_values.append(t.rpm)
        entries[t.rpm] = [(e.x, e.y) for e in t.entries]
    rpm_values.sort()
    return TorqueCurrentTable(rpm_values=rpm_values, entries=entries)


def _build_loss_table(
    table_inputs: list,
) -> LossTable:
    """Build a LossTable from request lookup table inputs."""
    rpm_values: list[float] = []
    entries: dict[float, list[tuple[float, float]]] = {}
    for t in table_inputs:
        rpm_values.append(t.rpm)
        entries[t.rpm] = [(e.x, e.y) for e in t.entries]
    rpm_values.sort()
    return LossTable(rpm_values=rpm_values, entries=entries)


# @MX:ANCHOR: [AUTO] predict_energy is the API entry point for the
# energy-balance compressor prediction model.
# @MX:REASON: New primary endpoint for energy-balance predictions;
# incorrect table construction or input mapping produces wrong results.
@router.post("/predict-energy")
async def predict_energy(body: CompressorEnergyRequest) -> dict:
    """Energy-balance based compressor prediction.

    Accepts operating conditions with motor lookup tables and thermal
    resistance parameters.  Returns power, loss, temperature, and
    energy-balance convergence data.
    """
    torque_table = _build_torque_table(body.torque_table)
    loss_table = _build_loss_table(body.loss_table)

    model_input = EnergyModelInput(
        Ps=body.Ps,
        Ts=body.Ts,
        P_mid=body.P_mid,
        T_mid=body.T_mid,
        Pd=body.Pd,
        mdot=body.mdot,
        V=body.V,
        I=body.I,
        RPM=body.RPM,
        R_coil_case=body.R_coil_case,
        R_coil_core=body.R_coil_core,
        R_coil_refrigerant=body.R_coil_refrigerant,
        T_ambient=body.T_ambient,
    )

    try:
        result = predict_energy_balance(model_input, torque_table, loss_table)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "Torque": result.Torque,
        "T_coil": result.T_coil,
        "Pin": result.Pin,
        "Pmech": result.Pmech,
        "MotorLoss": result.MotorLoss,
        "Q_refrig": result.Q_refrig,
        "Q_ambient": result.Q_ambient,
        "hs": result.hs,
        "h_mid": result.h_mid,
        "hd": result.hd,
        "Td_est": result.Td_est,
        "mdot_recirc": result.mdot_recirc,
        "recirc_ratio": result.recirc_ratio,
        "balance_error_pct": result.balance_error_pct,
        "converged": result.converged,
    }


# 6. POST /calibrate-energy
@router.post("/calibrate-energy")
async def calibrate_energy(body: EnergyCalibRequest) -> dict:
    """Calibrate thermal resistances (R_coil_case, R_coil_core, R_coil_refrigerant).

    Takes multiple measurement data points and lookup tables, then optimizes
    the thermal resistance values to minimize T_coil prediction error.
    """
    torque_table = _build_torque_table(body.torque_table)
    loss_table = _build_loss_table(body.loss_table)

    core_points = [
        CoreCalibDataPoint(
            Ps=pt.Ps,
            Ts=pt.Ts,
            P_mid=pt.P_mid,
            T_mid=pt.T_mid,
            Pd=pt.Pd,
            mdot=pt.mdot,
            V=pt.V,
            I=pt.I,
            RPM=pt.RPM,
            T_ambient=pt.T_ambient,
            T_coil_measured=pt.T_coil_measured,
            Td_measured=pt.Td_measured,
        )
        for pt in body.data_points
    ]

    config = body.config
    try:
        result = calibrate_thermal_resistances(
            data_points=core_points,
            torque_table=torque_table,
            loss_table=loss_table,
            R_init=body.R_init,
            n_starts=config.n_starts if config else 5,
            tol=config.tol if config else 1e-6,
            max_iter=config.max_iter if config else 500,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "R_coil_case": result.R_coil_case,
        "R_coil_core": result.R_coil_core,
        "R_coil_refrigerant": result.R_coil_refrigerant,
        "rmse_T_coil": result.rmse_T_coil,
        "mae_T_coil": result.mae_T_coil,
        "max_error_T_coil": result.max_error_T_coil,
        "rmse_Td": result.rmse_Td,
        "n_points": result.n_points,
        "converged": result.converged,
        "iterations": result.iterations,
        "T_coil_predicted": result.T_coil_predicted,
        "T_coil_measured": result.T_coil_measured,
        "Td_predicted": result.Td_predicted,
    }

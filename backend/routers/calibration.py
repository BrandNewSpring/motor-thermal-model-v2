"""Calibration API router with SSE streaming."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.calibration import CalibSettings as CoreCalibSettings
from core.calibration import run_calibration
from core.loss_model import CoilParams as CoreCoilParams
from core.loss_model import SimpleIronLoss as CoreSimpleIronLoss
from core.loss_model import make_simple_loss_fn
from core.motor_geometry import compute_thermal_masses
from core.thermal_model import simulate_3node_final
from schemas.calibration import (
    CalibRequest,
    CalibResult,
    ColumnMapping,
    FileCalibResult,
    FileConditions,
    ThermalParams,
)
from storage.profiles import get_profile, update_calib_result

router = APIRouter()

UPLOADS_DIR = Path.home() / ".mtm_v2" / "uploads"

# In-memory job store: job_id -> { status, result, queue }
_jobs: dict[str, dict] = {}


def _get_file_path(file_id: str) -> Path:
    """Resolve file_id to disk path."""
    if not UPLOADS_DIR.exists():
        raise HTTPException(status_code=404, detail="Uploads directory not found")
    matches = list(UPLOADS_DIR.glob(f"{file_id}_*"))
    if not matches:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")
    return matches[0]


def _parse_data_file(filepath: Path) -> pd.DataFrame:
    """Parse a CSV or Excel file.

    Tries encodings in order: utf-8, cp949, latin-1.
    CP949 covers Korean (EUC-KR) exports from power analyzers.
    """
    suffix = filepath.suffix.lower()
    if suffix == ".csv":
        for enc in ("utf-8", "cp949", "latin-1"):
            try:
                return pd.read_csv(filepath, encoding=enc)
            except UnicodeDecodeError:
                continue
        raise ValueError(f"Could not decode CSV file: {filepath.name}")
    elif suffix in (".xlsx", ".xls"):
        return pd.read_excel(filepath)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def _run_calibration_job(
    job_id: str,
    profile_id: str,
    data_file_ids: list[str],
    settings: "CalibSettings",
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue,
    column_mapping: "ColumnMapping | None" = None,
) -> None:
    """Run calibration in a background thread and push events to the queue."""
    try:
        # Load profile
        profile = get_profile(profile_id)
        if profile is None:
            loop.call_soon_threadsafe(
                lambda: queue.put_nowait({"type": "error", "message": f"Profile {profile_id} not found"})
            )
            return

        # Load and merge data from all files, tracking file boundaries
        file_frames: list[tuple[pd.DataFrame, str, str]] = []  # (df, file_id, filename)
        for fid in data_file_ids:
            data_path = _get_file_path(fid)
            file_frames.append((_parse_data_file(data_path), fid, data_path.name))
        df = pd.concat([ff[0] for ff in file_frames], ignore_index=True) if len(file_frames) > 1 else file_frames[0][0]

        # Build boundary indices: (start_idx, end_idx) per file in the concatenated df
        file_boundaries: list[tuple[int, int, str, str]] = []  # (start, end, file_id, filename)
        offset = 0
        for fdf, fid, fname in file_frames:
            n = len(fdf)
            file_boundaries.append((offset, offset + n, fid, fname))
            offset += n

        # Extract arrays from dataframe
        # Use explicit column mapping if provided, otherwise auto-detect
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

        time_col = None
        rpm_col = None
        I_col = None
        T_amb_col = None
        T_coil_col = None

        if column_mapping is not None:
            I_col = column_mapping.I_phase
            T_amb_col = column_mapping.T_amb
            T_coil_col = column_mapping.T_coil
            time_col = column_mapping.time
            rpm_col = column_mapping.rpm
        else:
            # Auto-detect columns by name heuristics
            for col in numeric_cols:
                col_lower = col.lower().strip()
                if "time" in col_lower and time_col is None:
                    time_col = col
                elif "rpm" in col_lower and rpm_col is None:
                    rpm_col = col
                elif col_lower in ("i_phase", "i", "current", "i_a") and I_col is None:
                    I_col = col
                elif "t_amb" in col_lower or "ambient" in col_lower:
                    T_amb_col = col
                elif "t_coil" in col_lower or "coil" in col_lower:
                    T_coil_col = col

        # Fallback: use positional if not enough detected
        if I_col is None and len(numeric_cols) >= 2:
            I_col = numeric_cols[0] if time_col != numeric_cols[0] else numeric_cols[1]
        if T_amb_col is None and len(numeric_cols) >= 3:
            T_amb_col = numeric_cols[-2] if T_coil_col != numeric_cols[-2] else numeric_cols[-3]
        if T_coil_col is None and len(numeric_cols) >= 1:
            T_coil_col = numeric_cols[-1]
        if rpm_col is None:
            rpm_col = time_col  # will be filled with 0 if time_col used
        if time_col is None:
            time_col = numeric_cols[0] if numeric_cols else None

        if I_col is None or T_amb_col is None or T_coil_col is None:
            loop.call_soon_threadsafe(
                lambda: queue.put_nowait({
                    "type": "error",
                    "message": "Could not detect required columns (I_phase, T_amb, T_coil)",
                })
            )
            return

        # Build arrays
        time_array = pd.to_numeric(df[time_col], errors="coerce").fillna(0).values.astype(float)
        if time_col == rpm_col:
            rpm_array = np.zeros_like(time_array)
        else:
            rpm_array = pd.to_numeric(df.get(rpm_col, 0), errors="coerce").fillna(0).values.astype(float)
        I_array = pd.to_numeric(df[I_col], errors="coerce").fillna(0).values.astype(float)
        T_amb_array = pd.to_numeric(df[T_amb_col], errors="coerce").fillna(25.0).values.astype(float)
        T_coil_meas = pd.to_numeric(df[T_coil_col], errors="coerce").fillna(0).values.astype(float)

        # If no time column, generate from index
        if np.all(time_array == 0):
            time_array = np.arange(len(I_array), dtype=float)

        # Compute thermal masses from profile geometry
        geo = profile.geometry
        mat = profile.material
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

        # Build loss function
        coil = CoreCoilParams(
            R0=profile.coil.R0,
            T0=profile.coil.T0,
            alpha=profile.coil.alpha,
            n_phases=profile.coil.n_phases,
        )

        iron_loss = profile.simple_iron_loss
        if iron_loss is None:
            iron_loss = __import__("schemas.motor", fromlist=["SimpleIronLoss"]).SimpleIronLoss()

        core_iron = CoreSimpleIronLoss(
            I_max=iron_loss.I_max,
            RPM_max=iron_loss.RPM_max,
            alpha_iron=iron_loss.alpha_iron,
            n_phases=profile.coil.n_phases,
            R0=profile.coil.R0,
            T0=profile.coil.T0,
            alpha_cu=profile.coil.alpha,
        )
        loss_fn = make_simple_loss_fn(coil, core_iron)

        # Convert API settings to core settings
        core_settings = CoreCalibSettings(
            n_starts=settings.n_starts,
            tail_gamma=settings.tail_gamma,
            ss_penalty=settings.ss_penalty,
            normalize_per_file=settings.normalize_per_file,
            R1_init=settings.R1_init,
            R2_init=settings.R2_init,
            h_nat_init=settings.h_nat_init,
            h_rpm_init=settings.h_rpm_init,
            R1_bounds=settings.R1_bounds,
            R2_bounds=settings.R2_bounds,
        )

        # Progress callback that pushes to the asyncio queue
        def progress_cb(event: dict) -> None:
            loop.call_soon_threadsafe(lambda: queue.put_nowait(event))

        # Phase notification
        loop.call_soon_threadsafe(
            lambda: queue.put_nowait({
                "type": "phase",
                "message": "Starting multi-start calibration...",
            })
        )

        # Run the calibration
        result = run_calibration(
            time_array=time_array,
            I_array=I_array,
            rpm_array=rpm_array,
            T_amb_array=T_amb_array,
            T_coil_meas=T_coil_meas,
            C_coil=masses.C_coil,
            C_core=masses.C_core,
            C_housing=masses.C_housing,
            A_housing=masses.A_housing,
            loss_fn=loss_fn,
            settings=core_settings,
            progress_callback=progress_cb,
        )

        # Build per-file results by re-simulating each file independently
        per_file_results: list[FileCalibResult] = []
        if len(file_boundaries) > 1 or (len(file_boundaries) == 1 and file_boundaries[0][2]):
            for start_idx, end_idx, fid, fname in file_boundaries:
                file_time = time_array[start_idx:end_idx]
                file_I = I_array[start_idx:end_idx]
                file_rpm = rpm_array[start_idx:end_idx]
                file_T_amb = T_amb_array[start_idx:end_idx]
                file_T_coil_meas = T_coil_meas[start_idx:end_idx]

                # Re-simulate with optimized parameters (starts from file's own ambient)
                file_sim = simulate_3node_final(
                    time_array=file_time,
                    I_array=file_I,
                    rpm_array=file_rpm,
                    T_amb_array=file_T_amb,
                    C_coil=masses.C_coil,
                    C_core=masses.C_core,
                    C_housing=masses.C_housing,
                    R1=result.R1,
                    R2=result.R2,
                    h_nat=result.h_nat,
                    h_rpm=result.h_rpm,
                    A_housing=masses.A_housing,
                    loss_fn=loss_fn,
                )

                per_file_results.append(FileCalibResult(
                    file_id=fid,
                    filename=fname,
                    conditions=FileConditions(
                        I_mean=float(np.mean(file_I)),
                        T_amb_mean=float(np.mean(file_T_amb)),
                        rpm_representative=float(np.mean(file_rpm)) if len(file_rpm) > 0 else 0.0,
                    ),
                    time_array=file_time.tolist(),
                    T_coil_meas=file_T_coil_meas.tolist(),
                    T_coil_sim=file_sim.T_coil.tolist(),
                    T_core_sim=file_sim.T_core.tolist(),
                    T_housing_sim=file_sim.T_housing.tolist(),
                ))

        # Build API result
        calib_result = CalibResult(
            params=ThermalParams(
                R1=result.R1,
                R2=result.R2,
                h_nat=result.h_nat,
                h_rpm=result.h_rpm,
                C_coil=masses.C_coil,
                C_core=masses.C_core,
                C_housing=masses.C_housing,
            ),
            rmse=result.rmse,
            r_squared=result.r_squared,
            T_coil_sim=result.T_coil_sim.tolist(),
            T_core_sim=result.T_core_sim.tolist(),
            T_housing_sim=result.T_housing_sim.tolist(),
            T_coil_meas=T_coil_meas.tolist(),
            time_array=time_array.tolist(),
            residuals=result.residuals.tolist(),
            time_s=result.time_s,
            converged=result.converged,
            loss_history=result.loss_history,
            per_file_results=per_file_results,
        )

        # Save result to job store and profile
        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["result"] = calib_result

        # Attach result to profile
        update_calib_result(profile_id, calib_result)

        # Send done event
        loop.call_soon_threadsafe(
            lambda: queue.put_nowait({
                "type": "done",
                "result": json.loads(calib_result.model_dump_json()),
            })
        )

    except Exception as exc:
        _jobs[job_id]["status"] = "error"
        error_msg = str(exc)
        _jobs[job_id]["error"] = error_msg
        loop.call_soon_threadsafe(
            lambda: queue.put_nowait({"type": "error", "message": error_msg})
        )


@router.post("/start")
async def start_calibration(body: CalibRequest) -> dict:
    """Start a calibration run and return job_id."""
    try:
        file_ids = body.resolved_file_ids()
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=str(exc)
        ) from exc

    job_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _jobs[job_id] = {"status": "running", "result": None, "error": None, "queue": queue}

    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        None,
        _run_calibration_job,
        job_id,
        body.profile_id,
        file_ids,
        body.settings,
        loop,
        queue,
        body.column_mapping,
    )

    return {"job_id": job_id}


async def _event_stream(job_id: str) -> "AsyncGenerator[str, None]":
    """SSE event stream generator."""
    job = _jobs.get(job_id)
    if job is None:
        yield f"data: {json.dumps({'type': 'error', 'message': 'Job not found'})}\n\n"
        return

    queue: asyncio.Queue = job["queue"]
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=300.0)
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Timeout'})}\n\n"
            break

        yield f"data: {json.dumps(event)}\n\n"
        if event.get("type") in ("done", "error"):
            break


@router.get("/{job_id}/stream")
async def stream_calibration(job_id: str) -> StreamingResponse:
    """SSE endpoint for calibration progress."""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return StreamingResponse(
        _event_stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}/result", response_model=CalibResult)
async def get_calibration_result(job_id: str) -> CalibResult:
    """Return the final calibration result (polling endpoint)."""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job["status"] == "running":
        raise HTTPException(status_code=503, detail="Calibration still in progress")
    if job["status"] == "error":
        raise HTTPException(status_code=500, detail=job.get("error", "Calibration failed"))
    if job["result"] is None:
        raise HTTPException(status_code=500, detail="No result available")

    return job["result"]

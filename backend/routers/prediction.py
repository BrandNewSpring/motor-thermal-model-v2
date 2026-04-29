"""Prediction API router — steady-state and grid prediction."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np
from fastapi import APIRouter, HTTPException

from core.loss_model import CoilParams as CoreCoilParams
from core.loss_model import SimpleIronLoss as CoreSimpleIronLoss
from core.loss_model import make_simple_loss_fn
from core.motor_geometry import compute_thermal_masses
from core.thermal_model import R3_at_rpm, simulate_3node
from schemas.data import GridPredictionRequest, GridPredictionResult, SteadyStateRequest, SteadyStateResult
from storage.profiles import get_profile

router = APIRouter()

# Shared thread pool for grid computations
_executor = ThreadPoolExecutor(max_workers=4)

# Thermal runaway threshold
_THERMAL_RUNAWAY_LIMIT = 500.0  # degC


def _get_calibrated_params(
    profile, request
) -> tuple[float, float, float, float]:
    """Extract calibration parameters from profile or request overrides."""
    R1 = getattr(request, "R1", None)
    R2 = getattr(request, "R2", None)
    h_nat = getattr(request, "h_nat", None)
    h_rpm = getattr(request, "h_rpm", None)

    # Try to load from profile calib_result if not overridden
    if R1 is None or R2 is None or h_nat is None or h_rpm is None:
        # Access raw profile dict to check for calib_result
        import json
        from pathlib import Path

        profiles_dir = Path.home() / ".mtm_v2" / "profiles"
        fp = profiles_dir / f"{profile.id}.json"
        if fp.exists():
            raw = json.loads(fp.read_text(encoding="utf-8"))
            calib = raw.get("calib_result")
            if calib and isinstance(calib, dict):
                params = calib.get("params", {})
                R1 = R1 or params.get("R1")
                R2 = R2 or params.get("R2")
                h_nat = h_nat or params.get("h_nat")
                h_rpm = h_rpm or params.get("h_rpm")

    # Final defaults
    if R1 is None:
        R1 = 0.5
    if R2 is None:
        R2 = 0.1
    if h_nat is None:
        h_nat = 10.0
    if h_rpm is None:
        h_rpm = 0.02

    return R1, R2, h_nat, h_rpm


def _compute_steady_state(
    profile,
    I_phase: float,
    T_amb: float,
    rpm: float,
    R1: float,
    R2: float,
    h_nat: float,
    h_rpm: float,
) -> SteadyStateResult:
    """Run a long simulation to reach steady state."""
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

    coil = CoreCoilParams(
        R0=profile.coil.R0,
        T0=profile.coil.T0,
        alpha=profile.coil.alpha,
        n_phases=profile.coil.n_phases,
    )

    iron_loss = profile.simple_iron_loss
    if iron_loss is None:
        from schemas.motor import SimpleIronLoss
        iron_loss = SimpleIronLoss()

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

    # Estimate time constant and simulate 3*tau
    R3 = R3_at_rpm(rpm, h_nat, h_rpm, masses.A_housing)
    C_total = masses.C_coil + masses.C_core + masses.C_housing
    tau = C_total * R3
    t_end = max(3.0 * tau, 1000.0)

    N = 500
    t = np.linspace(0, t_end, N)
    I = np.full(N, I_phase)
    rpm_arr = np.full(N, rpm)
    T_amb_arr = np.full(N, T_amb)

    result = simulate_3node(
        time_array=t,
        I_array=I,
        rpm_array=rpm_arr,
        T_amb_array=T_amb_arr,
        C_coil=masses.C_coil,
        C_core=masses.C_core,
        C_housing=masses.C_housing,
        R1=R1,
        R2=R2,
        h_nat=h_nat,
        h_rpm=h_rpm,
        A_housing=masses.A_housing,
        loss_fn=loss_fn,
        T_init=T_amb,
        mode="fast",
    )

    T_coil_ss = float(result.T_coil[-1])
    if T_coil_ss > _THERMAL_RUNAWAY_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"Thermal runaway detected: T_coil_ss = {T_coil_ss:.1f} degC > {_THERMAL_RUNAWAY_LIMIT}",
        )

    # Compute losses at steady state
    Q_cu, Q_iron = loss_fn(I_phase, T_coil_ss, rpm)

    return SteadyStateResult(
        T_coil_ss=T_coil_ss,
        T_core_ss=float(result.T_core[-1]),
        T_housing_ss=float(result.T_housing[-1]),
        Q_copper=Q_cu,
        Q_iron=Q_iron,
        R3_at_rpm=R3,
    )


@router.post("/steady-state", response_model=SteadyStateResult)
async def predict_steady_state(body: SteadyStateRequest) -> SteadyStateResult:
    """Predict steady-state temperatures at a single operating point."""
    profile = get_profile(body.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {body.profile_id} not found")

    R1, R2, h_nat, h_rpm = _get_calibrated_params(profile, body)
    return _compute_steady_state(profile, body.I_phase, body.T_amb, body.rpm, R1, R2, h_nat, h_rpm)


@router.post("/grid", response_model=GridPredictionResult)
async def predict_grid(body: GridPredictionRequest) -> GridPredictionResult:
    """Predict steady-state temperatures on an I x RPM grid."""
    profile = get_profile(body.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {body.profile_id} not found")

    R1, R2, h_nat, h_rpm = _get_calibrated_params(profile, body)

    I_values = np.linspace(body.I_range[0], body.I_range[1], body.n_points)
    RPM_values = np.linspace(body.RPM_range[0], body.RPM_range[1], body.n_points)

    grid_I = np.zeros((body.n_points, body.n_points))
    grid_RPM = np.zeros((body.n_points, body.n_points))
    grid_T_coil = np.zeros((body.n_points, body.n_points))
    grid_T_core = np.zeros((body.n_points, body.n_points))
    grid_T_housing = np.zeros((body.n_points, body.n_points))

    def _compute_point(i: int, j: int) -> tuple[int, int, float, float, float]:
        I_val = float(I_values[i])
        rpm_val = float(RPM_values[j])
        result = _compute_steady_state(
            profile, I_val, body.T_amb, rpm_val, R1, R2, h_nat, h_rpm
        )
        return i, j, result.T_coil_ss, result.T_core_ss, result.T_housing_ss

    # Run grid computations in thread pool
    futures = []
    for i in range(body.n_points):
        for j in range(body.n_points):
            grid_I[i][j] = I_values[i]
            grid_RPM[i][j] = RPM_values[j]
            futures.append(_executor.submit(_compute_point, i, j))

    for future in futures:
        try:
            i, j, T_coil, T_core, T_housing = future.result(timeout=120)
            grid_T_coil[i][j] = T_coil
            grid_T_core[i][j] = T_core
            grid_T_housing[i][j] = T_housing
        except Exception as exc:
            if "Thermal runaway" in str(exc):
                grid_T_coil[i][j] = float("nan")
                grid_T_core[i][j] = float("nan")
                grid_T_housing[i][j] = float("nan")
            else:
                raise

    return GridPredictionResult(
        grid_I=grid_I.tolist(),
        grid_RPM=grid_RPM.tolist(),
        grid_T_coil=grid_T_coil.tolist(),
        grid_T_core=grid_T_core.tolist(),
        grid_T_housing=grid_T_housing.tolist(),
    )

"""Multi-start differential evolution calibration for compressor thermal model.

Calibrates 6 compressor thermal model parameters:
  UA_0, UA_1, eta_vol, eta_s, R_coil_core, h_ref

using weighted least-squares objective with multi-start differential evolution.

Reference: SPEC-COMP-THERMAL-001 REQ-COMP-OPTIM-001
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import differential_evolution

from .compressor_model import (
    IterationResult,
    MotorParams,
    solve_tm_iterative,
)
from .refrigerant import get_density, get_enthalpy


# ---------------------------------------------------------------------------
# Bounds for the 6 calibration parameters
# ---------------------------------------------------------------------------
# Order: [UA_0, UA_1, eta_vol, eta_s, R_coil_core, h_ref]
PARAMETER_BOUNDS = [
    (5.0, 50.0),       # UA_0 [W/K]
    (0.1, 5.0),         # UA_1 [W/(K*krpm)]
    (0.3, 0.95),        # eta_vol [-]
    (0.3, 0.95),        # eta_s [-]
    (0.001, 1.0),       # R_coil_core [degC/W]
    (0.1, 100.0),       # h_ref [W/(m^2*K*sqrt(RPM))]
]

PARAMETER_NAMES = [
    "UA_0", "UA_1", "eta_vol", "eta_s", "R_coil_core", "h_ref",
]

# Cross-validation target RMSE for Tm [degC]
_CV_TARGET_RMSE: float = 3.0


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass
class CalibrationConfig:
    """Configuration for calibration optimization."""

    n_starts: int = 3
    seed: int = 42
    strategy: str = "best1bin"
    popsize: int = 15   # multiplied by ndim
    ftol: float = 1e-8
    max_iter: int = 1000
    sigma_Tm: float = 1.0
    sigma_Torque_pct: float = 0.05
    alpha: float = 0.5   # solver relaxation
    solver_max_iter: int = 30  # max iterations for inner Tm solver per eval
    polish: bool = True  # L-BFGS-B polish after DE


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
@dataclass
class CalibrationResult:
    """Result of calibration optimization."""

    params: dict                  # UA_0, UA_1, eta_vol, eta_s, R_coil_core, h_ref
    rmse_Tm: float
    rmse_Torque: float
    r_squared_Tm: float
    r_squared_Torque: float
    residuals_Tm: list[float]
    residuals_Torque: list[float]
    cost: float
    converged: bool
    n_starts: int
    loss_history: list[float]     # best cost per start
    time_s: float


@dataclass
class CVFoldResult:
    """Result of a single cross-validation fold."""

    held_out_sheet: str
    rmse_Tm_train: float
    rmse_Tm_test: float
    rmse_Torque_train: float
    rmse_Torque_test: float
    generalization_gap_Tm: float     # rmse_test - rmse_train
    generalization_gap_Torque: float


@dataclass
class CrossValidationResult:
    """Result of leave-one-sheet-out cross-validation."""

    folds: list[CVFoldResult]
    mean_rmse_Tm: float
    mean_generalization_gap_Tm: float
    n_folds_meeting_target: int  # folds with RMSE < 3 degC


# ---------------------------------------------------------------------------
# Objective function
# ---------------------------------------------------------------------------
# @MX:ANCHOR: [AUTO] objective_function is the core cost function for
# differential_evolution, called thousands of times during calibration.
# @MX:REASON: Incorrect objective formulation produces wrong calibrated
# parameters; the weighted normalization must match the SPEC definition.
def objective_function(
    x: np.ndarray,
    data_points: list,
    motor_params: MotorParams,
    config: CalibrationConfig,
) -> float:
    """Weighted objective function for differential_evolution.

    J = sum_i w_i * [(Tm_pred_i - Tm_meas_i)^2 / sigma_Tm^2
                   + (Torque_pred_i - Torque_meas_i)^2 / sigma_Torque_i^2]

    Parameters
    ----------
    x : np.ndarray
        Optimization vector [UA_0, UA_1, eta_vol, eta_s, R_coil_core, h_ref].
    data_points : list
        List of _PrecomputedDataPoint or CompressorDataPoint objects.
        When _PrecomputedDataPoint is used, suction properties are already
        cached and passed directly to the solver, avoiding redundant CoolProp
        calls across DE evaluations.
    motor_params : MotorParams
        Motor electrical parameters.
    config : CalibrationConfig
        Calibration configuration with normalization weights.

    Returns
    -------
    float
        Weighted sum-of-squares cost (non-negative).
    """
    params_dict = _vector_to_params(x)

    total_cost = 0.0
    sigma_Tm = config.sigma_Tm

    for dp in data_points:
        operating_point = {
            "RPM": dp.RPM,
            "Ps": dp.Ps,
            "Ts": dp.Ts,
            "Pd": dp.Pd,
            "I_peak": motor_params.I_peak,
        }

        solver_params = {
            **params_dict,
            "R": motor_params.R,
            "V_displ": motor_params.V_displ,
            "IronLoss": motor_params.IronLoss,
        }

        # Extract pre-computed suction properties if available
        hs_pre = getattr(dp, "_hs_precomputed", None)
        rho_pre = getattr(dp, "_rho_precomputed", None)

        try:
            result = solve_tm_iterative(
                operating_point, solver_params, alpha=config.alpha,
                max_iter=config.solver_max_iter,
                hs_precomputed=hs_pre, rho_precomputed=rho_pre,
            )
        except Exception:
            return 1e15  # Penalize infeasible parameter combinations

        # Tm residual
        Tm_pred = result.Tm
        Tm_meas = dp.Tm
        Tm_residual = (Tm_pred - Tm_meas) ** 2 / (sigma_Tm ** 2)

        # Torque residual (normalized by 5% of measured torque)
        Torque_pred = result.Torque
        Torque_meas = dp.Torque
        sigma_Torque = config.sigma_Torque_pct * max(abs(Torque_meas), 1e-6)
        Torque_residual = (Torque_pred - Torque_meas) ** 2 / (sigma_Torque ** 2)

        total_cost += Tm_residual + Torque_residual

    return total_cost


# ---------------------------------------------------------------------------
# Residual computation
# ---------------------------------------------------------------------------
def compute_residuals(
    data_points: list,
    params: dict,
    motor_params: MotorParams,
    config: CalibrationConfig,
) -> Tuple[list[float], list[float]]:
    """Compute per-point Tm and Torque residuals.

    Parameters
    ----------
    data_points : list
        CompressorDataPoint list.
    params : dict
        Calibration parameters {UA_0, UA_1, eta_vol, eta_s, R_coil_core, h_ref}.
    motor_params : MotorParams
        Motor electrical parameters.
    config : CalibrationConfig
        Calibration configuration.

    Returns
    -------
    tuple[list[float], list[float]]
        (residuals_Tm, residuals_Torque) — per-point residuals.
    """
    residuals_Tm: list[float] = []
    residuals_Torque: list[float] = []

    for dp in data_points:
        operating_point = {
            "RPM": dp.RPM,
            "Ps": dp.Ps,
            "Ts": dp.Ts,
            "Pd": dp.Pd,
            "I_peak": motor_params.I_peak,
        }

        solver_params = {
            "UA_0": params["UA_0"],
            "UA_1": params["UA_1"],
            "eta_vol": params["eta_vol"],
            "eta_s": params["eta_s"],
            "R_coil_core": params["R_coil_core"],
            "h_ref": params["h_ref"],
            "R": motor_params.R,
            "V_displ": motor_params.V_displ,
            "IronLoss": motor_params.IronLoss,
        }

        try:
            hs_pre = getattr(dp, "_hs_precomputed", None)
            rho_pre = getattr(dp, "_rho_precomputed", None)
            result = solve_tm_iterative(
                operating_point, solver_params, alpha=config.alpha,
                max_iter=config.solver_max_iter,
                hs_precomputed=hs_pre, rho_precomputed=rho_pre,
            )
            residuals_Tm.append(result.Tm - dp.Tm)
            residuals_Torque.append(result.Torque - dp.Torque)
        except Exception:
            residuals_Tm.append(float("nan"))
            residuals_Torque.append(float("nan"))

    return residuals_Tm, residuals_Torque


# ---------------------------------------------------------------------------
# Main calibration entry point
# ---------------------------------------------------------------------------
# @MX:ANCHOR: [AUTO] calibrate_compressor is the main public API for
# compressor calibration, called from the router layer.
# @MX:REASON: This function orchestrates multi-start optimization; incorrect
# logic here produces wrong calibrated parameters for all downstream analysis.
def calibrate_compressor(
    data_points: list,
    motor_params: MotorParams,
    config: CalibrationConfig = CalibrationConfig(),
    progress_callback: Callable | None = None,
) -> CalibrationResult:
    """Run multi-start differential evolution calibration.

    Parameters
    ----------
    data_points : list
        CompressorDataPoint list with measured data.
    motor_params : MotorParams
        Motor electrical parameters.
    config : CalibrationConfig
        Calibration configuration. Defaults used if not provided.
    progress_callback : callable | None
        Optional callback(event_dict) for SSE progress updates.

    Returns
    -------
    CalibrationResult
        Optimized parameters, metrics, and residuals.
    """
    t_start = time.perf_counter()

    ndim = len(PARAMETER_BOUNDS)
    bounds = PARAMETER_BOUNDS

    best_result = None
    best_cost = float("inf")
    loss_history: list[float] = []

    # Pre-compute suction properties for each unique (Ps, Ts) pair.
    # During calibration, operating conditions are fixed across all DE
    # evaluations — only model parameters change. Pre-computing these
    # avoids thousands of redundant CoolProp calls in the inner loop.
    data_points = _precompute_suction_states(data_points)

    for i_start in range(config.n_starts):
        seed = config.seed + i_start * 1000

        # Progress: start beginning
        if progress_callback is not None:
            progress_callback({
                "type": "progress",
                "start": i_start + 1,
                "n_starts": config.n_starts,
                "iter": 0,
                "cost": float("inf"),
                "elapsed": time.perf_counter() - t_start,
            })

        # Callback wrapper for differential_evolution
        de_iterations = [0]
        def _de_callback(xk: np.ndarray, convergence: float = None) -> None:
            de_iterations[0] += 1
            if progress_callback is not None and de_iterations[0] % 10 == 0:
                cost_val = objective_function(xk, data_points, motor_params, config)
                progress_callback({
                    "type": "progress",
                    "start": i_start + 1,
                    "n_starts": config.n_starts,
                    "iter": de_iterations[0],
                    "cost": cost_val,
                    "elapsed": time.perf_counter() - t_start,
                })

        try:
            result = differential_evolution(
                func=objective_function,
                bounds=bounds,
                args=(data_points, motor_params, config),
                strategy=config.strategy,
                maxiter=config.max_iter,
                popsize=config.popsize,
                tol=config.ftol,
                seed=seed,
                callback=_de_callback,
                polish=config.polish,
            )

            start_cost = float(result.fun)
            loss_history.append(start_cost)

            if start_cost < best_cost:
                best_cost = start_cost
                best_result = result

        except Exception:
            loss_history.append(float("inf"))

    elapsed = time.perf_counter() - t_start

    if best_result is None:
        raise RuntimeError("All calibration optimization starts failed")

    # Extract optimal parameters
    opt_params = _vector_to_params(best_result.x)

    # Compute residuals with optimal parameters
    residuals_Tm, residuals_Torque = compute_residuals(
        data_points, opt_params, motor_params, config,
    )

    # Compute metrics
    arr_Tm = np.array(residuals_Tm)
    arr_Torque = np.array(residuals_Torque)

    rmse_Tm = float(np.sqrt(np.mean(arr_Tm ** 2)))

    # Torque RMSE as percentage of mean measured torque
    mean_Torque_meas = float(np.mean([abs(dp.Torque) for dp in data_points]))
    rmse_Torque_abs = float(np.sqrt(np.mean(arr_Torque ** 2)))
    rmse_Torque = (rmse_Torque_abs / mean_Torque_meas) * 100.0 if mean_Torque_meas > 0 else 0.0

    # R-squared for Tm
    Tm_meas = np.array([dp.Tm for dp in data_points])
    Tm_pred = Tm_meas + arr_Tm  # predicted = measured + residual
    ss_tot_Tm = float(np.sum((Tm_meas - np.mean(Tm_meas)) ** 2))
    ss_res_Tm = float(np.sum(arr_Tm ** 2))
    r_squared_Tm = 1.0 - ss_res_Tm / ss_tot_Tm if ss_tot_Tm > 0 else 0.0

    # R-squared for Torque
    Torque_meas = np.array([dp.Torque for dp in data_points])
    arr_Torque_abs = np.array(residuals_Torque)
    ss_tot_Torque = float(np.sum((Torque_meas - np.mean(Torque_meas)) ** 2))
    ss_res_Torque = float(np.sum(arr_Torque_abs ** 2))
    r_squared_Torque = 1.0 - ss_res_Torque / ss_tot_Torque if ss_tot_Torque > 0 else 0.0

    # Progress: done
    if progress_callback is not None:
        progress_callback({
            "type": "done",
            "cost": best_cost,
            "elapsed": elapsed,
        })

    return CalibrationResult(
        params=opt_params,
        rmse_Tm=rmse_Tm,
        rmse_Torque=rmse_Torque,
        r_squared_Tm=r_squared_Tm,
        r_squared_Torque=r_squared_Torque,
        residuals_Tm=residuals_Tm,
        residuals_Torque=residuals_Torque,
        cost=best_cost,
        converged=bool(best_result.success),
        n_starts=config.n_starts,
        loss_history=loss_history,
        time_s=elapsed,
    )


# ---------------------------------------------------------------------------
# Cross-validation
# ---------------------------------------------------------------------------
def cross_validate(
    datasets: dict[str, list],
    motor_params: MotorParams,
    config: CalibrationConfig = CalibrationConfig(),
) -> CrossValidationResult:
    """Leave-one-sheet-out cross-validation.

    Parameters
    ----------
    datasets : dict[str, list]
        Sheet name -> list of CompressorDataPoint.
    motor_params : MotorParams
        Motor electrical parameters.
    config : CalibrationConfig
        Calibration configuration.

    Returns
    -------
    CrossValidationResult
        Per-fold results and aggregated metrics.
    """
    folds: list[CVFoldResult] = []
    sheet_names = list(datasets.keys())

    for held_out_name in sheet_names:
        # Train on all sheets except the held-out one
        train_points: list = []
        for name, points in datasets.items():
            if name != held_out_name:
                train_points.extend(points)

        test_points = datasets[held_out_name]

        if len(train_points) == 0 or len(test_points) == 0:
            continue

        # Calibrate on training set
        calib_result = calibrate_compressor(train_points, motor_params, config)

        # Compute residuals on train and test
        train_res_Tm, train_res_Torque = compute_residuals(
            train_points, calib_result.params, motor_params, config,
        )
        test_res_Tm, test_res_Torque = compute_residuals(
            test_points, calib_result.params, motor_params, config,
        )

        rmse_Tm_train = float(np.sqrt(np.mean(np.array(train_res_Tm) ** 2)))
        rmse_Tm_test = float(np.sqrt(np.mean(np.array(test_res_Tm) ** 2)))

        # Torque RMSE as percentage
        mean_train_Torque = float(np.mean([abs(dp.Torque) for dp in train_points]))
        mean_test_Torque = float(np.mean([abs(dp.Torque) for dp in test_points]))

        rmse_Torque_train_abs = float(np.sqrt(np.mean(np.array(train_res_Torque) ** 2)))
        rmse_Torque_test_abs = float(np.sqrt(np.mean(np.array(test_res_Torque) ** 2)))

        rmse_Torque_train = (rmse_Torque_train_abs / mean_train_Torque * 100.0) if mean_train_Torque > 0 else 0.0
        rmse_Torque_test = (rmse_Torque_test_abs / mean_test_Torque * 100.0) if mean_test_Torque > 0 else 0.0

        folds.append(CVFoldResult(
            held_out_sheet=held_out_name,
            rmse_Tm_train=rmse_Tm_train,
            rmse_Tm_test=rmse_Tm_test,
            rmse_Torque_train=rmse_Torque_train,
            rmse_Torque_test=rmse_Torque_test,
            generalization_gap_Tm=rmse_Tm_test - rmse_Tm_train,
            generalization_gap_Torque=rmse_Torque_test - rmse_Torque_train,
        ))

    mean_rmse_Tm = float(np.mean([f.rmse_Tm_test for f in folds])) if folds else 0.0
    mean_gap_Tm = float(np.mean([f.generalization_gap_Tm for f in folds])) if folds else 0.0
    n_folds_meeting_target = sum(1 for f in folds if f.rmse_Tm_test < _CV_TARGET_RMSE)

    return CrossValidationResult(
        folds=folds,
        mean_rmse_Tm=mean_rmse_Tm,
        mean_generalization_gap_Tm=mean_gap_Tm,
        n_folds_meeting_target=n_folds_meeting_target,
    )


# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------
def generate_synthetic_data(
    n_points: int = 8,
    params: dict | None = None,
    motor_params: MotorParams | None = None,
    noise_Tm: float = 0.5,
    noise_Torque: float = 0.02,
    rpms: list[float] | None = None,
) -> list:
    """Generate synthetic compressor data for testing.

    Uses realistic operating conditions for R1234yf compressor.

    Parameters
    ----------
    n_points : int
        Number of data points. Default 8.
    params : dict | None
        True calibration parameters. Defaults used if None.
    motor_params : MotorParams | None
        Motor electrical parameters. Defaults used if None.
    noise_Tm : float
        Standard deviation of Tm noise [degC]. Default 0.5.
    noise_Torque : float
        Fractional noise on Torque. Default 0.02.
    rpms : list[float] | None
        Custom RPM values. Defaults to standard test range if None.

    Returns
    -------
    list
        List of dataclass objects with fields matching CompressorDataPoint
        from compressor_data.py (RPM, Ps, Ts, Pd, Td, Tm, Torque, etc.).
    """
    if params is None:
        params = {
            "UA_0": 20.0, "UA_1": 1.0, "eta_vol": 0.75,
            "eta_s": 0.70, "R_coil_core": 0.05, "h_ref": 5.0,
        }
    if motor_params is None:
        motor_params = MotorParams()

    if rpms is None:
        rpms = [1500.0, 2000.0, 2500.0, 3000.0, 3500.0, 4000.0, 5000.0, 6000.0]

    # Take first n_points from rpms
    rpms = rpms[:n_points]

    # Operating conditions
    Ps = 500000.0   # 500 kPa suction pressure
    Ts = 15.0       # 15 degC suction temperature
    Pd = 2000000.0  # 2000 kPa discharge pressure

    rng = np.random.default_rng(42)

    data_points: list = []
    for rpm in rpms:
        operating_point = {
            "RPM": rpm,
            "Ps": Ps,
            "Ts": Ts,
            "Pd": Pd,
            "I_peak": motor_params.I_peak,
        }

        solver_params = {
            **params,
            "R": motor_params.R,
            "V_displ": motor_params.V_displ,
            "IronLoss": motor_params.IronLoss,
        }

        result = solve_tm_iterative(operating_point, solver_params, alpha=0.5, max_iter=50)

        # Add noise to create "measured" values
        Tm_meas = result.Tm + rng.normal(0, noise_Tm)
        Torque_meas = result.Torque * (1.0 + rng.normal(0, noise_Torque))

        # Build a data point object compatible with the calibration functions.
        # Use a simple namespace/object to avoid importing the full dataclass.
        dp = _SyntheticDataPoint(
            RPM=rpm,
            Ps=Ps,
            Ts=Ts,
            Pd=Pd,
            Td=result.Td,
            Tm=Tm_meas,
            Torque=Torque_meas,
            mdot=result.mdot,
            hm=result.hm,
            hd=result.hd,
            P_loss=result.MotorLoss,
        )
        data_points.append(dp)

    return data_points


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _PrecomputedDataPoint:
    """Proxy wrapper that delegates all attribute access to the original data
    point and adds pre-computed suction state properties.  Works with any
    data point type (Pydantic model, _SyntheticDataPoint, plain object).
    """

    __slots__ = ("_dp", "_hs_precomputed", "_rho_precomputed")

    def __init__(self, dp: object, hs: float, rho: float) -> None:
        self._dp = dp
        self._hs_precomputed = hs
        self._rho_precomputed = rho

    def __getattr__(self, name: str):
        return getattr(self._dp, name)


def _precompute_suction_states(data_points: list) -> list:
    """Pre-compute suction enthalpy and density for each data point.

    During calibration, operating conditions (Ps, Ts) are fixed. This
    computes hs and rho_s once per unique (Ps, Ts) pair and wraps each
    data point so the inner solver loop skips redundant CoolProp calls.

    Parameters
    ----------
    data_points : list
        Data points with .Ps and .Ts attributes.

    Returns
    -------
    list
        Wrapped data points exposing all original attributes plus
        _hs_precomputed and _rho_precomputed.
    """
    cache: dict[tuple[float, float], tuple[float, float]] = {}
    result: list = []
    for dp in data_points:
        key = (dp.Ps, dp.Ts)
        if key not in cache:
            cache[key] = (
                get_enthalpy(dp.Ps, dp.Ts),
                get_density(dp.Ps, dp.Ts),
            )
        hs_val, rho_val = cache[key]
        result.append(_PrecomputedDataPoint(dp, hs_val, rho_val))
    return result


class _SyntheticDataPoint:
    """Minimal data point for synthetic test data."""

    __slots__ = (
        "RPM", "Ps", "Ts", "Pd", "Td", "Tm", "Torque",
        "mdot", "hm", "hd", "P_loss",
    )

    def __init__(
        self,
        RPM: float, Ps: float, Ts: float, Pd: float,
        Td: float, Tm: float, Torque: float,
        mdot: float, hm: float, hd: float, P_loss: float,
    ):
        self.RPM = RPM
        self.Ps = Ps
        self.Ts = Ts
        self.Pd = Pd
        self.Td = Td
        self.Tm = Tm
        self.Torque = Torque
        self.mdot = mdot
        self.hm = hm
        self.hd = hd
        self.P_loss = P_loss


def _vector_to_params(x: np.ndarray) -> dict:
    """Convert optimization vector to parameter dict."""
    return dict(zip(PARAMETER_NAMES, x.tolist()))

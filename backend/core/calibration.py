"""4-parameter calibration engine for the 3-node thermal model.

Optimises [R1, R2, h_nat, h_rpm] in log-space using multi-start L-BFGS-B
with tail-biased weighting and steady-state anchoring.

Reference: PRD v1.0 Section 5
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import minimize

from .loss_model import CoilParams, SimpleIronLoss, make_simple_loss_fn
from .motor_geometry import (
    compute_initial_resistances,
    compute_thermal_masses,
)
from .thermal_model import simulate_3node_fast, simulate_3node_final


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CalibSettings:
    """Calibration hyper-parameters."""

    n_starts: int = 3
    tail_gamma: float = 2.0  # exponent for tail weight ramp
    ss_penalty: float = 5.0  # multiplier for last-20% residuals
    normalize_per_file: bool = True
    # Free-parameter initial guesses (None = physics estimate)
    R1_init: float | None = None
    R2_init: float | None = None
    h_nat_init: float = 10.0
    h_rpm_init: float = 0.02
    # Bounds (None = auto)
    R1_bounds: Tuple[float, float] | None = None
    R2_bounds: Tuple[float, float] | None = None


@dataclass
class CalibResult:
    """Calibration output."""

    R1: float  # degC/W
    R2: float  # degC/W
    h_nat: float  # W/(m^2*K)
    h_rpm: float  # W/(m^2*K)/sqrt(RPM)
    rmse: float  # degC
    r_squared: float
    T_coil_sim: np.ndarray  # degC
    T_core_sim: np.ndarray  # degC
    T_housing_sim: np.ndarray  # degC
    residuals: np.ndarray  # degC
    time_s: float  # wall-clock seconds
    converged: bool
    loss_history: List[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Weight vector
# ---------------------------------------------------------------------------
def _build_weights(n: int, tail_fraction: float = 0.2, tail_gamma: float = 2.0) -> np.ndarray:
    """Build tail-biased weight vector.

    The first 80% of points get weight 1.  The last 20% get weight
    ramping from 1 to (1 + tail_gamma) linearly.

    Parameters
    ----------
    n : int
        Number of data points.
    tail_fraction : float
        Fraction of tail to emphasise. Default 0.2.
    tail_gamma : float
        Additional weight at the very end. Default 2.0.

    Returns
    -------
    np.ndarray
        Weight vector of shape (n,).
    """
    w = np.ones(n)
    tail_start = int(n * (1.0 - tail_fraction))
    if tail_start < n:
        tail_len = n - tail_start
        ramp = np.linspace(1.0, 1.0 + tail_gamma, tail_len)
        w[tail_start:] = ramp
    return w


# ---------------------------------------------------------------------------
# Objective function
# ---------------------------------------------------------------------------
def _make_objective(
    time_array: np.ndarray,
    I_array: np.ndarray,
    rpm_array: np.ndarray,
    T_amb_array: np.ndarray,
    T_coil_meas: np.ndarray,
    C_coil: float,
    C_core: float,
    C_housing: float,
    A_housing: float,
    loss_fn: Callable,
    weights: np.ndarray,
    delta_T_ss: float,
    ss_penalty: float,
    T_init: float,
) -> Callable[[np.ndarray], float]:
    """Build the scalar objective for L-BFGS-B (log-space parameterisation).

    Decision variable ``x = [log(R1), log(R2), log(h_nat), log(h_rpm)]``.
    """

    def objective(x: np.ndarray) -> float:
        R1 = math.exp(x[0])
        R2 = math.exp(x[1])
        h_nat = math.exp(x[2])
        h_rpm = math.exp(x[3])

        try:
            result = simulate_3node_fast(
                time_array=time_array,
                I_array=I_array,
                rpm_array=rpm_array,
                T_amb_array=T_amb_array,
                C_coil=C_coil, C_core=C_core, C_housing=C_housing,
                R1=R1, R2=R2, h_nat=h_nat, h_rpm=h_rpm,
                A_housing=A_housing,
                loss_fn=loss_fn,
                T_init=T_init,
            )
        except Exception:
            return 1e15  # infeasible — penalise heavily

        residuals = result.T_coil - T_coil_meas
        # Normalise by delta_T_ss to make objective scale-invariant
        if delta_T_ss > 0.0:
            norm_resid = residuals / delta_T_ss
        else:
            norm_resid = residuals

        # Weighted SSE
        sse = float(np.sum(weights * norm_resid**2))

        # SS anchor: extra penalty on last 20%
        n = len(residuals)
        tail_start = int(n * 0.8)
        if tail_start < n and delta_T_ss > 0.0:
            tail_resid = residuals[tail_start:] / delta_T_ss
            ss_term = ss_penalty * float(np.mean(tail_resid**2))
            sse += ss_term

        return sse

    return objective


# ---------------------------------------------------------------------------
# Main calibration entry point
# ---------------------------------------------------------------------------
def run_calibration(
    time_array: np.ndarray,
    I_array: np.ndarray,
    rpm_array: np.ndarray,
    T_amb_array: np.ndarray,
    T_coil_meas: np.ndarray,
    C_coil: float,
    C_core: float,
    C_housing: float,
    A_housing: float,
    loss_fn: Callable,
    settings: CalibSettings | None = None,
    progress_callback: Callable[[Dict], None] | None = None,
) -> CalibResult:
    """Run 4-parameter calibration via multi-start L-BFGS-B.

    Parameters
    ----------
    time_array, I_array, rpm_array, T_amb_array : np.ndarray
        Input time series (shape N).
    T_coil_meas : np.ndarray
        Measured coil temperature [degC], shape (N,).
    C_coil, C_core, C_housing : float
        Thermal capacitances [J/degC].
    A_housing : float
        Housing surface area [m^2].
    loss_fn : callable
        ``(I, T_coil, RPM) -> (Q_cu, Q_iron)``.
    settings : CalibSettings | None
        Calibration hyper-parameters.  Uses defaults if None.
    progress_callback : callable | None
        Optional ``callback(event_dict)`` for SSE progress updates.

    Returns
    -------
    CalibResult
        Optimised parameters, metrics, and simulated temperatures.

    Reference
    ---------
    PRD Section 5.
    """
    if settings is None:
        settings = CalibSettings()

    t_start_wall = time.perf_counter()

    # Initial temperature
    T_init = float(T_coil_meas[0])

    # Steady-state delta T for normalisation
    delta_T_ss = float(T_coil_meas[-1] - T_amb_array[-1])
    if abs(delta_T_ss) < 1.0:
        delta_T_ss = 1.0  # avoid division by near-zero

    # Weights
    weights = _build_weights(
        len(time_array),
        tail_fraction=0.2,
        tail_gamma=settings.tail_gamma,
    )

    # Initial guess in log-space
    R1_0 = settings.R1_init if settings.R1_init is not None else 0.5
    R2_0 = settings.R2_init if settings.R2_init is not None else 0.1
    x0 = np.log([R1_0, R2_0, settings.h_nat_init, settings.h_rpm_init])

    # Bounds (log-space)
    lb = np.log([0.01, 0.01, 2.0, 1e-4])
    ub = np.log([10.0, 5.0, 100.0, 2.0])

    # Override with explicit bounds if provided
    if settings.R1_bounds is not None:
        lb[0] = math.log(max(settings.R1_bounds[0], 1e-6))
        ub[0] = math.log(settings.R1_bounds[1])
    if settings.R2_bounds is not None:
        lb[1] = math.log(max(settings.R2_bounds[0], 1e-6))
        ub[1] = math.log(settings.R2_bounds[1])

    bounds = list(zip(lb, ub))

    # Objective
    objective = _make_objective(
        time_array=time_array,
        I_array=I_array,
        rpm_array=rpm_array,
        T_amb_array=T_amb_array,
        T_coil_meas=T_coil_meas,
        C_coil=C_coil, C_core=C_core, C_housing=C_housing,
        A_housing=A_housing,
        loss_fn=loss_fn,
        weights=weights,
        delta_T_ss=delta_T_ss,
        ss_penalty=settings.ss_penalty,
        T_init=T_init,
    )

    # Multi-start optimisation
    best_result = None
    best_loss = float("inf")
    loss_history: List[float] = []

    # Generate starting points: nominal + perturbations
    starts = [x0.copy()]
    rng = np.random.default_rng(42)
    for _ in range(max(settings.n_starts - 1, 0)):
        perturb = x0 + rng.normal(0, 0.5, size=4)
        perturb = np.clip(perturb, lb, ub)
        starts.append(perturb)

    for i_start, x_start in enumerate(starts):
        if progress_callback is not None:
            progress_callback({
                "type": "progress",
                "start": i_start + 1,
                "n_starts": settings.n_starts,
                "iter": 0,
                "rmse": float("inf"),
                "elapsed": time.perf_counter() - t_start_wall,
            })

        res = minimize(
            objective,
            x_start,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 500, "ftol": 1e-12},
        )

        loss_history.append(float(res.fun))

        if float(res.fun) < best_loss:
            best_loss = float(res.fun)
            best_result = res

    if best_result is None:
        raise RuntimeError("All optimisation starts failed")

    # Extract optimal parameters
    x_opt = best_result.x
    R1_opt = math.exp(x_opt[0])
    R2_opt = math.exp(x_opt[1])
    h_nat_opt = math.exp(x_opt[2])
    h_rpm_opt = math.exp(x_opt[3])

    # Final simulation with tight tolerances
    final_sim = simulate_3node_final(
        time_array=time_array,
        I_array=I_array,
        rpm_array=rpm_array,
        T_amb_array=T_amb_array,
        C_coil=C_coil, C_core=C_core, C_housing=C_housing,
        R1=R1_opt, R2=R2_opt, h_nat=h_nat_opt, h_rpm=h_rpm_opt,
        A_housing=A_housing,
        loss_fn=loss_fn,
        T_init=T_init,
    )

    residuals = final_sim.T_coil - T_coil_meas
    rmse = float(np.sqrt(np.mean(residuals**2)))

    # R-squared
    ss_tot = float(np.sum((T_coil_meas - np.mean(T_coil_meas))**2))
    ss_res = float(np.sum(residuals**2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else 0.0

    elapsed = time.perf_counter() - t_start_wall

    return CalibResult(
        R1=R1_opt,
        R2=R2_opt,
        h_nat=h_nat_opt,
        h_rpm=h_rpm_opt,
        rmse=rmse,
        r_squared=r_squared,
        T_coil_sim=final_sim.T_coil,
        T_core_sim=final_sim.T_core,
        T_housing_sim=final_sim.T_housing,
        residuals=residuals,
        time_s=elapsed,
        converged=best_result.success,
        loss_history=loss_history,
    )

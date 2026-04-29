"""3-node lumped-parameter thermal ODE model.

Thermal network topology::

    Q_gen
      |
    [T_coil] ---R1--- [T_core] ---R2--- [T_housing] ---R3(RPM)--- T_amb
     C_coil            C_core             C_housing

Node 1 (T_coil) is the only measured temperature.  Nodes 2-3 are internal
states estimated by the ODE solver.

Reference: PRD v1.0 Section 4.1-4.4
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from scipy.integrate import solve_ivp


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SimResult:
    """Output of a 3-node thermal simulation."""

    T_coil: np.ndarray  # degC
    T_core: np.ndarray  # degC
    T_housing: np.ndarray  # degC
    time: np.ndarray  # s
    Q_gen: np.ndarray  # W  (total heat generation per time step)


# ---------------------------------------------------------------------------
# Convective resistance
# ---------------------------------------------------------------------------
def R3_at_rpm(
    rpm: float,
    h_nat: float,
    h_rpm: float,
    A_housing: float,
) -> float:
    """Compute housing-to-ambient thermal resistance at a given RPM.

    .. math::

        R_3 = \\frac{1}{(h_{nat} + h_{rpm} \\times \\sqrt{RPM}) \\times A_{housing}}

    Parameters
    ----------
    rpm : float
        Rotor speed [RPM].  Use 0 for natural convection.
    h_nat : float
        Natural convection coefficient [W/(m^2*K)].
    h_rpm : float
        Forced convection coefficient [W/(m^2*K)/sqrt(RPM)].
    A_housing : float
        Housing outer surface area [m^2].

    Returns
    -------
    float
        R3 [degC/W].
    """
    sqrt_rpm = math.sqrt(max(rpm, 0.0))
    h_total = h_nat + h_rpm * sqrt_rpm
    if h_total <= 0.0:
        return 1e12  # effectively infinite resistance
    return 1.0 / (h_total * A_housing)


# ---------------------------------------------------------------------------
# ODE right-hand side
# ---------------------------------------------------------------------------
def _build_ode_rhs(
    C_coil: float,
    C_core: float,
    C_housing: float,
    R1: float,
    R2: float,
    h_nat: float,
    h_rpm: float,
    A_housing: float,
    loss_fn: Callable[[float, float, float], Tuple[float, float]],
    time_interp_I: Callable[[float], float],
    time_interp_RPM: Callable[[float], float],
    time_interp_Tamb: Callable[[float], float],
) -> Callable[[float, np.ndarray], np.ndarray]:
    """Return the ODE right-hand side function for solve_ivp."""

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        T1, T2, T3 = y  # coil, core, housing

        I_t = time_interp_I(t)
        rpm_t = time_interp_RPM(t)
        T_amb_t = time_interp_Tamb(t)

        # Heat generation
        Q_cu, Q_iron = loss_fn(I_t, T1, rpm_t)
        Q_gen = Q_cu + Q_iron

        # Thermal resistances
        R3 = R3_at_rpm(rpm_t, h_nat, h_rpm, A_housing)

        # Heat flows
        Q12 = (T1 - T2) / R1
        Q23 = (T2 - T3) / R2
        Q3a = (T3 - T_amb_t) / R3

        # ODEs (PRD 4.2)
        dT1 = (Q_gen - Q12) / C_coil
        dT2 = (Q12 - Q23) / C_core
        dT3 = (Q23 - Q3a) / C_housing

        return np.array([dT1, dT2, dT3])

    return rhs


# ---------------------------------------------------------------------------
# Interpolation helpers
# ---------------------------------------------------------------------------
def _make_interp(x: np.ndarray, y: np.ndarray) -> Callable[[float], float]:
    """Create a linear interpolation callable for scalar lookup."""
    # np.interp handles edge values (clamps to boundary)
    def interp_fn(t: float) -> float:
        return float(np.interp(t, x, y))

    return interp_fn


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------
def simulate_3node(
    time_array: np.ndarray,
    I_array: np.ndarray,
    rpm_array: np.ndarray,
    T_amb_array: np.ndarray,
    C_coil: float,
    C_core: float,
    C_housing: float,
    R1: float,
    R2: float,
    h_nat: float,
    h_rpm: float,
    A_housing: float,
    loss_fn: Callable[[float, float, float], Tuple[float, float]],
    T_init: float | None = None,
    rtol: float = 1e-3,
    atol: float = 1e-2,
    mode: str = "fast",
) -> SimResult:
    """Integrate the 3-node thermal ODE system.

    Parameters
    ----------
    time_array : np.ndarray
        Time vector [s], shape (N,).
    I_array : np.ndarray
        Phase current [A], shape (N,).
    rpm_array : np.ndarray
        Rotor speed [RPM], shape (N,).
    T_amb_array : np.ndarray
        Ambient temperature [degC], shape (N,).
    C_coil, C_core, C_housing : float
        Thermal capacitances [J/degC].
    R1, R2 : float
        Internal thermal resistances [degC/W].
    h_nat, h_rpm : float
        Convection coefficients [W/(m^2*K)] and [W/(m^2*K)/sqrt(RPM)].
    A_housing : float
        Housing outer surface area [m^2].
    loss_fn : callable
        ``(I, T_coil, RPM) -> (Q_copper, Q_iron)``.
    T_init : float | None
        Initial temperature for all nodes.  Defaults to T_coil[0].
    rtol, atol : float
        Solver tolerances.
    mode : str
        ``"fast"`` (loose tol, subsampled) or ``"final"`` (tight tol, full).

    Returns
    -------
    SimResult
        Temperature arrays and heat generation history.

    Reference
    ---------
    PRD Section 4.2.
    """
    if len(time_array) < 2:
        raise ValueError("time_array must have at least 2 points")

    # Apply mode defaults
    if mode == "fast":
        rtol = 1e-2
        atol = 1.0
    elif mode == "final":
        rtol = 1e-6
        atol = 1e-3

    # Initial condition
    if T_init is None:
        T_init = float(T_amb_array[0])
    y0 = np.array([T_init, T_init, T_init])

    # Build interpolation functions for time-varying inputs
    interp_I = _make_interp(time_array, I_array)
    interp_RPM = _make_interp(time_array, rpm_array)
    interp_Tamb = _make_interp(time_array, T_amb_array)

    # Build ODE
    rhs = _build_ode_rhs(
        C_coil=C_coil,
        C_core=C_core,
        C_housing=C_housing,
        R1=R1,
        R2=R2,
        h_nat=h_nat,
        h_rpm=h_rpm,
        A_housing=A_housing,
        loss_fn=loss_fn,
        time_interp_I=interp_I,
        time_interp_RPM=interp_RPM,
        time_interp_Tamb=interp_Tamb,
    )

    # Evaluation points
    t_span = (float(time_array[0]), float(time_array[-1]))
    t_eval = time_array.astype(float)

    # For fast mode, subsample to ~300 points to speed up optimization
    if mode == "fast" and len(t_eval) > 300:
        idx = np.linspace(0, len(t_eval) - 1, 300, dtype=int)
        t_eval_sub = t_eval[idx]
    else:
        t_eval_sub = t_eval
        idx = np.arange(len(t_eval))

    # Solve
    sol = solve_ivp(
        rhs,
        t_span,
        y0,
        method="LSODA",
        t_eval=t_eval_sub,
        rtol=rtol,
        atol=atol,
    )

    if sol.status != 0:
        raise RuntimeError(f"ODE solver failed: {sol.message}")

    # Map back to full time grid if subsampled
    T_coil_sub = sol.y[0]
    T_core_sub = sol.y[1]
    T_housing_sub = sol.y[2]

    if mode == "fast" and len(t_eval_sub) < len(time_array):
        T_coil_full = np.interp(time_array, t_eval_sub, T_coil_sub)
        T_core_full = np.interp(time_array, t_eval_sub, T_core_sub)
        T_housing_full = np.interp(time_array, t_eval_sub, T_housing_sub)
    else:
        T_coil_full = T_coil_sub
        T_core_full = T_core_sub
        T_housing_full = T_housing_sub

    # Compute Q_gen history on the output time grid
    Q_gen = np.zeros(len(time_array))
    for i in range(len(time_array)):
        Q_cu, Q_iron = loss_fn(
            float(I_array[i]),
            float(T_coil_full[i]),
            float(rpm_array[i]),
        )
        Q_gen[i] = Q_cu + Q_iron

    return SimResult(
        T_coil=T_coil_full,
        T_core=T_core_full,
        T_housing=T_housing_full,
        time=time_array.copy(),
        Q_gen=Q_gen,
    )


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------
def simulate_3node_fast(
    time_array: np.ndarray,
    I_array: np.ndarray,
    rpm_array: np.ndarray,
    T_amb_array: np.ndarray,
    C_coil: float,
    C_core: float,
    C_housing: float,
    R1: float,
    R2: float,
    h_nat: float,
    h_rpm: float,
    A_housing: float,
    loss_fn: Callable[[float, float, float], Tuple[float, float]],
    T_init: float | None = None,
) -> SimResult:
    """Fast simulation with loose tolerances (for calibration)."""
    return simulate_3node(
        time_array=time_array,
        I_array=I_array,
        rpm_array=rpm_array,
        T_amb_array=T_amb_array,
        C_coil=C_coil, C_core=C_core, C_housing=C_housing,
        R1=R1, R2=R2, h_nat=h_nat, h_rpm=h_rpm,
        A_housing=A_housing,
        loss_fn=loss_fn,
        T_init=T_init,
        mode="fast",
    )


def simulate_3node_final(
    time_array: np.ndarray,
    I_array: np.ndarray,
    rpm_array: np.ndarray,
    T_amb_array: np.ndarray,
    C_coil: float,
    C_core: float,
    C_housing: float,
    R1: float,
    R2: float,
    h_nat: float,
    h_rpm: float,
    A_housing: float,
    loss_fn: Callable[[float, float, float], Tuple[float, float]],
    T_init: float | None = None,
) -> SimResult:
    """Final simulation with tight tolerances (for display)."""
    return simulate_3node(
        time_array=time_array,
        I_array=I_array,
        rpm_array=rpm_array,
        T_amb_array=T_amb_array,
        C_coil=C_coil, C_core=C_core, C_housing=C_housing,
        R1=R1, R2=R2, h_nat=h_nat, h_rpm=h_rpm,
        A_housing=A_housing,
        loss_fn=loss_fn,
        T_init=T_init,
        mode="final",
    )

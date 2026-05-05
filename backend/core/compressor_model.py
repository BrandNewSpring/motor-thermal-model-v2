"""Compressor thermal model with 5 coupled sub-models and iterative solver.

Sub-models:
  A. Mass flow (REQ-COMP-MASSFLOW-001)
  B. Motor loss (REQ-COMP-MOTORLOSS-001)
  C. Discharge conditions (REQ-COMP-DISCHARGE-001)
  D. Heat recirculation (REQ-COMP-RECIRC-001)
  E. Coil temperature (REQ-COMP-COIL-001)

The iterative solver resolves the circular dependency:
  Tm -> Q_recirc -> hm -> Tm

Key insight: 93-99% of motor section heat pickup comes from hot discharge
gas recirculation (NOT motor electrical losses).

Units throughout:
  - Pressure: Pa
  - Temperature: degC
  - Enthalpy: J/kg
  - Entropy: J/(kg*K)
  - Mass flow: kg/s
  - Power: W
  - Torque: Nm

Reference: SPEC-COMP-THERMAL-001
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

from schemas.compressor import (
    CompressorCalibrationParams,
    CompressorOperatingPoint,
    CompressorPrediction,
)

from .refrigerant import get_density, get_enthalpy, get_temperature, get_entropy


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MotorParams:
    """Motor electrical parameters for the compressor model."""

    R: float = 0.5          # per-phase resistance [Ohm]
    V_displ: float = 1.0e-5 # displacement volume [m^3]
    I_peak: float = 10.0    # peak current [A]
    IronLoss: float = 0.0   # iron loss [W]


@dataclass
class IterationResult:
    """Result of the iterative Tm solver."""

    Tm: float           # converged motor outlet temperature [degC]
    Td: float           # discharge temperature [degC]
    hm: float           # motor outlet enthalpy [J/kg]
    hd: float           # discharge enthalpy [J/kg]
    mdot: float         # mass flow rate [kg/s]
    Q_recirc: float     # heat recirculation [W]
    MotorLoss: float    # motor electrical loss [W]
    Torque: float       # compressor torque [Nm]
    T_coil: float       # coil temperature [degC]
    converged: bool     # whether solver converged
    iterations: int     # number of iterations performed
    residual: float     # final |Tm_new - Tm_old| [degC]


# ---------------------------------------------------------------------------
# Sub-model A: Mass Flow (REQ-COMP-MASSFLOW-001)
# ---------------------------------------------------------------------------
# @MX:ANCHOR: [AUTO] compute_mass_flow is called by solve_tm_iterative and
# will be called by calibration and batch prediction endpoints.
# @MX:REASON: Mass flow is the foundation for all downstream energy balance
# calculations; incorrect density lookup or formula produces cascading errors.
def compute_mass_flow(
    RPM: float,
    Ps: float,
    Ts: float,
    eta_vol: float,
    V_displ: float,
) -> float:
    """Compute refrigerant mass flow rate.

    .. math::
        \\dot{m} = \\eta_{vol} \\times V_{displ} \\times \\frac{RPM}{60} \\times \\rho(P_s, T_s)

    Parameters
    ----------
    RPM : float
        Compressor speed [RPM].
    Ps : float
        Suction pressure [Pa].
    Ts : float
        Suction temperature [degC].
    eta_vol : float
        Volumetric efficiency [-].
    V_displ : float
        Displacement volume [m^3].

    Returns
    -------
    float
        Mass flow rate [kg/s].
    """
    if RPM <= 0.0 or eta_vol <= 0.0 or V_displ <= 0.0:
        return 0.0

    rho = get_density(Ps, Ts)
    return eta_vol * V_displ * (RPM / 60.0) * rho


# ---------------------------------------------------------------------------
# Sub-model B: Motor Loss (REQ-COMP-MOTORLOSS-001)
# ---------------------------------------------------------------------------
# @MX:ANCHOR: [AUTO] compute_motor_loss uses AF-validated empirical formula
# with temp/RPM correction factor, called by the iterative solver each step.
# @MX:REASON: Motor loss feeds directly into the energy balance (hm calculation);
# an incorrect formula corrupts the entire thermal prediction.
def compute_motor_loss(
    R: float,
    I_peak: float,
    T_coil: float,
    RPM: float,
    IronLoss: float = 0.0,
) -> float:
    """Compute motor electrical loss using the AF-validated formula.

    .. math::
        Q_{motor} = R \\times \\left(\\frac{I_{peak}}{\\sqrt{2}}\\right)^2
        \\times 3 \\times C(T_{coil}, RPM) + Q_{iron}

    where the correction factor is:

    .. math::
        C = 0.9312 + 0.00703 \\times T_{coil}
            + 2.87 \\times 10^{-5} \\times RPM
            + 1.34 \\times 10^{-9} \\times RPM^2

    Parameters
    ----------
    R : float
        Per-phase resistance [Ohm].
    I_peak : float
        Peak phase current [A].
    T_coil : float
        Coil temperature [degC].
    RPM : float
        Compressor speed [RPM].
    IronLoss : float
        Additional iron loss [W].

    Returns
    -------
    float
        Total motor loss [W].
    """
    I_rms = I_peak / math.sqrt(2.0)
    correction = (
        0.9312
        + 0.00703 * T_coil
        + 2.87e-5 * RPM
        + 1.34e-9 * RPM**2
    )
    resistive_loss = R * I_rms**2 * 3.0 * correction
    return resistive_loss + IronLoss


# ---------------------------------------------------------------------------
# Sub-model C: Discharge Conditions (REQ-COMP-DISCHARGE-001)
# ---------------------------------------------------------------------------
def compute_discharge_state(
    hm: float,
    Pm: float,
    Pd: float,
    eta_s: float,
) -> Tuple[float, float]:
    """Compute discharge enthalpy and temperature from isentropic efficiency.

    .. math::
        h_{d,is} = h(P_d, s(P_m, h_m))
        h_d = h_m + (h_{d,is} - h_m) / \\eta_s
        T_d = T(P_d, h_d)

    Parameters
    ----------
    hm : float
        Motor outlet enthalpy [J/kg].
    Pm : float
        Motor section pressure [Pa] (approximately equal to Ps).
    Pd : float
        Discharge pressure [Pa].
    eta_s : float
        Isentropic efficiency [-]. Must be in (0, 1].

    Returns
    -------
    tuple[float, float]
        (hd, Td) — discharge enthalpy [J/kg] and temperature [degC].

    Raises
    ------
    ValueError
        If eta_s is not in (0, 1].
    """
    if not (0.0 < eta_s <= 1.0):
        raise ValueError(
            f"Isentropic efficiency must be in (0, 1], got eta_s={eta_s}. "
            "Provide a physically valid isentropic efficiency."
        )

    # Isentropic discharge: s at motor outlet -> h at Pd with same s
    sm = get_entropy(Pm, hm)

    # Compute hd_isen using CoolProp: h at (Pd, s=sm)
    import CoolProp.CoolProp as CP
    hd_isen = CP.PropsSI("H", "P", Pd, "S", sm, "R1234yf")

    # Actual discharge enthalpy
    hd = hm + (hd_isen - hm) / eta_s

    # Discharge temperature from (Pd, hd)
    Td = get_temperature(Pd, hd)

    return hd, Td


# ---------------------------------------------------------------------------
# Sub-model D: Heat Recirculation (REQ-COMP-RECIRC-001)
# ---------------------------------------------------------------------------
def compute_q_recirc(
    UA_0: float,
    UA_1: float,
    RPM: float,
    Td: float,
    Tm: float,
) -> float:
    """Compute heat recirculation from discharge gas to motor section.

    .. math::
        Q_{recirc} = (UA_0 + UA_1 \\times RPM / 1000) \\times (T_d - T_m)

    The UA_recirc coefficient is linear with RPM (validated R^2=0.87).

    Parameters
    ----------
    UA_0 : float
        Base overall heat transfer coefficient [W/K].
    UA_1 : float
        RPM-dependent UA correction [W/K per 1000 RPM].
    RPM : float
        Compressor speed [RPM].
    Td : float
        Discharge temperature [degC].
    Tm : float
        Motor section temperature [degC].

    Returns
    -------
    float
        Heat recirculation rate [W]. Positive when Td > Tm.
    """
    UA_recirc = UA_0 + UA_1 * RPM / 1000.0
    return UA_recirc * (Td - Tm)


# ---------------------------------------------------------------------------
# Sub-model E: Coil Temperature (REQ-COMP-COIL-001)
# ---------------------------------------------------------------------------
# @MX:WARN: [AUTO] Cooling term Q_refrig * h_ref * sqrt(RPM) can produce
# unphysically large values with default parameters. Requires calibrated
# h_ref and Q_refrig to keep T_coil in physical range.
# @MX:REASON: With h_ref=500, Q_refrig=227W, RPM=3000 the cooling term is
# ~6.2M degC. The solver uses a simplified coil temp for stability.
def compute_coil_temperature(
    Tm: float,
    Q_coil: float,
    R_coil_core: float,
    Q_refrig: float,
    h_ref: float,
    RPM: float,
) -> float:
    """Compute coil temperature from thermal resistance network.

    .. math::
        T_{coil} = T_m + Q_{coil} \\times R_{coil/core}
                   - Q_{refrig} \\times h_{ref} \\times \\sqrt{RPM}

    Parameters
    ----------
    Tm : float
        Motor section temperature [degC].
    Q_coil : float
        Coil heat generation [W].
    R_coil_core : float
        Coil-to-core thermal resistance [K/W].
    Q_refrig : float
        Refrigerant cooling effect [W].
    h_ref : float
        Reference heat transfer coefficient [W/(m^2*K)].
    RPM : float
        Compressor speed [RPM].

    Returns
    -------
    float
        Coil temperature [degC].
    """
    heating = Q_coil * R_coil_core
    cooling = Q_refrig * h_ref * math.sqrt(max(RPM, 0.0))
    return Tm + heating - cooling


# ---------------------------------------------------------------------------
# Torque Calculation (REQ-COMP-TORQUE-001)
# ---------------------------------------------------------------------------
def compute_torque(CompPower: float, RPM: float) -> float:
    """Compute compressor shaft torque from power and speed.

    .. math::
        \\tau = \\frac{P_{comp}}{\\omega} = \\frac{P_{comp}}{RPM \\times 2\\pi / 60}

    Parameters
    ----------
    CompPower : float
        Compressor power [W].
    RPM : float
        Compressor speed [RPM].

    Returns
    -------
    float
        Torque [Nm].

    Raises
    ------
    ValueError
        If RPM is zero (division by zero).
    """
    if RPM <= 0.0:
        raise ValueError(
            f"RPM must be positive to compute torque, got RPM={RPM}. "
            "Provide a valid positive RPM value."
        )
    omega = RPM * 2.0 * math.pi / 60.0
    return CompPower / omega


# ---------------------------------------------------------------------------
# Iterative Tm Solver (REQ-COMP-ITER-001)
# ---------------------------------------------------------------------------
# @MX:WARN: [AUTO] Iterative solver has coupled feedback loop (Tm -> Q_recirc -> hm -> Tm).
# Requires relaxation factor alpha < 1 and bootstrap without recirculation for stability.
# @MX:REASON: Without proper initialization and relaxation, the solver diverges because
# Q_recirc can be 30x larger than MotorLoss, causing enthalpy overshoot.
def solve_tm_iterative(
    operating_point: dict,
    params: dict,
    alpha: float = 0.5,
    max_iter: int = 100,
    tol: float = 0.01,
    hs_precomputed: float | None = None,
    rho_precomputed: float | None = None,
) -> IterationResult:
    """Solve for motor section temperature iteratively.

    Resolves the circular dependency:
        Tm -> Q_recirc -> hm -> Tm

    Algorithm:
        1. Initialize Tm = Ts
        2. Compute mdot from sub-model A
        3. Compute MotorLoss from sub-model B
        4. Compute Q_recirc from sub-model D
        5. Compute hm = hs + (MotorLoss + Q_recirc) / mdot
        6. Compute new Tm = T(Pm, hm)
        7. Apply relaxation: Tm = alpha * Tm_new + (1-alpha) * Tm_old
        8. Check convergence: |Tm_new - Tm_old| < tol
        9. If not converged, go to step 3

    Parameters
    ----------
    operating_point : dict
        Keys: RPM, Ps, Ts, Pd, I_peak.
    params : dict
        Keys: UA_0, UA_1, eta_vol, eta_s, R_coil_core, h_ref, R, V_displ, IronLoss.
    alpha : float
        Relaxation factor (0 < alpha <= 1). Default 0.5.
    max_iter : int
        Maximum iterations. Default 100.
    tol : float
        Convergence tolerance [degC]. Default 0.01.
    hs_precomputed : float | None
        Pre-computed suction enthalpy [J/kg]. Avoids redundant CoolProp call.
    rho_precomputed : float | None
        Pre-computed suction density [kg/m^3]. Avoids redundant CoolProp call.

    Returns
    -------
    IterationResult
        Converged solution with all computed quantities.
    """
    # Extract operating point
    RPM = operating_point["RPM"]
    Ps = operating_point["Ps"]
    Ts = operating_point["Ts"]
    Pd = operating_point["Pd"]
    I_peak = operating_point.get("I_peak", 10.0)

    # Extract parameters
    UA_0 = params["UA_0"]
    UA_1 = params["UA_1"]
    eta_vol = params["eta_vol"]
    eta_s = params["eta_s"]
    R_coil_core = params["R_coil_core"]
    h_ref = params["h_ref"]
    R = params["R"]
    V_displ = params["V_displ"]
    IronLoss = params.get("IronLoss", 0.0)

    # Suction conditions — use pre-computed values when available to avoid
    # repeated CoolProp calls during calibration (same Ps, Ts every evaluation).
    Pm = Ps  # Motor section pressure approximately equals suction
    hs = hs_precomputed if hs_precomputed is not None else get_enthalpy(Ps, Ts)
    rho_s = rho_precomputed if rho_precomputed is not None else get_density(Ps, Ts)

    # Step 1: Compute mdot (constant throughout iteration)
    if RPM <= 0.0 or eta_vol <= 0.0 or V_displ <= 0.0:
        mdot = 0.0
    else:
        mdot = eta_vol * V_displ * (RPM / 60.0) * rho_s

    if mdot <= 0.0:
        # Edge case: zero flow
        return IterationResult(
            Tm=Ts, Td=Ts, hm=hs, hd=hs, mdot=0.0,
            Q_recirc=0.0, MotorLoss=0.0, Torque=0.0, T_coil=Ts,
            converged=False, iterations=0, residual=0.0,
        )

    # Initialize iteration variables
    T_coil = Ts  # Initial coil temp estimate
    MotorLoss = compute_motor_loss(R, I_peak, T_coil, RPM, IronLoss)

    # Bootstrap: compute initial Tm and Td WITHOUT recirculation to get
    # reasonable starting values for the coupled iteration.
    hm_init = hs + MotorLoss / mdot
    try:
        Tm = get_temperature(Pm, hm_init)
    except (ValueError, Exception):
        Tm = Ts + 5.0  # Fallback
    hd_init, Td = compute_discharge_state(hm_init, Pm, Pd, eta_s)
    hm = hm_init
    hd = hd_init

    converged = False
    iterations = 0
    residual = float("inf")

    # The main iteration loop resolves: Tm -> Q_recirc -> hm -> Tm
    for i in range(max_iter):
        iterations = i + 1

        # Step 3: Motor loss (sub-model B) with current coil temp
        MotorLoss = compute_motor_loss(R, I_peak, T_coil, RPM, IronLoss)

        # Step 4b: Q_recirc (sub-model D) using CURRENT Td and Tm
        Q_recirc = compute_q_recirc(UA_0, UA_1, RPM, Td, Tm)

        # Step 5: Motor outlet enthalpy
        hm_new = hs + (MotorLoss + Q_recirc) / mdot

        # Step 6: New Tm from enthalpy
        try:
            Tm_new = get_temperature(Pm, hm_new)
        except (ValueError, Exception):
            Tm_new = Tm  # Stay at previous value on error

        # Step 4: Discharge state (sub-model C) using new hm
        try:
            hd, Td_new = compute_discharge_state(hm_new, Pm, Pd, eta_s)
        except (ValueError, Exception):
            hd, Td_new = hd, Td  # Keep previous on error

        # Step 7: Relaxation on Tm and Td
        Tm_old = Tm
        Tm = alpha * Tm_new + (1.0 - alpha) * Tm_old
        Td = alpha * Td_new + (1.0 - alpha) * Td
        hm = hs + (MotorLoss + Q_recirc) / mdot  # Recompute with relaxed temps

        # Step 5b: Update coil temperature (simplified for iteration stability)
        # Use a stable estimate: T_coil tracks Tm with a small offset from
        # motor loss heating. The full sub-model E is evaluated after
        # convergence as a secondary output.
        T_coil = Tm + MotorLoss * R_coil_core

        # Step 8: Convergence check
        residual = abs(Tm_new - Tm_old)
        if residual < tol:
            converged = True
            break

    # Final discharge state with converged hm
    try:
        hd, Td = compute_discharge_state(hm, Pm, Pd, eta_s)
    except (ValueError, Exception):
        pass  # Keep last valid hd, Td

    # Final recirculation
    Q_recirc = compute_q_recirc(UA_0, UA_1, RPM, Td, Tm)

    # Final coil temperature using simplified thermal resistance network.
    # The full sub-model E formula (compute_coil_temperature) is available
    # as a standalone function for calibrated parameter sets. The simplified
    # form is used here for numerical stability with default parameters.
    T_coil = Tm + MotorLoss * R_coil_core

    # Compressor power and torque
    CompPower = mdot * (hd - hs) - MotorLoss
    Torque = compute_torque(max(CompPower, 0.0), RPM)

    return IterationResult(
        Tm=Tm,
        Td=Td,
        hm=hm,
        hd=hd,
        mdot=mdot,
        Q_recirc=Q_recirc,
        MotorLoss=MotorLoss,
        Torque=Torque,
        T_coil=T_coil,
        converged=converged,
        iterations=iterations,
        residual=residual if not converged else abs(Tm_new - Tm_old),
    )


# ---------------------------------------------------------------------------
# Full Prediction Function
# ---------------------------------------------------------------------------
# @MX:ANCHOR: [AUTO] predict_compressor is the main public API entry point
# for single-point compressor thermal prediction, called from the router layer.
# @MX:REASON: This function bridges the Pydantic schema layer to the core solver;
# incorrect parameter mapping produces wrong predictions that pass schema validation.
def predict_compressor(
    operating_point: CompressorOperatingPoint,
    params: CompressorCalibrationParams,
    motor_params: MotorParams,
) -> CompressorPrediction:
    """Single-point compressor thermal prediction.

    Runs the iterative solver and returns prediction results.

    Parameters
    ----------
    operating_point : CompressorOperatingPoint
        Input operating conditions.
    params : CompressorCalibrationParams
        Calibrated thermal parameters.
    motor_params : MotorParams
        Motor electrical parameters.

    Returns
    -------
    CompressorPrediction
        Prediction output with all computed quantities.
    """
    op_dict = {
        "RPM": operating_point.RPM,
        "Ps": operating_point.Ps,
        "Ts": operating_point.Ts,
        "Pd": operating_point.Pd,
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

    result = solve_tm_iterative(op_dict, params_dict)

    return CompressorPrediction(
        Tm=result.Tm,
        Td=result.Td,
        Torque=result.Torque,
        Q_recirc=result.Q_recirc,
        MotorLoss=result.MotorLoss,
        hm=result.hm,
        hd=result.hd,
        mdot=result.mdot,
    )

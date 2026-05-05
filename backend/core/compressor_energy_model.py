"""Compressor energy-balance prediction model.

Replaces the 6-parameter calibration approach with an energy-balance-based
model that uses lookup tables for motor torque/current and loss characteristics.

Steps:
  1. Electrical input power from 3-phase BLDC (pf~1)
  2. Torque from RPM/current lookup table
  3. Mechanical power from torque and speed
  4. Motor loss from RPM/torque lookup table
  5. Energy balance validation
  6. Refrigerant enthalpy via CoolProp
  7. Heat partitioning (refrigerant vs ambient)
  8. Coil temperature from thermal resistance network
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.refrigerant import get_enthalpy, get_temperature


# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------
def barg_to_pa(p_barg: float) -> float:
    """Convert barG (gauge pressure) to Pascal (absolute).

    Parameters
    ----------
    p_barg : float
        Gauge pressure in bar.

    Returns
    -------
    float
        Absolute pressure in Pa.
    """
    # barG -> barA (+1.01325 atm) -> Pa (*100000)
    return (p_barg + 1.01325) * 100_000.0


def kg_h_to_kg_s(mdot: float) -> float:
    """Convert mass flow rate from kg/h to kg/s.

    Parameters
    ----------
    mdot : float
        Mass flow rate in kg/h.

    Returns
    -------
    float
        Mass flow rate in kg/s.
    """
    return mdot / 3600.0


# ---------------------------------------------------------------------------
# Lookup table interpolation
# ---------------------------------------------------------------------------
@dataclass
class LookupTable:
    """2D lookup table for motor characteristics.

    Each entry maps an RPM breakpoint to a list of (x, y) tuples defining
    a curve.  Bilinear interpolation is performed across RPM and x.
    """

    rpm_values: list[float]  # RPM breakpoints (sorted ascending)
    entries: dict[float, list[tuple[float, float]]]  # RPM -> [(x, y), ...]

    def interpolate(self, rpm: float, x: float) -> float:
        """Bilinear interpolation across RPM and x value.

        Clamps to the nearest table boundary when rpm or x falls outside
        the defined range.

        Parameters
        ----------
        rpm : float
            Motor speed [RPM].
        x : float
            Independent variable (I for torque table, Torque for loss table).

        Returns
        -------
        float
            Interpolated dependent variable value.

        Raises
        ------
        ValueError
            If the table has no entries.
        """
        if not self.rpm_values:
            raise ValueError("LookupTable has no RPM entries")

        # --- RPM interpolation (1-D along RPM axis) ---
        rpm_lo, rpm_hi = self._find_bracket(self.rpm_values, rpm)
        entries_lo = self.entries[rpm_lo]
        entries_hi = self.entries[rpm_hi]

        # --- x interpolation within each RPM curve ---
        y_lo = self._interpolate_curve(entries_lo, x)
        y_hi = self._interpolate_curve(entries_hi, x)

        if rpm_hi == rpm_lo:
            return y_lo

        frac = (rpm - rpm_lo) / (rpm_hi - rpm_lo)
        return y_lo + frac * (y_hi - y_lo)

    @staticmethod
    def _find_bracket(breakpoints: list[float], value: float) -> tuple[float, float]:
        """Find the bracket (lo, hi) around *value* in sorted *breakpoints*.

        Clamps to the boundary values if *value* is outside the range.
        """
        if value <= breakpoints[0]:
            return breakpoints[0], breakpoints[0]
        if value >= breakpoints[-1]:
            return breakpoints[-1], breakpoints[-1]

        for i in range(len(breakpoints) - 1):
            if breakpoints[i] <= value <= breakpoints[i + 1]:
                return breakpoints[i], breakpoints[i + 1]

        # Fallback (should not reach here)
        return breakpoints[-1], breakpoints[-1]

    @staticmethod
    def _interpolate_curve(
        entries: list[tuple[float, float]], x: float
    ) -> float:
        """Linear interpolation along a single RPM curve.

        Clamps to boundary y-values when x is outside the curve range.
        """
        if not entries:
            raise ValueError("Curve has no entries")

        xs = [e[0] for e in entries]
        ys = [e[1] for e in entries]

        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]

        for i in range(len(xs) - 1):
            if xs[i] <= x <= xs[i + 1]:
                frac = (x - xs[i]) / (xs[i + 1] - xs[i])
                return ys[i] + frac * (ys[i + 1] - ys[i])

        return ys[-1]


class TorqueCurrentTable(LookupTable):
    """Lookup table: (RPM, I) -> Torque [Nm]."""

    def interpolate_torque(self, rpm: float, current: float) -> float:
        """Look up motor torque for given RPM and current.

        Parameters
        ----------
        rpm : float
            Motor speed [RPM].
        current : float
            Phase current [A RMS].

        Returns
        -------
        float
            Motor torque [Nm].
        """
        return self.interpolate(rpm, current)


class LossTable(LookupTable):
    """Lookup table: (RPM, Torque) -> MotorLoss [W]."""

    def interpolate_loss(self, rpm: float, torque: float) -> float:
        """Look up motor loss for given RPM and torque.

        Parameters
        ----------
        rpm : float
            Motor speed [RPM].
        torque : float
            Motor torque [Nm].

        Returns
        -------
        float
            Motor loss [W].
        """
        return self.interpolate(rpm, torque)


# ---------------------------------------------------------------------------
# Energy model data classes
# ---------------------------------------------------------------------------
@dataclass
class EnergyModelInput:
    """Input parameters for the energy-balance compressor model."""

    # Refrigerant conditions
    Ps: float  # Suction pressure [barG]
    Ts: float  # Suction temperature [degC]
    P_mid: float  # Mid-point pressure after motor [barG]
    T_mid: float  # Mid-point temperature after motor [degC]
    Pd: float  # Discharge pressure [barG]
    mdot: float  # Mass flow rate [kg/h]
    # Motor electrical
    V: float  # Line-to-line voltage [V RMS]
    I: float  # Phase current [A RMS]
    RPM: float  # Motor speed [rpm]
    # Thermal
    R_coil_case: float  # Coil-to-case thermal resistance [K/W]
    R_coil_core: float  # Coil-to-core thermal resistance [K/W]
    R_coil_refrigerant: float  # Coil-to-refrigerant thermal resistance [K/W]
    T_ambient: float  # Ambient temperature [degC]


@dataclass
class EnergyModelResult:
    """Result from the energy-balance prediction."""

    Torque: float  # Motor torque [Nm]
    T_coil: float  # Coil temperature [degC]
    Pin: float  # Electrical input power [W]
    Pmech: float  # Mechanical output power [W]
    MotorLoss: float  # Total motor loss [W]
    Q_refrig: float  # Heat to refrigerant [W]
    Q_ambient: float  # Heat to ambient [W]
    hs: float  # Suction enthalpy [J/kg]
    h_mid: float  # Mid-point enthalpy [J/kg]
    hd: float  # Discharge enthalpy [J/kg]
    Td_est: float  # Estimated discharge temperature [degC]
    mdot_recirc: float  # Hot gas recirculation mass flow [kg/s]
    recirc_ratio: float  # Recirculation ratio (mdot_recirc / mdot_s) [-]
    balance_error_pct: float  # Energy balance error [%]
    converged: bool  # Whether energy balance is reasonable (< 10 %)


# ---------------------------------------------------------------------------
# Core prediction function
# ---------------------------------------------------------------------------
# @MX:ANCHOR: [AUTO] predict_energy_balance is the core calculation engine
# for the new energy-balance compressor model.
# @MX:REASON: This function is the single entry point for energy-balance
# predictions and will be called from the API router and tests.
def predict_energy_balance(
    inp: EnergyModelInput,
    torque_table: TorqueCurrentTable,
    loss_table: LossTable,
) -> EnergyModelResult:
    """Run energy balance prediction for the compressor.

    Parameters
    ----------
    inp : EnergyModelInput
        Operating point and motor parameters.
    torque_table : TorqueCurrentTable
        (RPM, I) -> Torque lookup.
    loss_table : LossTable
        (RPM, Torque) -> MotorLoss lookup.

    Returns
    -------
    EnergyModelResult
        Prediction results including power, losses, temperatures, and
        convergence status.
    """
    # Step 1: Electrical input power (3-phase BLDC, power factor ~1)
    Pin = math.sqrt(3) * inp.V * inp.I

    # Step 2: Torque from lookup table
    Torque = torque_table.interpolate_torque(inp.RPM, inp.I)

    # Step 3: Mechanical output power
    omega = 2.0 * math.pi * inp.RPM / 60.0
    Pmech = Torque * omega

    # Step 4: Motor loss from lookup table
    MotorLoss = loss_table.interpolate_loss(inp.RPM, Torque)

    # Step 5: Energy balance error
    balance_error_pct = abs(Pin - Pmech - MotorLoss) / Pin * 100.0

    # Step 6-7: Refrigerant enthalpies
    Ps_pa = barg_to_pa(inp.Ps)
    P_mid_pa = barg_to_pa(inp.P_mid)
    Pd_pa = barg_to_pa(inp.Pd)
    hs = get_enthalpy(Ps_pa, inp.Ts)
    h_mid = get_enthalpy(P_mid_pa, inp.T_mid)

    # Step 8: Heat absorbed by refrigerant
    mdot_s = kg_h_to_kg_s(inp.mdot)
    Q_refrig = mdot_s * (h_mid - hs)

    # Step 9: Heat to ambient
    Q_ambient = MotorLoss - Q_refrig

    # Step 10: Discharge enthalpy from energy balance
    # Compression work goes into the refrigerant: hd = h_mid + Pmech / mdot_s
    hd = h_mid + Pmech / mdot_s if mdot_s > 0 else h_mid

    # Step 11: Discharge temperature from (Pd, hd)
    Td_est: float = 0.0
    try:
        Td_est = get_temperature(Pd_pa, hd)
    except (ValueError, RuntimeError):
        Td_est = float("nan")

    # Step 12: Hot gas recirculation model
    # Q_refrig = MotorLoss + mdot_recirc * (hd - h_mid)
    # => mdot_recirc = (Q_refrig - MotorLoss) / (hd - h_mid)
    dh = hd - h_mid
    if dh > 0 and Q_refrig > MotorLoss:
        mdot_recirc = (Q_refrig - MotorLoss) / dh
    else:
        mdot_recirc = 0.0
    recirc_ratio = mdot_recirc / mdot_s if mdot_s > 0 else 0.0

    # Step 13: Coil temperature from thermal resistance network (3-path)
    # MotorLoss = (T_coil - T_mid)/R_core + (T_coil - T_ambient)/R_case + (T_coil - Ts)/R_refrig
    # Solving for T_coil:
    inv_R_core = 1.0 / inp.R_coil_core
    inv_R_case = 1.0 / inp.R_coil_case
    inv_R_refrig = 1.0 / inp.R_coil_refrigerant
    T_coil = (
        MotorLoss + inp.T_mid * inv_R_core + inp.T_ambient * inv_R_case + inp.Ts * inv_R_refrig
    ) / (inv_R_core + inv_R_case + inv_R_refrig)

    # Step 14: Convergence check
    converged = balance_error_pct < 10.0

    return EnergyModelResult(
        Torque=Torque,
        T_coil=T_coil,
        Pin=Pin,
        Pmech=Pmech,
        MotorLoss=MotorLoss,
        Q_refrig=Q_refrig,
        Q_ambient=Q_ambient,
        hs=hs,
        h_mid=h_mid,
        hd=hd,
        Td_est=Td_est,
        mdot_recirc=mdot_recirc,
        recirc_ratio=recirc_ratio,
        balance_error_pct=balance_error_pct,
        converged=converged,
    )


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------
@dataclass
class CalibDataPoint:
    """Single measurement point for calibration."""

    Ps: float
    Ts: float
    P_mid: float
    T_mid: float
    Pd: float
    mdot: float
    V: float
    I: float
    RPM: float
    T_ambient: float
    T_coil_measured: float
    Td_measured: float | None = None


@dataclass
class CalibResult:
    """Result from thermal resistance calibration."""

    R_coil_case: float
    R_coil_core: float
    R_coil_refrigerant: float
    rmse_T_coil: float
    mae_T_coil: float
    max_error_T_coil: float
    rmse_Td: float | None
    n_points: int
    converged: bool
    iterations: int
    T_coil_predicted: list[float]
    T_coil_measured: list[float]
    Td_predicted: list[float]


def _make_input(
    point: CalibDataPoint,
    R_case: float,
    R_core: float,
    R_refrig: float,
) -> EnergyModelInput:
    """Build EnergyModelInput from a data point with trial R values."""
    return EnergyModelInput(
        Ps=point.Ps,
        Ts=point.Ts,
        P_mid=point.P_mid,
        T_mid=point.T_mid,
        Pd=point.Pd,
        mdot=point.mdot,
        V=point.V,
        I=point.I,
        RPM=point.RPM,
        R_coil_case=R_case,
        R_coil_core=R_core,
        R_coil_refrigerant=R_refrig,
        T_ambient=point.T_ambient,
    )


def calibrate_thermal_resistances(
    data_points: list[CalibDataPoint],
    torque_table: TorqueCurrentTable,
    loss_table: LossTable,
    R_init: dict[str, float] | None = None,
    n_starts: int = 5,
    tol: float = 1e-6,
    max_iter: int = 500,
) -> CalibResult:
    """Calibrate thermal resistances by matching predicted T_coil to measurements.

    Parameters
    ----------
    data_points : list[CalibDataPoint]
        Measurement data (operating conditions + T_coil_measured).
    torque_table : TorqueCurrentTable
        Motor torque lookup.
    loss_table : LossTable
        Motor loss lookup.
    R_init : dict or None
        Initial guesses for R values.
    n_starts : int
        Number of multi-start optimization runs.
    tol : float
        Convergence tolerance.
    max_iter : int
        Maximum iterations per start.

    Returns
    -------
    CalibResult
        Optimized R values and prediction metrics.
    """
    from scipy.optimize import differential_evolution, minimize

    bounds = [(1e-4, 10.0), (1e-4, 10.0), (1e-4, 10.0)]

    def objective(params: list[float]) -> float:
        R_case, R_core, R_refrig = params
        if R_case <= 0 or R_core <= 0 or R_refrig <= 0:
            return 1e12
        total_sq = 0.0
        for pt in data_points:
            try:
                inp = _make_input(pt, R_case, R_core, R_refrig)
                result = predict_energy_balance(inp, torque_table, loss_table)
                total_sq += (result.T_coil - pt.T_coil_measured) ** 2
            except (ValueError, RuntimeError):
                return 1e12
        return total_sq

    # Global search with differential evolution
    de_result = differential_evolution(
        objective,
        bounds,
        maxiter=max_iter,
        tol=tol,
        seed=42,
        polish=True,
    )

    best_params = de_result.x.tolist()
    best_fun = de_result.fun
    converged = de_result.success

    # Evaluate predictions at optimum
    R_case, R_core, R_refrig = best_params
    T_coil_preds: list[float] = []
    T_coil_meas: list[float] = []
    Td_preds: list[float] = []
    n = len(data_points)

    for pt in data_points:
        inp = _make_input(pt, R_case, R_core, R_refrig)
        result = predict_energy_balance(inp, torque_table, loss_table)
        T_coil_preds.append(result.T_coil)
        T_coil_meas.append(pt.T_coil_measured)
        Td_preds.append(result.Td_est)

    errors = [p - m for p, m in zip(T_coil_preds, T_coil_meas)]
    rmse = math.sqrt(sum(e ** 2 for e in errors) / n) if n > 0 else 0.0
    mae = sum(abs(e) for e in errors) / n if n > 0 else 0.0
    max_err = max(abs(e) for e in errors) if errors else 0.0

    # Td RMSE (if measured values available)
    rmse_Td: float | None = None
    td_measured = [pt.Td_measured for pt in data_points if pt.Td_measured is not None]
    if td_measured:
        td_preds_filtered = [
            Td_preds[i]
            for i, pt in enumerate(data_points)
            if pt.Td_measured is not None
        ]
        td_errors = [p - m for p, m in zip(td_preds_filtered, td_measured)]
        rmse_Td = math.sqrt(sum(e ** 2 for e in td_errors) / len(td_errors))

    return CalibResult(
        R_coil_case=R_case,
        R_coil_core=R_core,
        R_coil_refrigerant=R_refrig,
        rmse_T_coil=rmse,
        mae_T_coil=mae,
        max_error_T_coil=max_err,
        rmse_Td=rmse_Td,
        n_points=n,
        converged=converged,
        iterations=de_result.nfev,
        T_coil_predicted=T_coil_preds,
        T_coil_measured=T_coil_meas,
        Td_predicted=Td_preds,
    )

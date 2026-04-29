"""Copper and iron loss computation for the motor thermal model.

Provides two iron-loss modes:
  - *simple*: power-law scaling with RPM (PRD Section 4.5 Mode A)
  - *map*:    bilinear interpolation from an FEA loss-map DataFrame (PRD Section 4.5 Mode B)

Reference: PRD v1.0 Section 4.5
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Default coil parameters (SPEC CoilParams)
# ---------------------------------------------------------------------------
R0_DEFAULT: float = 0.5  # Ohm  (1-phase, at T0)
T0_DEFAULT: float = 20.0  # degC
ALPHA_CU: float = 0.00393  # 1/degC  (copper temp coefficient)
N_PHASES_DEFAULT: int = 3
BETA_IRON_DEFAULT: float = 0.002  # 1/K  (iron loss temp correction)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CoilParams:
    """Coil electrical parameters."""

    R0: float = R0_DEFAULT
    T0: float = T0_DEFAULT
    alpha: float = ALPHA_CU
    n_phases: int = N_PHASES_DEFAULT


@dataclass(frozen=True)
class SimpleIronLoss:
    """Parameters for the simple (power-law) iron-loss model."""

    I_max: float = 10.0  # A
    RPM_max: float = 5000.0  # RPM
    alpha_iron: float = 2.0  # RPM exponent
    n_phases: int = N_PHASES_DEFAULT
    R0: float = R0_DEFAULT
    T0: float = T0_DEFAULT
    alpha_cu: float = ALPHA_CU


# ---------------------------------------------------------------------------
# Copper loss
# ---------------------------------------------------------------------------
def compute_copper_loss(
    I_A: float,
    T_coil_C: float,
    R0_ohm: float = R0_DEFAULT,
    n_phases: int = N_PHASES_DEFAULT,
    T0: float = T0_DEFAULT,
    alpha_cu: float = ALPHA_CU,
) -> float:
    """Compute copper (Joule) loss at temperature *T_coil_C*.

    .. math::

        Q_{cu} = n \\times I^2 \\times R_0 \\times [1 + \\alpha (T_{coil} - T_0)]

    Parameters
    ----------
    I_A : float
        Phase current [A].
    T_coil_C : float
        Coil temperature [degC].
    R0_ohm : float
        Reference resistance at *T0* [Ohm].
    n_phases : int
        Number of phases.
    T0 : float
        Reference temperature [degC].
    alpha_cu : float
        Copper resistance temperature coefficient [1/degC].

    Returns
    -------
    float
        Copper loss [W].
    """
    R_T = R0_ohm * (1.0 + alpha_cu * (T_coil_C - T0))
    return n_phases * I_A**2 * R_T


# ---------------------------------------------------------------------------
# Iron loss — simple mode
# ---------------------------------------------------------------------------
def compute_iron_loss_simple(
    W_rpm: float,
    P_iron_ref_W: float,
    alpha_iron: float = 2.0,
    W_ref: float = 1.0,
) -> float:
    """Compute iron loss using simple power-law model.

    .. math::

        Q_{iron} = P_{iron,ref} \\times (W / W_{ref})^{\\alpha_{iron}}

    Parameters
    ----------
    W_rpm : float
        Current speed [RPM].
    P_iron_ref_W : float
        Iron loss at *W_ref* [W].
    alpha_iron : float
        Speed exponent. Default 2.0.
    W_ref : float
        Reference speed [RPM].

    Returns
    -------
    float
        Iron loss [W].
    """
    if W_ref == 0.0:
        return 0.0
    return P_iron_ref_W * (W_rpm / W_ref) ** alpha_iron


def compute_iron_max(
    n_phases: int = N_PHASES_DEFAULT,
    I_max: float = 10.0,
    R0: float = R0_DEFAULT,
    alpha_cu: float = ALPHA_CU,
    T_ref: float = 20.0,
    T0: float = T0_DEFAULT,
) -> float:
    """Compute Q_iron_max per PRD eq: 0.3 * n * I_max^2 * R(T_ref).

    Parameters
    ----------
    n_phases : int
    I_max : float
        Maximum reference current [A].
    R0 : float
        Reference resistance [Ohm].
    alpha_cu : float
    T_ref : float
        Temperature at which to evaluate R [degC].
    T0 : float
        Reference temperature for R0 [degC].

    Returns
    -------
    float
        Q_iron_max [W].
    """
    R_at_Tref = R0 * (1.0 + alpha_cu * (T_ref - T0))
    return 0.3 * n_phases * I_max**2 * R_at_Tref


# ---------------------------------------------------------------------------
# Iron loss — loss-map mode (bilinear interpolation)
# ---------------------------------------------------------------------------
def compute_iron_loss_map(
    I_A: float,
    W_rpm: float,
    loss_map_df: pd.DataFrame,
    T_coil_C: float = 20.0,
    beta_iron: float = BETA_IRON_DEFAULT,
    R0_ohm: float = R0_DEFAULT,
    T0: float = T0_DEFAULT,
    alpha_cu: float = ALPHA_CU,
) -> Tuple[float, float]:
    """Compute copper and iron loss from an FEA loss map via bilinear interp.

    The DataFrame must have columns ``rpm``, ``torque_nm``, ``p_copper_w``,
    ``p_iron_w``.  The function looks up by (RPM, Torque) and applies
    temperature corrections per PRD Section 4.5 Mode B.

    Parameters
    ----------
    I_A : float
        Phase current [A] (used to derive torque when not available —
        currently kept for API symmetry).
    W_rpm : float
        Current speed [RPM].
    loss_map_df : pd.DataFrame
        Loss-map table with columns rpm, torque_nm, p_copper_w, p_iron_w.
    T_coil_C : float
        Current coil temperature [degC].
    beta_iron : float
        Iron loss temperature correction coefficient [1/K]. Default 0.002.

    Returns
    -------
    tuple[float, float]
        (Q_copper_corrected, Q_iron_corrected) in watts.

    Notes
    -----
    Out-of-range values are clamped to the nearest boundary with a warning.
    """
    # Extract unique sorted grid axes
    rpms = np.sort(loss_map_df["rpm"].unique())
    torques = np.sort(loss_map_df["torque_nm"].unique())

    # Clamp to grid bounds
    rpm_clamped = np.clip(W_rpm, rpms[0], rpms[-1])
    if rpm_clamped != W_rpm:
        warnings.warn(
            f"RPM {W_rpm} outside loss-map range [{rpms[0]}, {rpms[-1]}]; clamped.",
            stacklevel=2,
        )

    # For bilinear interp, we use (rpm, I_A) as proxy when torque column
    # is present.  Use the I_A value directly as the torque axis proxy.
    torque_clamped = np.clip(I_A, torques[0], torques[-1])

    # Build 2-D grids for copper and iron
    p_cu_grid = loss_map_df.pivot(
        index="rpm", columns="torque_nm", values="p_copper_w"
    ).reindex(index=rpms, columns=torques).values
    p_iron_grid = loss_map_df.pivot(
        index="rpm", columns="torque_nm", values="p_iron_w"
    ).reindex(index=rpms, columns=torques).values

    # Bilinear interpolation helper
    def _bilinear(grid: np.ndarray, x: float, y: float) -> float:
        # Find bracketing indices on each axis
        xi = np.searchsorted(rpms, x) - 1
        yi = np.searchsorted(torques, y) - 1
        xi = max(0, min(xi, len(rpms) - 2))
        yi = max(0, min(yi, len(torques) - 2))

        x0, x1 = rpms[xi], rpms[xi + 1]
        y0, y1 = torques[yi], torques[yi + 1]

        dx = (x - x0) / (x1 - x0) if x1 != x0 else 0.0
        dy = (y - y0) / (y1 - y0) if y1 != y0 else 0.0

        return float(
            grid[xi, yi] * (1 - dx) * (1 - dy)
            + grid[xi + 1, yi] * dx * (1 - dy)
            + grid[xi, yi + 1] * (1 - dx) * dy
            + grid[xi + 1, yi + 1] * dx * dy
        )

    p_cu_ref = _bilinear(p_cu_grid, rpm_clamped, torque_clamped)
    p_iron_ref = _bilinear(p_iron_grid, rpm_clamped, torque_clamped)

    # Temperature corrections (PRD 4.5 Mode B)
    Q_copper = p_cu_ref * (1.0 + alpha_cu * (T_coil_C - 20.0))
    Q_iron = p_iron_ref * (1.0 - beta_iron * (T_coil_C - 20.0))

    return Q_copper, Q_iron


# ---------------------------------------------------------------------------
# Unified loss function
# ---------------------------------------------------------------------------
def compute_total_loss(
    I_A: float,
    T_coil_C: float,
    W_rpm: float,
    coil: CoilParams | None = None,
    loss_mode: str = "simple",
    loss_map_df: pd.DataFrame | None = None,
    P_iron_ref_W: float = 0.0,
    alpha_iron: float = 2.0,
    W_ref: float = 1.0,
) -> float:
    """Compute total heat generation Q_gen = Q_copper + Q_iron.

    Parameters
    ----------
    I_A : float
        Phase current [A].
    T_coil_C : float
        Coil temperature [degC].
    W_rpm : float
        Rotor speed [RPM].
    coil : CoilParams | None
        Coil parameters. Uses defaults if None.
    loss_mode : str
        ``"simple"`` or ``"map"``.
    loss_map_df : pd.DataFrame | None
        Required when *loss_mode* is ``"map"``.
    P_iron_ref_W : float
        Iron loss at *W_ref* for simple mode [W].
    alpha_iron : float
        Speed exponent for simple mode.
    W_ref : float
        Reference RPM for simple mode.

    Returns
    -------
    float
        Total heat generation [W].
    """
    if coil is None:
        coil = CoilParams()

    Q_copper = compute_copper_loss(
        I_A=I_A,
        T_coil_C=T_coil_C,
        R0_ohm=coil.R0,
        n_phases=coil.n_phases,
        T0=coil.T0,
        alpha_cu=coil.alpha,
    )

    if loss_mode == "map":
        if loss_map_df is None:
            raise ValueError("loss_map_df is required for map mode")
        _, Q_iron = compute_iron_loss_map(
            I_A=I_A,
            W_rpm=W_rpm,
            loss_map_df=loss_map_df,
            T_coil_C=T_coil_C,
        )
    else:
        Q_iron = compute_iron_loss_simple(
            W_rpm=W_rpm,
            P_iron_ref_W=P_iron_ref_W,
            alpha_iron=alpha_iron,
            W_ref=W_ref,
        )

    return Q_copper + Q_iron


# ---------------------------------------------------------------------------
# Heat-source closures used by thermal_model
# ---------------------------------------------------------------------------
def make_simple_loss_fn(
    coil: CoilParams,
    iron: SimpleIronLoss,
) -> "Callable[[float, float, float], Tuple[float, float]]":
    """Return a loss function ``(I, T_coil, RPM) -> (Q_cu, Q_iron)`` for simple mode.

    The returned callable matches the signature expected by
    :func:`thermal_model.simulate_3node`.
    """
    Q_iron_max = compute_iron_max(
        n_phases=iron.n_phases,
        I_max=iron.I_max,
        R0=iron.R0,
        alpha_cu=iron.alpha_cu,
        T_ref=iron.T0,
        T0=iron.T0,
    )

    def loss_fn(I: float, T_coil: float, RPM: float) -> Tuple[float, float]:
        Q_cu = compute_copper_loss(
            I_A=I,
            T_coil_C=T_coil,
            R0_ohm=coil.R0,
            n_phases=coil.n_phases,
            T0=coil.T0,
            alpha_cu=coil.alpha,
        )
        if iron.RPM_max > 0:
            Q_iron = Q_iron_max * (RPM / iron.RPM_max) ** iron.alpha_iron
        else:
            Q_iron = 0.0
        return Q_cu, Q_iron

    return loss_fn


def make_map_loss_fn(
    coil: CoilParams,
    loss_map_df: pd.DataFrame,
    beta_iron: float = BETA_IRON_DEFAULT,
) -> "Callable[[float, float, float], Tuple[float, float]]":
    """Return a loss function ``(I, T_coil, RPM) -> (Q_cu, Q_iron)`` for map mode."""

    def loss_fn(I: float, T_coil: float, RPM: float) -> Tuple[float, float]:
        return compute_iron_loss_map(
            I_A=I,
            W_rpm=RPM,
            loss_map_df=loss_map_df,
            T_coil_C=T_coil,
            beta_iron=beta_iron,
            R0_ohm=coil.R0,
            T0=coil.T0,
            alpha_cu=coil.alpha,
        )

    return loss_fn


# Type alias hint
from typing import Callable  # noqa: E402

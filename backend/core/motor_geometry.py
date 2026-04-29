"""Motor geometry thermal mass and initial resistance computation.

Computes thermal capacitances (C_coil, C_core, C_housing) from motor
geometry and material properties, and initial thermal resistance estimates
(R2_mold, R3_nat) for the 3-node thermal model.

Reference: PRD v1.0 Sections 4.3-4.4
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict


# ---------------------------------------------------------------------------
# Material property defaults (PRD Section 4.3)
# ---------------------------------------------------------------------------
COPPER_CP: float = 385.0  # J/(kg*K)
FESI_CP: float = 490.0  # J/(kg*K)
ALUMINUM_CP: float = 900.0  # J/(kg*K)

# Mold / interface layer (PRD Section 4.4, SPEC MotorGeometry defaults)
MOLD_THICKNESS_MM: float = 0.5  # mm  (t_mold_mm)
MOLD_CONDUCTIVITY: float = 0.3  # W/(m*K)  (k_mold)

# Default convection (PRD Section 4.4)
H_NAT_DEFAULT: float = 10.0  # W/(m^2*K)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ThermalMasses:
    """Thermal capacitance and intermediate geometry results."""

    C_coil: float  # J/degC
    C_core: float  # J/degC
    C_housing: float  # J/degC
    m_coil: float  # kg
    m_core: float  # kg
    m_housing: float  # kg
    A_interface: float  # m^2  (stator outer surface)
    A_housing: float  # m^2  (housing outer surface)


@dataclass(frozen=True)
class InitialResistances:
    """Physics-based initial thermal resistance estimates."""

    R2_mold: float  # degC/W  (core-to-housing via mold)
    R3_nat_init: float  # degC/W  (housing-to-ambient, RPM=0)
    tau_approx: float  # s  (approximate thermal time constant)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_thermal_masses(
    D_motor_mm: float,
    L_motor_mm: float,
    t_housing_mm: float,
    m_motor_g: float,
    m_housing_g: float,
    L_housing_mm: float | None = None,
    f_copper: float = 0.35,
    c_p_Cu: float = COPPER_CP,
    c_p_FeSi: float = FESI_CP,
    c_p_Al: float = ALUMINUM_CP,
) -> ThermalMasses:
    """Compute thermal capacitances from motor geometry and material props.

    Parameters
    ----------
    D_motor_mm : float
        Stator outer diameter [mm].
    L_motor_mm : float
        Stator axial length [mm].
    t_housing_mm : float
        Housing wall thickness [mm].
    m_motor_g : float
        Total motor mass including housing [g].
    m_housing_g : float
        Housing mass [g].
    L_housing_mm : float | None
        Housing axial length [mm]. Defaults to *L_motor_mm*.
    f_copper : float
        Copper fill fraction of stator mass (0-1). Default 0.35.
    c_p_Cu, c_p_FeSi, c_p_Al : float
        Specific heat capacities [J/(kg*K)].

    Returns
    -------
    ThermalMasses
        Capacitances, masses, and interface areas.

    Reference
    ---------
    PRD Section 4.3.
    """
    if L_housing_mm is None:
        L_housing_mm = L_motor_mm

    # Convert to SI
    D_motor = D_motor_mm / 1000.0  # m
    L_motor = L_motor_mm / 1000.0  # m
    t_housing = t_housing_mm / 1000.0  # m
    L_housing = L_housing_mm / 1000.0  # m

    # Interface areas (PRD 4.4)
    A_interface = math.pi * D_motor * L_motor  # m^2
    D_out = D_motor + 2.0 * t_housing
    A_housing = math.pi * D_out * L_housing  # m^2

    # Mass decomposition (PRD 4.3)
    m_housing = m_housing_g / 1000.0  # kg
    m_stator = (m_motor_g - m_housing_g) / 1000.0  # kg
    m_coil = m_stator * f_copper  # kg
    m_core = m_stator * (1.0 - f_copper)  # kg

    # Thermal capacitances
    C_coil = m_coil * c_p_Cu  # J/degC
    C_core = m_core * c_p_FeSi  # J/degC
    C_housing = m_housing * c_p_Al  # J/degC

    return ThermalMasses(
        C_coil=C_coil,
        C_core=C_core,
        C_housing=C_housing,
        m_coil=m_coil,
        m_core=m_core,
        m_housing=m_housing,
        A_interface=A_interface,
        A_housing=A_housing,
    )


def compute_initial_resistances(
    D_motor_mm: float,
    L_motor_mm: float,
    t_housing_mm: float,
    m_motor_g: float,
    m_housing_g: float,
    L_housing_mm: float | None = None,
    f_copper: float = 0.35,
    t_mold_mm: float = MOLD_THICKNESS_MM,
    k_mold: float = MOLD_CONDUCTIVITY,
    h_nat: float = H_NAT_DEFAULT,
) -> InitialResistances:
    """Compute physics-based initial thermal resistances.

    Parameters
    ----------
    D_motor_mm, L_motor_mm, t_housing_mm : float
        Motor geometry [mm].
    m_motor_g, m_housing_g : float
        Total and housing mass [g].
    L_housing_mm : float | None
        Housing length [mm]. Defaults to *L_motor_mm*.
    f_copper : float
        Copper fill fraction. Default 0.35.
    t_mold_mm : float
        Mold (interface) thickness [mm]. Default 0.5.
    k_mold : float
        Mold thermal conductivity [W/(m*K)]. Default 0.3.
    h_nat : float
        Natural convection coefficient [W/(m^2*K)]. Default 10.

    Returns
    -------
    InitialResistances
        R2_mold, R3_nat_init, and approximate time constant.

    Reference
    ---------
    PRD Sections 4.3-4.4.
    """
    masses = compute_thermal_masses(
        D_motor_mm=D_motor_mm,
        L_motor_mm=L_motor_mm,
        t_housing_mm=t_housing_mm,
        m_motor_g=m_motor_g,
        m_housing_g=m_housing_g,
        L_housing_mm=L_housing_mm,
        f_copper=f_copper,
    )

    # R2_mold: core-to-housing conduction through mold layer
    t_mold = t_mold_mm / 1000.0  # m
    R2_mold = t_mold / (k_mold * masses.A_interface)  # degC/W

    # R3 at RPM=0 (natural convection only)
    R3_nat_init = 1.0 / (h_nat * masses.A_housing)  # degC/W

    # Approximate time constant: sum(C) * R3
    C_total = masses.C_coil + masses.C_core + masses.C_housing
    tau_approx = C_total * R3_nat_init  # s

    return InitialResistances(
        R2_mold=R2_mold,
        R3_nat_init=R3_nat_init,
        tau_approx=tau_approx,
    )

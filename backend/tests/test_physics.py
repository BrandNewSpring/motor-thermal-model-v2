"""Unit tests for the motor thermal physics engine.

Tests cover:
  1. Thermal mass computation (motor_geometry)
  2. R2_mold resistance calculation (motor_geometry)
  3. Copper loss calculation (loss_model)
  4. 3-node ODE steady-state convergence (thermal_model)
  5. Calibration smoke test with synthetic data (calibration)

Run with:
    python -m pytest tests/test_physics.py -v
"""

from __future__ import annotations

import math

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------
from core.motor_geometry import (
    compute_initial_resistances,
    compute_thermal_masses,
)
from core.loss_model import (
    CoilParams,
    SimpleIronLoss,
    compute_copper_loss,
    compute_iron_loss_simple,
    make_simple_loss_fn,
)
from core.thermal_model import (
    R3_at_rpm,
    simulate_3node,
)
from core.calibration import (
    CalibResult,
    CalibSettings,
    run_calibration,
)


# ===========================================================================
# Fixtures — default motor geometry
# ===========================================================================
@pytest.fixture()
def default_geo():
    """Default motor geometry values per PRD Section 3."""
    return dict(
        D_motor_mm=106.0,
        L_motor_mm=48.85,
        t_housing_mm=10.5,
        m_motor_g=1200.0,  # total motor mass [g]
        m_housing_g=350.0,  # housing mass [g]
        L_housing_mm=48.85,
    )


# ===========================================================================
# Test 1: Thermal masses
# ===========================================================================
class TestThermalMasses:
    """motor_geometry.compute_thermal_masses tests."""

    def test_C_housing_gt_C_coil(self, default_geo):
        """D=106mm, L=48.85mm -> C_housing > C_coil (Al housing is massive)."""
        masses = compute_thermal_masses(**default_geo)
        assert masses.C_housing > masses.C_coil, (
            f"C_housing={masses.C_housing:.2f} should exceed "
            f"C_coil={masses.C_coil:.2f}"
        )

    def test_positive_capacitances(self, default_geo):
        """All thermal capacitances must be positive."""
        masses = compute_thermal_masses(**default_geo)
        assert masses.C_coil > 0
        assert masses.C_core > 0
        assert masses.C_housing > 0

    def test_A_interface_approx(self, default_geo):
        """A_interface ~ pi * 0.106 * 0.04885 = 0.01626 m^2."""
        masses = compute_thermal_masses(**default_geo)
        expected = math.pi * 0.106 * 0.04885
        assert abs(masses.A_interface - expected) / expected < 0.01, (
            f"A_interface={masses.A_interface:.6f}, expected={expected:.6f}"
        )

    def test_A_housing_approx(self, default_geo):
        """A_housing ~ pi * (0.106 + 2*0.0105) * 0.04885 ~ 0.0195 m^2."""
        masses = compute_thermal_masses(**default_geo)
        D_out = 0.106 + 2 * 0.0105  # 0.127 m
        expected = math.pi * D_out * 0.04885
        assert abs(masses.A_housing - expected) / expected < 0.01, (
            f"A_housing={masses.A_housing:.6f}, expected={expected:.6f}"
        )


# ===========================================================================
# Test 2: R2_mold
# ===========================================================================
class TestR2Mold:
    """motor_geometry.compute_initial_resistances tests."""

    def test_R2_mold_value(self, default_geo):
        """R2_mold ~ 0.103 degC/W +/- 5%."""
        res = compute_initial_resistances(**default_geo)
        expected = 0.103
        assert abs(res.R2_mold - expected) / expected < 0.05, (
            f"R2_mold={res.R2_mold:.4f}, expected~{expected}"
        )

    def test_R2_mold_formula(self, default_geo):
        """R2_mold = t_mold / (k_mold * A_interface)."""
        masses = compute_thermal_masses(**default_geo)
        t_mold = 0.5e-3  # 0.5 mm in m
        k_mold = 0.3  # W/(m*K)
        expected = t_mold / (k_mold * masses.A_interface)
        res = compute_initial_resistances(**default_geo)
        assert abs(res.R2_mold - expected) < 1e-10

    def test_R3_nat_init_positive(self, default_geo):
        """R3_nat_init must be positive."""
        res = compute_initial_resistances(**default_geo)
        assert res.R3_nat_init > 0


# ===========================================================================
# Test 3: Copper loss
# ===========================================================================
class TestCopperLoss:
    """loss_model.compute_copper_loss tests."""

    def test_basic_copper_loss(self):
        """I=10A, T=100C, R0=0.5, n=3 -> Q_cu = 3*100*0.5*(1+0.00393*80)."""
        I = 10.0
        T = 100.0
        R0 = 0.5
        n = 3
        T0 = 20.0
        alpha = 0.00393

        Q_cu = compute_copper_loss(
            I_A=I, T_coil_C=T, R0_ohm=R0, n_phases=n, T0=T0, alpha_cu=alpha,
        )

        expected = n * I**2 * R0 * (1.0 + alpha * (T - T0))
        assert abs(Q_cu - expected) / expected < 1e-10, (
            f"Q_cu={Q_cu:.4f}, expected={expected:.4f}"
        )

    def test_copper_loss_at_T0(self):
        """At T=T0, Q = n*I^2*R0."""
        Q = compute_copper_loss(I_A=5.0, T_coil_C=20.0, R0_ohm=0.5, n_phases=3)
        expected = 3 * 25.0 * 0.5
        assert abs(Q - expected) < 1e-10

    def test_copper_loss_increases_with_temp(self):
        """Higher temperature -> higher resistance -> higher loss."""
        Q_low = compute_copper_loss(I_A=10.0, T_coil_C=25.0, R0_ohm=0.5)
        Q_high = compute_copper_loss(I_A=10.0, T_coil_C=120.0, R0_ohm=0.5)
        assert Q_high > Q_low


# ===========================================================================
# Test 4: Iron loss (simple)
# ===========================================================================
class TestIronLossSimple:
    """loss_model.compute_iron_loss_simple tests."""

    def test_at_ref_rpm(self):
        """At W=W_ref, Q_iron = P_iron_ref."""
        Q = compute_iron_loss_simple(W_rpm=3000.0, P_iron_ref_W=50.0, W_ref=3000.0)
        assert abs(Q - 50.0) < 1e-10

    def test_zero_rpm(self):
        """At RPM=0, Q_iron = 0 (for positive exponent)."""
        Q = compute_iron_loss_simple(W_rpm=0.0, P_iron_ref_W=50.0, W_ref=3000.0)
        assert abs(Q) < 1e-10

    def test_scales_with_rpm(self):
        """Q_iron scales as RPM^alpha."""
        Q_low = compute_iron_loss_simple(
            W_rpm=1000.0, P_iron_ref_W=50.0, W_ref=3000.0, alpha_iron=2.0,
        )
        Q_high = compute_iron_loss_simple(
            W_rpm=3000.0, P_iron_ref_W=50.0, W_ref=3000.0, alpha_iron=2.0,
        )
        assert Q_high > Q_low


# ===========================================================================
# Test 5: R3_at_rpm
# ===========================================================================
class TestR3AtRpm:
    """thermal_model.R3_at_rpm tests."""

    def test_zero_rpm(self):
        """R3 at RPM=0 = 1/(h_nat * A)."""
        R3 = R3_at_rpm(rpm=0.0, h_nat=10.0, h_rpm=0.02, A_housing=0.0195)
        expected = 1.0 / (10.0 * 0.0195)
        assert abs(R3 - expected) < 1e-10

    def test_nonzero_rpm_lower(self):
        """R3 at RPM>0 should be lower than at RPM=0."""
        R3_0 = R3_at_rpm(rpm=0.0, h_nat=10.0, h_rpm=0.02, A_housing=0.0195)
        R3_3k = R3_at_rpm(rpm=3000.0, h_nat=10.0, h_rpm=0.02, A_housing=0.0195)
        assert R3_3k < R3_0


# ===========================================================================
# Test 6: 3-node steady-state convergence
# ===========================================================================
class TestSteadyState:
    """thermal_model.simulate_3node steady-state tests."""

    def _run_steady_state(self) -> "SimResult":
        """Run a long simulation with constant inputs.

        Uses I=3A to keep Q_total ~14 W and SS rise ~40 degC (physically
        realistic for a small motor with these R-values).
        """
        from core.thermal_model import SimResult  # noqa: F811

        # Constant operating point — I=3A gives ~14 W total loss
        # Thermal time constant ~ C_total * R3 ~ 700 * 2.5 ~ 1750 s.
        # Positive R(T) feedback extends effective convergence time,
        # so simulate ~17 time constants (30000 s) for tight convergence.
        N = 500
        t = np.linspace(0, 30000.0, N)
        I = np.full(N, 3.0)
        rpm = np.full(N, 3000.0)
        T_amb = np.full(N, 25.0)

        masses = compute_thermal_masses(
            D_motor_mm=106.0, L_motor_mm=48.85, t_housing_mm=10.5,
            m_motor_g=1200.0, m_housing_g=350.0,
        )

        coil = CoilParams(R0=0.5, T0=20.0, alpha=0.00393, n_phases=3)
        iron = SimpleIronLoss(I_max=10.0, RPM_max=5000.0, alpha_iron=2.0)
        loss_fn = make_simple_loss_fn(coil, iron)

        result = simulate_3node(
            time_array=t, I_array=I, rpm_array=rpm, T_amb_array=T_amb,
            C_coil=masses.C_coil, C_core=masses.C_core, C_housing=masses.C_housing,
            R1=0.5, R2=0.1, h_nat=10.0, h_rpm=0.02,
            A_housing=masses.A_housing,
            loss_fn=loss_fn,
            T_init=25.0,
            mode="fast",
        )
        return result

    def test_T_coil_converges(self):
        """With constant I and RPM, T_coil must converge (dT/dt -> 0)."""
        result = self._run_steady_state()

        # Check that the last 10% of T_coil is within 1 degC of final value
        tail = result.T_coil[-50:]
        T_final = result.T_coil[-1]
        max_dev = float(np.max(np.abs(tail - T_final)))
        assert max_dev < 1.0, (
            f"T_coil did not converge: max deviation in tail = {max_dev:.2f} degC"
        )

    def test_T_coil_above_T_amb(self):
        """T_coil must be above ambient when current is flowing."""
        result = self._run_steady_state()
        assert result.T_coil[-1] > 25.0, (
            f"T_coil_final={result.T_coil[-1]:.2f} should be > T_amb=25.0"
        )

    def test_thermal_gradient(self):
        """T_coil > T_core > T_housing > T_amb in steady state."""
        result = self._run_steady_state()
        T1 = result.T_coil[-1]
        T2 = result.T_core[-1]
        T3 = result.T_housing[-1]
        assert T1 > T2 > T3 > 25.0, (
            f"Expected T_coil > T_core > T_housing > T_amb, "
            f"got {T1:.1f} > {T2:.1f} > {T3:.1f} > 25.0"
        )


# ===========================================================================
# Test 7: Calibration smoke test
# ===========================================================================
class TestCalibrationSmoke:
    """calibration.run_calibration with synthetic data."""

    def test_recovery(self):
        """Generate synthetic data from known params, then recover them.

        Uses I=3A for physically realistic heat generation (~14 W) and
        a moderate temperature rise (~40 degC).  The calibration should
        recover the ground-truth parameters within 40% for this smoke test.
        """
        # Ground-truth parameters
        R1_true = 0.5
        R2_true = 0.1
        h_nat_true = 10.0
        h_rpm_true = 0.02

        masses = compute_thermal_masses(
            D_motor_mm=106.0, L_motor_mm=48.85, t_housing_mm=10.5,
            m_motor_g=1200.0, m_housing_g=350.0,
        )

        coil = CoilParams(R0=0.5, T0=20.0, alpha=0.00393, n_phases=3)
        iron = SimpleIronLoss(I_max=10.0, RPM_max=5000.0, alpha_iron=2.0)
        loss_fn = make_simple_loss_fn(coil, iron)

        # Generate synthetic measurement with I=3A (realistic)
        N = 300
        t = np.linspace(0, 2000.0, N)
        I = np.full(N, 3.0)
        rpm = np.full(N, 3000.0)
        T_amb = np.full(N, 25.0)

        truth_sim = simulate_3node(
            time_array=t, I_array=I, rpm_array=rpm, T_amb_array=T_amb,
            C_coil=masses.C_coil, C_core=masses.C_core, C_housing=masses.C_housing,
            R1=R1_true, R2=R2_true, h_nat=h_nat_true, h_rpm=h_rpm_true,
            A_housing=masses.A_housing,
            loss_fn=loss_fn,
            T_init=25.0,
            mode="final",
        )
        T_coil_meas = truth_sim.T_coil

        # Run calibration starting from a perturbed initial guess
        settings = CalibSettings(
            n_starts=3,
            R1_init=0.3,
            R2_init=0.15,
            h_nat_init=8.0,
            h_rpm_init=0.03,
        )

        result = run_calibration(
            time_array=t,
            I_array=I,
            rpm_array=rpm,
            T_amb_array=T_amb,
            T_coil_meas=T_coil_meas,
            C_coil=masses.C_coil,
            C_core=masses.C_core,
            C_housing=masses.C_housing,
            A_housing=masses.A_housing,
            loss_fn=loss_fn,
            settings=settings,
        )

        # Check parameter recovery (within 40% for smoke test)
        assert abs(result.R1 - R1_true) / R1_true < 0.40, (
            f"R1: got {result.R1:.4f}, expected {R1_true}"
        )
        assert abs(result.R2 - R2_true) / R2_true < 0.40, (
            f"R2: got {result.R2:.4f}, expected {R2_true}"
        )
        assert abs(result.h_nat - h_nat_true) / h_nat_true < 0.40, (
            f"h_nat: got {result.h_nat:.4f}, expected {h_nat_true}"
        )
        assert abs(result.h_rpm - h_rpm_true) / h_rpm_true < 0.40, (
            f"h_rpm: got {result.h_rpm:.4f}, expected {h_rpm_true}"
        )

        # RMSE should be small (synthetic data, no noise)
        assert result.rmse < 5.0, f"RMSE={result.rmse:.2f} is too high"

        # R-squared should be close to 1
        assert result.r_squared > 0.95, f"R^2={result.r_squared:.4f} is too low"

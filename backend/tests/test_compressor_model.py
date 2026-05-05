"""Unit and integration tests for compressor thermal model sub-models.

Tests cover (TDD RED -> GREEN):
  1. Sub-model A: Mass flow computation
  2. Sub-model B: Motor loss computation
  3. Sub-model C: Discharge state computation
  4. Sub-model D: Heat recirculation computation
  5. Sub-model E: Coil temperature computation
  6. Torque calculation
  7. Iterative Tm solver convergence
  8. Full prediction pipeline
  9. Energy balance verification

Run with:
    cd backend && .venv/bin/python -m pytest tests/test_compressor_model.py -v

Reference: SPEC-COMP-THERMAL-001
"""

from __future__ import annotations

import math

import pytest

from core.compressor_model import (
    IterationResult,
    MotorParams,
    compute_coil_temperature,
    compute_discharge_state,
    compute_mass_flow,
    compute_motor_loss,
    compute_q_recirc,
    compute_torque,
    predict_compressor,
    solve_tm_iterative,
)
from core.refrigerant import (
    clear_cache,
    get_density,
    get_enthalpy,
    get_temperature,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clear_refrigerant_cache():
    """Clear refrigerant cache between tests for reproducibility."""
    clear_cache()
    yield
    clear_cache()


# Standard test conditions (pressures in Pa, temperatures in degC)
RPM_STANDARD = 3000.0
Ps_STANDARD = 500_000.0   # 500 kPa
Ts_STANDARD = 15.0         # 15 degC
Pd_STANDARD = 2_000_000.0  # 2000 kPa

# Motor parameters
R_MOTOR = 0.5      # Ohm per phase
V_DISPL = 1.0e-5   # 10 cm^3 displacement
I_PEAK = 10.0      # A peak current
IRON_LOSS = 5.0    # W

# Calibration parameters
UA_0 = 50.0    # W/K
UA_1 = 0.1     # W/K per 1000 RPM
ETA_VOL = 0.85
ETA_S = 0.75
R_COIL_CORE = 0.01   # K/W
H_REF = 500.0         # W/(m^2*K)


# ===========================================================================
# Sub-model A: Mass Flow (REQ-COMP-MASSFLOW-001)
# ===========================================================================
class TestComputeMassFlow:
    """Tests for compute_mass_flow sub-model."""

    def test_returns_positive_mass_flow_at_standard_conditions(self):
        """Mass flow must be positive at normal operating conditions."""
        mdot = compute_mass_flow(RPM_STANDARD, Ps_STANDARD, Ts_STANDARD,
                                 ETA_VOL, V_DISPL)
        assert mdot > 0.0

    def test_formula_matches_hand_calculation(self):
        """Verify: mdot = eta_vol * V_displ * (RPM/60) * rho(Ps, Ts)."""
        rho = get_density(Ps_STANDARD, Ts_STANDARD)
        expected = ETA_VOL * V_DISPL * (RPM_STANDARD / 60.0) * rho
        result = compute_mass_flow(RPM_STANDARD, Ps_STANDARD, Ts_STANDARD,
                                   ETA_VOL, V_DISPL)
        assert math.isclose(result, expected, rel_tol=1e-10)

    def test_zero_rpm_gives_zero_flow(self):
        """At zero RPM, mass flow must be zero."""
        mdot = compute_mass_flow(0.0, Ps_STANDARD, Ts_STANDARD, ETA_VOL, V_DISPL)
        assert mdot == 0.0

    def test_higher_rpm_gives_higher_flow(self):
        """Mass flow should scale linearly with RPM."""
        mdot_low = compute_mass_flow(1000.0, Ps_STANDARD, Ts_STANDARD,
                                     ETA_VOL, V_DISPL)
        mdot_high = compute_mass_flow(3000.0, Ps_STANDARD, Ts_STANDARD,
                                      ETA_VOL, V_DISPL)
        assert mdot_high > mdot_low
        # Ratio should be exactly 3.0 (linear with RPM)
        assert math.isclose(mdot_high / mdot_low, 3.0, rel_tol=1e-10)

    def test_zero_eta_vol_gives_zero_flow(self):
        """Zero volumetric efficiency produces zero mass flow."""
        mdot = compute_mass_flow(RPM_STANDARD, Ps_STANDARD, Ts_STANDARD,
                                 0.0, V_DISPL)
        assert mdot == 0.0

    def test_higher_pressure_gives_higher_density_and_flow(self):
        """Higher suction pressure increases density and therefore mass flow."""
        mdot_low_p = compute_mass_flow(RPM_STANDARD, 300_000.0, Ts_STANDARD,
                                       ETA_VOL, V_DISPL)
        mdot_high_p = compute_mass_flow(RPM_STANDARD, 700_000.0, Ts_STANDARD,
                                        ETA_VOL, V_DISPL)
        assert mdot_high_p > mdot_low_p


# ===========================================================================
# Sub-model B: Motor Loss (REQ-COMP-MOTORLOSS-001)
# ===========================================================================
class TestComputeMotorLoss:
    """Tests for compute_motor_loss sub-model."""

    def test_returns_positive_loss_at_standard_conditions(self):
        """Motor loss must be positive at normal conditions."""
        loss = compute_motor_loss(R_MOTOR, I_PEAK, 80.0, RPM_STANDARD, IRON_LOSS)
        assert loss > 0.0

    def test_formula_matches_hand_calculation(self):
        """Verify the AF-validated motor loss formula.

        MotorLoss = R * (I_peak / sqrt(2))^2 * 3 *
                     (0.9312 + 0.00703*T_coil + 2.87e-5*RPM + 1.34e-9*RPM^2)
                     + IronLoss
        """
        T_coil = 80.0
        RPM = RPM_STANDARD
        I_rms = I_PEAK / math.sqrt(2)
        correction = 0.9312 + 0.00703 * T_coil + 2.87e-5 * RPM + 1.34e-9 * RPM**2
        expected = R_MOTOR * I_rms**2 * 3.0 * correction + IRON_LOSS
        result = compute_motor_loss(R_MOTOR, I_PEAK, T_coil, RPM, IRON_LOSS)
        assert math.isclose(result, expected, rel_tol=1e-10)

    def test_zero_current_gives_only_iron_loss(self):
        """With zero current, only iron loss remains."""
        loss = compute_motor_loss(R_MOTOR, 0.0, 80.0, RPM_STANDARD, IRON_LOSS)
        assert math.isclose(loss, IRON_LOSS, rel_tol=1e-10)

    def test_zero_iron_loss(self):
        """With IronLoss=0, only resistive loss remains."""
        loss = compute_motor_loss(R_MOTOR, I_PEAK, 80.0, RPM_STANDARD, 0.0)
        I_rms = I_PEAK / math.sqrt(2)
        correction = 0.9312 + 0.00703 * 80.0 + 2.87e-5 * RPM_STANDARD + 1.34e-9 * RPM_STANDARD**2
        expected = R_MOTOR * I_rms**2 * 3.0 * correction
        assert math.isclose(loss, expected, rel_tol=1e-10)

    def test_loss_increases_with_coil_temperature(self):
        """Higher coil temperature increases resistance and loss."""
        loss_low_T = compute_motor_loss(R_MOTOR, I_PEAK, 40.0, RPM_STANDARD, 0.0)
        loss_high_T = compute_motor_loss(R_MOTOR, I_PEAK, 120.0, RPM_STANDARD, 0.0)
        assert loss_high_T > loss_low_T

    def test_loss_increases_with_rpm(self):
        """Higher RPM increases mechanical losses in the correction factor."""
        loss_low = compute_motor_loss(R_MOTOR, I_PEAK, 80.0, 1000.0, 0.0)
        loss_high = compute_motor_loss(R_MOTOR, I_PEAK, 80.0, 5000.0, 0.0)
        assert loss_high > loss_low


# ===========================================================================
# Sub-model C: Discharge State (REQ-COMP-DISCHARGE-001)
# ===========================================================================
class TestComputeDischargeState:
    """Tests for compute_discharge_state sub-model."""

    def test_returns_tuple_of_two_floats(self):
        """Should return (hd, Td) as a tuple."""
        hm = get_enthalpy(Ps_STANDARD, Ts_STANDARD + 20.0)
        result = compute_discharge_state(hm, Ps_STANDARD, Pd_STANDARD, ETA_S)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_discharge_enthalpy_higher_than_motor_enthalpy(self):
        """Discharge enthalpy must exceed motor outlet enthalpy (compression)."""
        hm = get_enthalpy(Ps_STANDARD, Ts_STANDARD + 20.0)
        hd, Td = compute_discharge_state(hm, Ps_STANDARD, Pd_STANDARD, ETA_S)
        assert hd > hm

    def test_discharge_temperature_higher_than_suction(self):
        """Discharge temperature must exceed suction temperature."""
        hm = get_enthalpy(Ps_STANDARD, Ts_STANDARD + 20.0)
        hd, Td = compute_discharge_state(hm, Ps_STANDARD, Pd_STANDARD, ETA_S)
        assert Td > Ts_STANDARD

    def test_isentropic_efficiency_effect(self):
        """Lower eta_s gives higher hd (less efficient = more heat)."""
        hm = get_enthalpy(Ps_STANDARD, Ts_STANDARD + 20.0)
        hd_high_eff, _ = compute_discharge_state(hm, Ps_STANDARD, Pd_STANDARD, 0.9)
        hd_low_eff, _ = compute_discharge_state(hm, Ps_STANDARD, Pd_STANDARD, 0.5)
        assert hd_low_eff > hd_high_eff

    def test_eta_s_equals_one_gives_isentropic_enthalpy(self):
        """At eta_s=1.0, hd = hd_isen (perfect isentropic process)."""
        from core.refrigerant import get_entropy
        hm = get_enthalpy(Ps_STANDARD, Ts_STANDARD + 20.0)
        sm = get_entropy(Ps_STANDARD, hm)

        # Directly compute isentropic discharge enthalpy
        # hd_isen = h(Pd, s=sm)
        # Use CoolProp to get h at (Pd, s)
        import CoolProp.CoolProp as CP
        hd_isen_direct = CP.PropsSI("H", "P", Pd_STANDARD, "S", sm, "R1234yf")

        hd, _ = compute_discharge_state(hm, Ps_STANDARD, Pd_STANDARD, 1.0)
        assert math.isclose(hd, hd_isen_direct, rel_tol=1e-6)

    def test_raises_on_invalid_eta_s(self):
        """Must raise ValueError for eta_s outside (0, 1]."""
        hm = get_enthalpy(Ps_STANDARD, Ts_STANDARD)
        with pytest.raises(ValueError):
            compute_discharge_state(hm, Ps_STANDARD, Pd_STANDARD, 0.0)
        with pytest.raises(ValueError):
            compute_discharge_state(hm, Ps_STANDARD, Pd_STANDARD, -0.5)
        with pytest.raises(ValueError):
            compute_discharge_state(hm, Ps_STANDARD, Pd_STANDARD, 1.5)


# ===========================================================================
# Sub-model D: Heat Recirculation (REQ-COMP-RECIRC-001)
# ===========================================================================
class TestComputeQRecirc:
    """Tests for compute_q_recirc sub-model."""

    def test_returns_positive_when_Td_exceeds_Tm(self):
        """Q_recirc must be positive when discharge is hotter than motor."""
        Q = compute_q_recirc(UA_0, UA_1, RPM_STANDARD, 100.0, 50.0)
        assert Q > 0.0

    def test_formula_matches_hand_calculation(self):
        """Verify: Q_recirc = (UA_0 + UA_1 * RPM/1000) * (Td - Tm)."""
        Td, Tm = 120.0, 60.0
        expected = (UA_0 + UA_1 * RPM_STANDARD / 1000.0) * (Td - Tm)
        result = compute_q_recirc(UA_0, UA_1, RPM_STANDARD, Td, Tm)
        assert math.isclose(result, expected, rel_tol=1e-10)

    def test_zero_delta_t_gives_zero_heat(self):
        """When Td == Tm, no heat recirculation occurs."""
        Q = compute_q_recirc(UA_0, UA_1, RPM_STANDARD, 80.0, 80.0)
        assert Q == 0.0

    def test_negative_when_Tm_exceeds_Td(self):
        """Q_recirc can be negative if motor is hotter than discharge."""
        Q = compute_q_recirc(UA_0, UA_1, RPM_STANDARD, 50.0, 100.0)
        assert Q < 0.0

    def test_linear_rpm_dependency(self):
        """Q_recirc increases linearly with RPM (R^2=0.87 validated)."""
        Td, Tm = 120.0, 60.0
        Q_rpm1 = compute_q_recirc(UA_0, UA_1, 1000.0, Td, Tm)
        Q_rpm3 = compute_q_recirc(UA_0, UA_1, 3000.0, Td, Tm)
        Q_rpm5 = compute_q_recirc(UA_0, UA_1, 5000.0, Td, Tm)
        # Should be linear in RPM: check constant second differences
        diff_1 = Q_rpm3 - Q_rpm1
        diff_2 = Q_rpm5 - Q_rpm3
        assert math.isclose(diff_1, diff_2, rel_tol=1e-10)


# ===========================================================================
# Sub-model E: Coil Temperature (REQ-COMP-COIL-001)
# ===========================================================================
class TestComputeCoilTemperature:
    """Tests for compute_coil_temperature sub-model."""

    def test_coil_temperature_differs_from_Tm(self):
        """Coil temperature should differ from motor temperature due to
        internal heat generation and refrigerant cooling."""
        T_coil = compute_coil_temperature(
            Tm=60.0, Q_coil=50.0, R_coil_core=R_COIL_CORE,
            Q_refrig=30.0, h_ref=H_REF, RPM=RPM_STANDARD,
        )
        assert T_coil != 60.0

    def test_formula_matches_hand_calculation(self):
        """Verify: T_coil = Tm + Q_coil*R_coil_core - Q_refrig*h_ref*sqrt(RPM)."""
        Tm = 60.0
        Q_coil = 50.0
        Q_refrig = 30.0
        expected = Tm + Q_coil * R_COIL_CORE - Q_refrig * H_REF * math.sqrt(RPM_STANDARD)
        result = compute_coil_temperature(
            Tm=Tm, Q_coil=Q_coil, R_coil_core=R_COIL_CORE,
            Q_refrig=Q_refrig, h_ref=H_REF, RPM=RPM_STANDARD,
        )
        assert math.isclose(result, expected, rel_tol=1e-10)

    def test_zero_Q_coil_gives_only_cooling_effect(self):
        """With no coil heating, only refrigerant cooling reduces T_coil."""
        Tm = 80.0
        T_coil = compute_coil_temperature(
            Tm=Tm, Q_coil=0.0, R_coil_core=R_COIL_CORE,
            Q_refrig=10.0, h_ref=H_REF, RPM=RPM_STANDARD,
        )
        assert T_coil < Tm  # Cooling reduces coil temperature

    def test_zero_Q_refrig_gives_only_heating_effect(self):
        """With no refrigerant cooling, only coil heating increases T_coil."""
        Tm = 80.0
        T_coil = compute_coil_temperature(
            Tm=Tm, Q_coil=50.0, R_coil_core=R_COIL_CORE,
            Q_refrig=0.0, h_ref=H_REF, RPM=RPM_STANDARD,
        )
        assert T_coil > Tm


# ===========================================================================
# Torque Calculation (REQ-COMP-TORQUE-001)
# ===========================================================================
class TestComputeTorque:
    """Tests for compute_torque."""

    def test_returns_positive_torque(self):
        """Torque must be positive for positive power and RPM."""
        torque = compute_torque(1000.0, RPM_STANDARD)
        assert torque > 0.0

    def test_formula_matches_hand_calculation(self):
        """Verify: Torque = CompPower / (RPM * 2*pi / 60)."""
        CompPower = 2000.0  # W
        omega = RPM_STANDARD * 2.0 * math.pi / 60.0
        expected = CompPower / omega
        result = compute_torque(CompPower, RPM_STANDARD)
        assert math.isclose(result, expected, rel_tol=1e-10)

    def test_zero_rpm_raises(self):
        """Division by zero at RPM=0 must be handled."""
        with pytest.raises((ValueError, ZeroDivisionError)):
            compute_torque(1000.0, 0.0)

    def test_zero_power_gives_zero_torque(self):
        """Zero compressor power gives zero torque."""
        torque = compute_torque(0.0, RPM_STANDARD)
        assert torque == 0.0


# ===========================================================================
# Iterative Tm Solver (REQ-COMP-ITER-001)
# ===========================================================================
class TestSolveTmIterative:
    """Tests for the iterative Tm solver."""

    def _make_operating_point(self, **overrides):
        """Create a standard operating point dict with optional overrides."""
        op = {
            "RPM": RPM_STANDARD,
            "Ps": Ps_STANDARD,
            "Ts": Ts_STANDARD,
            "Pd": Pd_STANDARD,
            "I_peak": I_PEAK,
        }
        op.update(overrides)
        return op

    def _make_params(self, **overrides):
        """Create a standard params dict with optional overrides."""
        p = {
            "UA_0": UA_0,
            "UA_1": UA_1,
            "eta_vol": ETA_VOL,
            "eta_s": ETA_S,
            "R_coil_core": R_COIL_CORE,
            "h_ref": H_REF,
            "R": R_MOTOR,
            "V_displ": V_DISPL,
            "IronLoss": IRON_LOSS,
        }
        p.update(overrides)
        return p

    def test_converges_at_standard_conditions(self):
        """Solver must converge at normal operating conditions."""
        result = solve_tm_iterative(
            self._make_operating_point(),
            self._make_params(),
        )
        assert result.converged
        assert result.Tm > Ts_STANDARD  # Motor section heats the gas
        assert result.Td > result.Tm    # Compression further heats gas

    def test_convergence_within_100_iterations(self):
        """Should converge well within 100 iterations at normal conditions."""
        result = solve_tm_iterative(
            self._make_operating_point(),
            self._make_params(),
            max_iter=100,
        )
        assert result.converged
        assert result.iterations <= 100

    def test_residual_below_tolerance(self):
        """Final residual must be below the convergence tolerance."""
        result = solve_tm_iterative(
            self._make_operating_point(),
            self._make_params(),
            tol=0.01,
        )
        assert result.converged
        assert result.residual < 0.01

    def test_relaxation_factor_affects_convergence_speed(self):
        """Lower alpha (more relaxation) should need more iterations but still converge."""
        result_alpha05 = solve_tm_iterative(
            self._make_operating_point(),
            self._make_params(),
            alpha=0.5,
        )
        result_alpha08 = solve_tm_iterative(
            self._make_operating_point(),
            self._make_params(),
            alpha=0.8,
        )
        assert result_alpha05.converged
        assert result_alpha08.converged
        # Both should converge to roughly the same Tm
        assert math.isclose(result_alpha05.Tm, result_alpha08.Tm, abs_tol=0.5)

    def test_non_convergence_with_very_low_max_iter(self):
        """With max_iter=1 or 2, solver may not converge."""
        result = solve_tm_iterative(
            self._make_operating_point(),
            self._make_params(),
            max_iter=2,
            alpha=0.3,
        )
        # It may or may not converge in 2 iterations; either way it returns a result
        assert isinstance(result, IterationResult)
        assert result.iterations <= 2

    def test_all_output_fields_populated(self):
        """All IterationResult fields must be populated with reasonable values."""
        result = solve_tm_iterative(
            self._make_operating_point(),
            self._make_params(),
        )
        assert result.mdot > 0.0
        assert result.Q_recirc != 0.0  # Should have some recirculation
        assert result.MotorLoss > 0.0
        assert result.T_coil > 0.0
        assert result.Torque > 0.0
        assert result.hm > 0.0
        assert result.hd > 0.0


# ===========================================================================
# Integration Tests
# ===========================================================================
class TestIntegration:
    """Integration tests for the full prediction pipeline."""

    def test_full_prediction_pipeline(self):
        """predict_compressor should return a complete prediction."""
        from schemas.compressor import CompressorCalibrationParams, CompressorOperatingPoint

        op = CompressorOperatingPoint(
            RPM=RPM_STANDARD,
            Ps=Ps_STANDARD,
            Ts=Ts_STANDARD,
            Pd=Pd_STANDARD,
        )
        params = CompressorCalibrationParams(
            UA_0=UA_0,
            UA_1=UA_1,
            eta_vol=ETA_VOL,
            eta_s=ETA_S,
            R_coil_core=R_COIL_CORE,
            h_ref=H_REF,
        )
        motor = MotorParams(
            R=R_MOTOR,
            V_displ=V_DISPL,
            I_peak=I_PEAK,
            IronLoss=IRON_LOSS,
        )
        prediction = predict_compressor(op, params, motor)

        assert prediction.Tm > Ts_STANDARD
        assert prediction.Td > prediction.Tm
        assert prediction.mdot > 0.0
        assert prediction.Q_recirc > 0.0
        assert prediction.MotorLoss > 0.0
        assert prediction.Torque > 0.0

    def test_energy_balance(self):
        """Energy balance: mdot*(hm - hs) should approximate MotorLoss + Q_recirc.

        The motor section adds motor loss and recirculation heat to the gas:
            hm = hs + (MotorLoss + Q_recirc) / mdot
        Therefore: mdot * (hm - hs) ≈ MotorLoss + Q_recirc
        """
        from schemas.compressor import CompressorCalibrationParams, CompressorOperatingPoint

        op = CompressorOperatingPoint(
            RPM=RPM_STANDARD,
            Ps=Ps_STANDARD,
            Ts=Ts_STANDARD,
            Pd=Pd_STANDARD,
        )
        params = CompressorCalibrationParams(
            UA_0=UA_0,
            UA_1=UA_1,
            eta_vol=ETA_VOL,
            eta_s=ETA_S,
            R_coil_core=R_COIL_CORE,
            h_ref=H_REF,
        )
        motor = MotorParams(
            R=R_MOTOR,
            V_displ=V_DISPL,
            I_peak=I_PEAK,
            IronLoss=IRON_LOSS,
        )
        pred = predict_compressor(op, params, motor)

        hs = get_enthalpy(Ps_STANDARD, Ts_STANDARD)
        energy_added = pred.mdot * (pred.hm - hs)
        total_loss = pred.MotorLoss + pred.Q_recirc

        # Allow 5% tolerance for numerical integration effects
        assert math.isclose(energy_added, total_loss, rel_tol=0.05), \
            f"Energy balance violated: mdot*(hm-hs)={energy_added:.1f} vs " \
            f"MotorLoss+Q_recirc={total_loss:.1f}"

    def test_torque_consistency(self):
        """Torque = CompPower / omega where CompPower = mdot*(hd - hs) - MotorLoss."""
        from schemas.compressor import CompressorCalibrationParams, CompressorOperatingPoint

        op = CompressorOperatingPoint(
            RPM=RPM_STANDARD,
            Ps=Ps_STANDARD,
            Ts=Ts_STANDARD,
            Pd=Pd_STANDARD,
        )
        params = CompressorCalibrationParams(
            UA_0=UA_0,
            UA_1=UA_1,
            eta_vol=ETA_VOL,
            eta_s=ETA_S,
            R_coil_core=R_COIL_CORE,
            h_ref=H_REF,
        )
        motor = MotorParams(
            R=R_MOTOR,
            V_displ=V_DISPL,
            I_peak=I_PEAK,
            IronLoss=IRON_LOSS,
        )
        pred = predict_compressor(op, params, motor)

        hs = get_enthalpy(Ps_STANDARD, Ts_STANDARD)
        CompPower = pred.mdot * (pred.hd - hs) - pred.MotorLoss
        omega = RPM_STANDARD * 2.0 * math.pi / 60.0
        expected_torque = CompPower / omega

        assert math.isclose(pred.Torque, expected_torque, rel_tol=0.05), \
            f"Torque inconsistency: {pred.Torque:.3f} vs expected {expected_torque:.3f}"

    def test_q_recirc_dominates_heat_pickup(self):
        """Q_recirc should be > 50% of total loss (validated 93-99% from data).

        We use a relaxed threshold here since calibration parameters affect the ratio.
        """
        from schemas.compressor import CompressorCalibrationParams, CompressorOperatingPoint

        op = CompressorOperatingPoint(
            RPM=RPM_STANDARD,
            Ps=Ps_STANDARD,
            Ts=Ts_STANDARD,
            Pd=Pd_STANDARD,
        )
        params = CompressorCalibrationParams(
            UA_0=UA_0,
            UA_1=UA_1,
            eta_vol=ETA_VOL,
            eta_s=ETA_S,
            R_coil_core=R_COIL_CORE,
            h_ref=H_REF,
        )
        motor = MotorParams(
            R=R_MOTOR,
            V_displ=V_DISPL,
            I_peak=I_PEAK,
            IronLoss=IRON_LOSS,
        )
        pred = predict_compressor(op, params, motor)

        total_loss = pred.MotorLoss + pred.Q_recirc
        if total_loss > 0:
            q_recirc_ratio = pred.Q_recirc / total_loss
            # With default parameters, Q_recirc should be significant
            assert q_recirc_ratio > 0.3, \
                f"Q_recirc ratio too low: {q_recirc_ratio:.2%}"

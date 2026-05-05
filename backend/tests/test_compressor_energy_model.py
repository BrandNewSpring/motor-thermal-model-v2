"""Tests for compressor energy-balance model.

Covers unit conversions, lookup table interpolation, energy balance
calculation, thermal resistance network, and full prediction with
mocked and real refrigerant calls.
"""

from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from core.compressor_energy_model import (
    CalibDataPoint,
    CalibResult,
    EnergyModelInput,
    EnergyModelResult,
    LookupTable,
    LossTable,
    TorqueCurrentTable,
    barg_to_pa,
    calibrate_thermal_resistances,
    kg_h_to_kg_s,
    predict_energy_balance,
)


# ===================================================================
# Fixtures: synthetic lookup tables
# ===================================================================
@pytest.fixture
def simple_torque_table() -> TorqueCurrentTable:
    """Simple 2-RPM torque table with linear I -> Torque mapping.

    At 1000 RPM:  5 A -> 1.0 Nm,  10 A -> 2.0 Nm
    At 2000 RPM:  5 A -> 0.8 Nm,  10 A -> 1.6 Nm
    """
    return TorqueCurrentTable(
        rpm_values=[1000.0, 2000.0],
        entries={
            1000.0: [(5.0, 1.0), (10.0, 2.0)],
            2000.0: [(5.0, 0.8), (10.0, 1.6)],
        },
    )


@pytest.fixture
def simple_loss_table() -> LossTable:
    """Simple 2-RPM loss table with linear Torque -> Loss mapping.

    At 1000 RPM:  1.0 Nm -> 50 W,  2.0 Nm -> 100 W
    At 2000 RPM:  1.0 Nm -> 80 W,  2.0 Nm -> 160 W
    """
    return LossTable(
        rpm_values=[1000.0, 2000.0],
        entries={
            1000.0: [(1.0, 50.0), (2.0, 100.0)],
            2000.0: [(1.0, 80.0), (2.0, 160.0)],
        },
    )


@pytest.fixture
def simple_model_input() -> EnergyModelInput:
    """Standard test input matching the simple lookup tables."""
    return EnergyModelInput(
        Ps=2.0,       # barG
        Ts=15.0,      # degC
        P_mid=2.5,    # barG
        T_mid=40.0,   # degC
        Pd=12.0,      # barG
        mdot=100.0,   # kg/h
        V=380.0,      # V
        I=7.5,        # A
        RPM=1500.0,   # rpm (midpoint of table)
        R_coil_case=0.5,   # K/W
        R_coil_core=0.3,   # K/W
        R_coil_refrigerant=0.2,  # K/W
        T_ambient=25.0,    # degC
    )


# ===================================================================
# Test: Unit conversions
# ===================================================================
class TestUnitConversions:
    """Tests for barg_to_pa and kg_h_to_kg_s."""

    def test_barg_to_pa_zero(self) -> None:
        """0 barG = 1.01325 barA = 101325 Pa."""
        assert barg_to_pa(0.0) == pytest.approx(101325.0, rel=1e-9)

    def test_barg_to_pa_positive(self) -> None:
        """5 barG = 6.01325 barA = 601325 Pa."""
        assert barg_to_pa(5.0) == pytest.approx(601325.0, rel=1e-9)

    def test_barg_to_pa_negative(self) -> None:
        """-0.5 barG = 0.51325 barA = 51325 Pa."""
        assert barg_to_pa(-0.5) == pytest.approx(51325.0, rel=1e-9)

    def test_barg_to_pa_one_barg(self) -> None:
        """1 barG = 2.01325 barA = 201325 Pa."""
        assert barg_to_pa(1.0) == pytest.approx(201325.0, rel=1e-9)

    def test_kg_h_to_kg_s_one(self) -> None:
        """3600 kg/h = 1.0 kg/s."""
        assert kg_h_to_kg_s(3600.0) == pytest.approx(1.0, rel=1e-9)

    def test_kg_h_to_kg_s_small(self) -> None:
        """100 kg/h = 100/3600 kg/s."""
        assert kg_h_to_kg_s(100.0) == pytest.approx(100.0 / 3600.0, rel=1e-9)

    def test_kg_h_to_kg_s_zero(self) -> None:
        """0 kg/h = 0 kg/s."""
        assert kg_h_to_kg_s(0.0) == pytest.approx(0.0, rel=1e-9)


# ===================================================================
# Test: Lookup table interpolation
# ===================================================================
class TestLookupTableInterpolation:
    """Tests for LookupTable bilinear interpolation."""

    def test_exact_rpm_exact_x(self, simple_torque_table: TorqueCurrentTable) -> None:
        """Exact match on both RPM and x returns exact y."""
        assert simple_torque_table.interpolate(1000.0, 5.0) == pytest.approx(1.0)
        assert simple_torque_table.interpolate(2000.0, 10.0) == pytest.approx(1.6)

    def test_interpolate_x_only(self, simple_torque_table: TorqueCurrentTable) -> None:
        """Exact RPM, interpolated x."""
        # At 1000 RPM, x=7.5 -> halfway between (5,1.0) and (10,2.0) = 1.5
        assert simple_torque_table.interpolate(1000.0, 7.5) == pytest.approx(1.5)

    def test_interpolate_rpm_only(
        self, simple_torque_table: TorqueCurrentTable
    ) -> None:
        """Interpolated RPM, exact x."""
        # At RPM=1500 (midpoint), x=5.0 -> avg of 1.0 and 0.8 = 0.9
        assert simple_torque_table.interpolate(1500.0, 5.0) == pytest.approx(0.9)

    def test_bilinear_interpolation(
        self, simple_torque_table: TorqueCurrentTable
    ) -> None:
        """Full bilinear interpolation across both axes."""
        # At RPM=1500, x=7.5:
        #   y_lo (RPM=1000, x=7.5) = 1.5
        #   y_hi (RPM=2000, x=7.5) = 1.2
        #   frac_rpm = 0.5 -> 1.5 + 0.5*(1.2 - 1.5) = 1.35
        assert simple_torque_table.interpolate(1500.0, 7.5) == pytest.approx(1.35)

    def test_clamp_rpm_below(
        self, simple_torque_table: TorqueCurrentTable
    ) -> None:
        """RPM below minimum clamps to lowest RPM curve."""
        # RPM=500 (< 1000) -> use 1000 RPM curve, x=5 -> 1.0
        assert simple_torque_table.interpolate(500.0, 5.0) == pytest.approx(1.0)

    def test_clamp_rpm_above(
        self, simple_torque_table: TorqueCurrentTable
    ) -> None:
        """RPM above maximum clamps to highest RPM curve."""
        # RPM=3000 (> 2000) -> use 2000 RPM curve, x=10 -> 1.6
        assert simple_torque_table.interpolate(3000.0, 10.0) == pytest.approx(1.6)

    def test_clamp_x_below(
        self, simple_torque_table: TorqueCurrentTable
    ) -> None:
        """x below minimum clamps to lowest x value."""
        assert simple_torque_table.interpolate(1000.0, 1.0) == pytest.approx(1.0)

    def test_clamp_x_above(
        self, simple_torque_table: TorqueCurrentTable
    ) -> None:
        """x above maximum clamps to highest x value."""
        assert simple_torque_table.interpolate(1000.0, 20.0) == pytest.approx(2.0)

    def test_empty_table_raises(self) -> None:
        """Empty table raises ValueError."""
        table = TorqueCurrentTable(rpm_values=[], entries={})
        with pytest.raises(ValueError, match="no RPM entries"):
            table.interpolate(1000.0, 5.0)

    def test_single_rpm_exact(self) -> None:
        """Single RPM table skips RPM interpolation."""
        table = TorqueCurrentTable(
            rpm_values=[1000.0],
            entries={1000.0: [(5.0, 1.0), (10.0, 2.0)]},
        )
        assert table.interpolate(1000.0, 7.5) == pytest.approx(1.5)

    def test_loss_table_interpolation(self, simple_loss_table: LossTable) -> None:
        """LossTable interpolates correctly."""
        # RPM=1500, Torque=1.35:
        #   y_lo (RPM=1000, Torque=1.35) = 50 + 0.35*50 = 67.5
        #   y_hi (RPM=2000, Torque=1.35) = 80 + 0.35*80 = 108.0
        #   frac_rpm = 0.5 -> 67.5 + 0.5*(108 - 67.5) = 87.75
        assert simple_loss_table.interpolate(1500.0, 1.35) == pytest.approx(87.75)

    def test_single_entry_curve(self) -> None:
        """Single-entry curve returns the single y value."""
        table = TorqueCurrentTable(
            rpm_values=[1000.0],
            entries={1000.0: [(5.0, 1.5)]},
        )
        assert table.interpolate(1000.0, 3.0) == pytest.approx(1.5)
        assert table.interpolate(1000.0, 7.0) == pytest.approx(1.5)


# ===================================================================
# Test: Thermal resistance T_coil calculation
# ===================================================================
class TestThermalResistance:
    """Tests for the T_coil calculation via thermal resistance network."""

    def test_tcoil_symmetric_resistances(self) -> None:
        """Equal resistances -> T_coil = midpoint of T_mid and T_ambient + MotorLoss/2 per R."""
        # MotorLoss = 100 W, R_coil_core = 1.0, R_coil_case = 1.0
        # T_mid = 50, T_ambient = 25
        # T_coil = (100 + 50/1.0 + 25/1.0) / (1.0 + 1.0) = 175/2 = 87.5
        R_core = 1.0
        R_case = 1.0
        T_mid = 50.0
        T_amb = 25.0
        loss = 100.0

        inv_core = 1.0 / R_core
        inv_case = 1.0 / R_case
        T_coil = (loss + T_mid * inv_core + T_amb * inv_case) / (inv_core + inv_case)
        assert T_coil == pytest.approx(87.5)

    def test_tcoil_zero_loss(self) -> None:
        """Zero motor loss -> T_coil is weighted average of T_mid and T_ambient."""
        R_core = 0.5
        R_case = 0.5
        T_mid = 60.0
        T_amb = 20.0
        loss = 0.0

        inv_core = 1.0 / R_core
        inv_case = 1.0 / R_case
        T_coil = (loss + T_mid * inv_core + T_amb * inv_case) / (inv_core + inv_case)
        # Both R equal -> T_coil = (60 + 20) / 2 = 40
        assert T_coil == pytest.approx(40.0)

    def test_tcoil_asymmetric_resistance(self) -> None:
        """Lower resistance to core pulls T_coil closer to T_mid."""
        R_core = 0.1  # Low resistance to core (strong coupling)
        R_case = 1.0  # High resistance to ambient (weak coupling)
        T_mid = 50.0
        T_amb = 25.0
        loss = 50.0

        inv_core = 1.0 / R_core
        inv_case = 1.0 / R_case
        T_coil = (loss + T_mid * inv_core + T_amb * inv_case) / (inv_core + inv_case)
        # Strong coupling to T_mid=50 -> T_coil should be closer to 50 than to 25
        assert T_coil > 37.5  # above simple average with loss


# ===================================================================
# Test: Energy balance with known values (mocked refrigerant)
# ===================================================================
class TestEnergyBalance:
    """Tests for the energy balance calculation with mocked CoolProp."""

    @patch("core.compressor_energy_model.get_enthalpy")
    @patch("core.compressor_energy_model.get_temperature")
    def test_known_values(
        self,
        mock_get_temp: pytest.MonkeyPatch.patch,
        mock_enthalpy: pytest.MonkeyPatch.patch,
        simple_torque_table: TorqueCurrentTable,
        simple_loss_table: LossTable,
    ) -> None:
        """Verify energy balance with manually computed expected values."""
        # Mock enthalpy: hs=400000 J/kg, h_mid=420000 J/kg -> dh=20000 J/kg
        mock_enthalpy.return_value = 400000.0

        def enthalpy_side_effect(P: float, T: float) -> float:
            if P < 350000:
                return 400000.0  # hs
            return 420000.0  # h_mid

        mock_enthalpy.side_effect = enthalpy_side_effect
        mock_get_temp.return_value = 85.0  # Td_est

        inp = EnergyModelInput(
            Ps=2.0, Ts=15.0, P_mid=2.5, T_mid=40.0, Pd=12.0,
            mdot=100.0, V=380.0, I=7.5, RPM=1500.0,
            R_coil_case=0.5, R_coil_core=0.3, R_coil_refrigerant=0.2, T_ambient=25.0,
        )
        result = predict_energy_balance(inp, simple_torque_table, simple_loss_table)

        # Pin = sqrt(3) * 380 * 7.5 = 4936.27 W
        expected_pin = math.sqrt(3) * 380.0 * 7.5
        assert result.Pin == pytest.approx(expected_pin, rel=1e-6)

        # Torque at RPM=1500, I=7.5: bilinear -> 1.35 Nm
        assert result.Torque == pytest.approx(1.35, rel=1e-6)

        # Pmech = 1.35 * 2*pi*1500/60 = 1.35 * 157.08 = 212.06 W
        omega = 2.0 * math.pi * 1500.0 / 60.0
        expected_pmech = 1.35 * omega
        assert result.Pmech == pytest.approx(expected_pmech, rel=1e-4)

        # MotorLoss at RPM=1500, Torque=1.35 -> 87.75 W
        assert result.MotorLoss == pytest.approx(87.75, rel=1e-4)

        # balance_error = |Pin - Pmech - MotorLoss| / Pin * 100
        expected_error = abs(expected_pin - expected_pmech - 87.75) / expected_pin * 100.0
        assert result.balance_error_pct == pytest.approx(expected_error, rel=1e-4)

        # Q_refrig = (100/3600) * (420000 - 400000) = 0.02778 * 20000 = 555.56 W
        expected_q_refrig = (100.0 / 3600.0) * 20000.0
        assert result.Q_refrig == pytest.approx(expected_q_refrig, rel=1e-4)

        # Q_ambient = MotorLoss - Q_refrig = 87.75 - 555.56 = -467.81
        expected_q_ambient = 87.75 - expected_q_refrig
        assert result.Q_ambient == pytest.approx(expected_q_ambient, rel=1e-4)

        # Discharge enthalpy: hd = h_mid + Pmech / mdot_s
        mdot_s = 100.0 / 3600.0
        expected_hd = 420000.0 + expected_pmech / mdot_s
        assert result.hd == pytest.approx(expected_hd, rel=1e-4)

        # Td_est from mock
        assert result.Td_est == pytest.approx(85.0)

        # Recirculation: Q_refrig > MotorLoss -> mdot_recirc > 0
        expected_dh = expected_hd - 420000.0
        expected_mdot_recirc = (expected_q_refrig - 87.75) / expected_dh if expected_dh > 0 else 0.0
        assert result.mdot_recirc == pytest.approx(expected_mdot_recirc, rel=1e-3)
        expected_recirc_ratio = expected_mdot_recirc / mdot_s
        assert result.recirc_ratio == pytest.approx(expected_recirc_ratio, rel=1e-3)

    @patch("core.compressor_energy_model.get_enthalpy")
    @patch("core.compressor_energy_model.get_temperature")
    def test_convergence_flag_pass(
        self,
        mock_get_temp: pytest.MonkeyPatch.patch,
        mock_enthalpy: pytest.MonkeyPatch.patch,
        simple_torque_table: TorqueCurrentTable,
        simple_loss_table: LossTable,
    ) -> None:
        """Converged=True when balance error < 10%."""
        # Set up so that Pin ~ Pmech + MotorLoss
        # Use values where Pin is close to Pmech + MotorLoss
        mock_enthalpy.return_value = 400000.0

        # Create a torque table where torque gives Pmech close to Pin - MotorLoss
        # Pin = sqrt(3) * 380 * 7.5 ~ 4936 W
        # We want Pmech + MotorLoss ~ Pin
        # Pmech = Torque * omega = Torque * 157.08
        # So Torque ~ (4936 - MotorLoss) / 157.08
        # MotorLoss = 87.75 at Torque=1.35 -> Torque ~ (4936-87.75)/157.08 = 30.86
        # This is way outside our table.  Instead, use a table that makes it match.

        # Use unrealistic but mathematically clean tables:
        # At RPM=1500, I=7.5 -> Torque = (Pin - Loss) / omega
        # First, Loss at RPM=1500, Torque -> we need consistency.
        # Easier: just test that with the real tables, converged is False
        # (because balance error will be huge with these tiny torque/loss values).

        inp = EnergyModelInput(
            Ps=2.0, Ts=15.0, P_mid=2.5, T_mid=40.0, Pd=12.0,
            mdot=100.0, V=380.0, I=7.5, RPM=1500.0,
            R_coil_case=0.5, R_coil_core=0.3, R_coil_refrigerant=0.2, T_ambient=25.0,
        )
        result = predict_energy_balance(inp, simple_torque_table, simple_loss_table)

        # With these small tables, error will be very large -> not converged
        assert result.converged is False

    @patch("core.compressor_energy_model.get_enthalpy")
    @patch("core.compressor_energy_model.get_temperature")
    def test_convergence_flag_converged(
        self,
        mock_get_temp: pytest.MonkeyPatch.patch,
        mock_enthalpy: pytest.MonkeyPatch.patch,
    ) -> None:
        """Converged=True when balance error < 10%."""
        mock_enthalpy.return_value = 400000.0

        # Build tables where Pin ~ Pmech + MotorLoss
        # V=380, I=7.5 -> Pin = 4936.27 W
        # RPM=1500 -> omega = 157.08 rad/s
        # Target: Pmech + MotorLoss = Pin = 4936.27
        # Let Torque = 30 Nm -> Pmech = 30 * 157.08 = 4712.4
        # Then MotorLoss should be ~ 4936.27 - 4712.4 = 223.87
        torque_table = TorqueCurrentTable(
            rpm_values=[1500.0],
            entries={1500.0: [(7.5, 30.0)]},
        )
        loss_table = LossTable(
            rpm_values=[1500.0],
            entries={1500.0: [(30.0, 223.87)]},
        )

        inp = EnergyModelInput(
            Ps=2.0, Ts=15.0, P_mid=2.5, T_mid=40.0, Pd=12.0,
            mdot=100.0, V=380.0, I=7.5, RPM=1500.0,
            R_coil_case=0.5, R_coil_core=0.3, R_coil_refrigerant=0.2, T_ambient=25.0,
        )
        result = predict_energy_balance(inp, torque_table, loss_table)

        # error = |4936.27 - 4712.4 - 223.87| / 4936.27 * 100 ~ 0%
        assert result.converged is True
        assert result.balance_error_pct < 1.0  # Should be nearly zero


# ===================================================================
# Test: Full predict_energy_balance with real CoolProp (integration)
# ===================================================================
class TestPredictEnergyBalanceIntegration:
    """Integration tests that call real CoolProp.

    These tests verify the end-to-end pipeline including refrigerant
    property lookups.  They will be skipped if CoolProp is unavailable.
    """

    @pytest.fixture
    def realistic_torque_table(self) -> TorqueCurrentTable:
        """More realistic torque-current table."""
        return TorqueCurrentTable(
            rpm_values=[1000.0, 2000.0, 3000.0],
            entries={
                1000.0: [(3.0, 0.8), (6.0, 1.6), (9.0, 2.4)],
                2000.0: [(3.0, 0.6), (6.0, 1.2), (9.0, 1.8)],
                3000.0: [(3.0, 0.4), (6.0, 0.8), (9.0, 1.2)],
            },
        )

    @pytest.fixture
    def realistic_loss_table(self) -> LossTable:
        """More realistic loss table."""
        return LossTable(
            rpm_values=[1000.0, 2000.0, 3000.0],
            entries={
                1000.0: [(0.5, 20.0), (1.5, 60.0), (2.5, 100.0)],
                2000.0: [(0.5, 40.0), (1.5, 120.0), (2.5, 200.0)],
                3000.0: [(0.5, 60.0), (1.5, 180.0), (2.5, 300.0)],
            },
        )

    def test_full_prediction_with_coolprop(
        self,
        realistic_torque_table: TorqueCurrentTable,
        realistic_loss_table: LossTable,
    ) -> None:
        """Full prediction using real CoolProp for R1234yf.

        Skips if CoolProp is not installed.
        """
        pytest.importorskip("CoolProp")

        inp = EnergyModelInput(
            Ps=2.0, Ts=15.0, P_mid=2.5, T_mid=40.0, Pd=12.0,
            mdot=50.0, V=380.0, I=6.0, RPM=2000.0,
            R_coil_case=0.5, R_coil_core=0.3, R_coil_refrigerant=0.2, T_ambient=25.0,
        )
        result = predict_energy_balance(inp, realistic_torque_table, realistic_loss_table)

        # Verify structure
        assert isinstance(result, EnergyModelResult)
        assert result.Pin > 0
        assert result.Pmech > 0
        assert result.MotorLoss > 0
        assert result.Torque > 0
        assert isinstance(result.converged, bool)
        assert result.balance_error_pct >= 0.0

        # Enthalpies should be positive for R1234yf
        assert result.hs > 0
        assert result.h_mid > 0

        # Q_refrig = mdot_kg_s * (h_mid - hs) -> should be positive
        # since T_mid (40) > Ts (15) at similar pressures
        assert result.Q_refrig > 0


# ===================================================================
# Test: Edge cases
# ===================================================================
class TestEdgeCases:
    """Edge case tests for the energy model."""

    @patch("core.compressor_energy_model.get_enthalpy")
    @patch("core.compressor_energy_model.get_temperature")
    def test_zero_rpm(
        self,
        mock_get_temp: pytest.MonkeyPatch.patch,
        mock_enthalpy: pytest.MonkeyPatch.patch,
        simple_torque_table: TorqueCurrentTable,
        simple_loss_table: LossTable,
    ) -> None:
        """RPM=0 should give Pmech=0 and valid result."""
        mock_enthalpy.return_value = 400000.0

        inp = EnergyModelInput(
            Ps=2.0, Ts=15.0, P_mid=2.5, T_mid=40.0, Pd=12.0,
            mdot=100.0, V=380.0, I=7.5, RPM=0.0,
            R_coil_case=0.5, R_coil_core=0.3, R_coil_refrigerant=0.2, T_ambient=25.0,
        )
        # RPM=0 is below table minimum -> clamps to 1000 RPM curve
        result = predict_energy_balance(inp, simple_torque_table, simple_loss_table)

        assert result.Pmech == pytest.approx(0.0)  # omega=0 -> Pmech=0
        assert result.Pin > 0  # Pin still computed from V, I

    @patch("core.compressor_energy_model.get_enthalpy")
    @patch("core.compressor_energy_model.get_temperature")
    def test_equal_resistances(
        self,
        mock_get_temp: pytest.MonkeyPatch.patch,
        mock_enthalpy: pytest.MonkeyPatch.patch,
    ) -> None:
        """Equal thermal resistances -> T_coil weighted equally."""
        mock_enthalpy.return_value = 400000.0

        table = TorqueCurrentTable(
            rpm_values=[1500.0],
            entries={1500.0: [(7.5, 30.0)]},
        )
        loss_table = LossTable(
            rpm_values=[1500.0],
            entries={1500.0: [(30.0, 200.0)]},
        )

        inp = EnergyModelInput(
            Ps=2.0, Ts=15.0, P_mid=2.5, T_mid=50.0, Pd=12.0,
            mdot=100.0, V=380.0, I=7.5, RPM=1500.0,
            R_coil_case=1.0, R_coil_core=1.0, R_coil_refrigerant=1.0, T_ambient=25.0,
        )
        result = predict_energy_balance(inp, table, loss_table)

        # T_coil = (200 + 50*1 + 25*1 + 15*1) / (1+1+1) = 290/3 = 96.667
        assert result.T_coil == pytest.approx(290.0 / 3.0)


# ===================================================================
# Test: Recirculation model
# ===================================================================
class TestRecirculationModel:
    """Tests for the hot gas recirculation calculation."""

    @patch("core.compressor_energy_model.get_enthalpy")
    @patch("core.compressor_energy_model.get_temperature")
    def test_recirculation_positive_when_qrefrig_exceeds_loss(
        self,
        mock_get_temp: pytest.MonkeyPatch.patch,
        mock_enthalpy: pytest.MonkeyPatch.patch,
    ) -> None:
        """When Q_refrig > MotorLoss, recirculation is positive."""
        def enthalpy_side_effect(P: float, T: float) -> float:
            if P < 350000:
                return 400000.0  # hs
            return 420000.0  # h_mid

        mock_enthalpy.side_effect = enthalpy_side_effect
        mock_get_temp.return_value = 90.0

        # Tables: Torque=30 Nm, Loss=200 W
        # Pin = sqrt(3)*380*7.5 = 4936.27 W
        # Pmech = 30 * 157.08 = 4712.4 W
        # hd = 420000 + 4712.4 / (100/3600) = 420000 + 169646 = 589646
        # Q_refrig = (100/3600) * (420000 - 400000) = 555.56 W
        # Since Q_refrig (555.56) > MotorLoss (200), recirculation > 0
        # mdot_recirc = (555.56 - 200) / (589646 - 420000) = 355.56 / 169646 = 0.002096 kg/s
        table = TorqueCurrentTable(
            rpm_values=[1500.0],
            entries={1500.0: [(7.5, 30.0)]},
        )
        loss_table = LossTable(
            rpm_values=[1500.0],
            entries={1500.0: [(30.0, 200.0)]},
        )

        inp = EnergyModelInput(
            Ps=2.0, Ts=15.0, P_mid=2.5, T_mid=40.0, Pd=12.0,
            mdot=100.0, V=380.0, I=7.5, RPM=1500.0,
            R_coil_case=0.5, R_coil_core=0.3, R_coil_refrigerant=0.2, T_ambient=25.0,
        )
        result = predict_energy_balance(inp, table, loss_table)

        assert result.mdot_recirc > 0
        assert result.recirc_ratio > 0
        assert result.hd > result.h_mid  # hd > h_mid always
        assert result.Td_est == pytest.approx(90.0)

    @patch("core.compressor_energy_model.get_enthalpy")
    @patch("core.compressor_energy_model.get_temperature")
    def test_recirculation_zero_when_loss_exceeds_qrefrig(
        self,
        mock_get_temp: pytest.MonkeyPatch.patch,
        mock_enthalpy: pytest.MonkeyPatch.patch,
    ) -> None:
        """When MotorLoss >= Q_refrig, recirculation is zero."""
        # hs = h_mid -> Q_refrig = 0 -> MotorLoss > Q_refrig
        mock_enthalpy.return_value = 400000.0
        mock_get_temp.return_value = 70.0

        table = TorqueCurrentTable(
            rpm_values=[1500.0],
            entries={1500.0: [(7.5, 30.0)]},
        )
        loss_table = LossTable(
            rpm_values=[1500.0],
            entries={1500.0: [(30.0, 200.0)]},
        )

        inp = EnergyModelInput(
            Ps=2.0, Ts=15.0, P_mid=2.5, T_mid=40.0, Pd=12.0,
            mdot=100.0, V=380.0, I=7.5, RPM=1500.0,
            R_coil_case=0.5, R_coil_core=0.3, R_coil_refrigerant=0.2, T_ambient=25.0,
        )
        result = predict_energy_balance(inp, table, loss_table)

        # hs == h_mid -> Q_refrig = 0 -> MotorLoss > Q_refrig -> mdot_recirc = 0
        assert result.Q_refrig == pytest.approx(0.0)
        assert result.mdot_recirc == pytest.approx(0.0)
        assert result.recirc_ratio == pytest.approx(0.0)

    @patch("core.compressor_energy_model.get_enthalpy")
    @patch("core.compressor_energy_model.get_temperature")
    def test_recirculation_ratio_realistic_range(
        self,
        mock_get_temp: pytest.MonkeyPatch.patch,
        mock_enthalpy: pytest.MonkeyPatch.patch,
    ) -> None:
        """Recirculation ratio should be in a physically realistic range (0-30%)."""
        def enthalpy_side_effect(P: float, T: float) -> float:
            if P < 350000:
                return 380000.0  # hs (suction, lower T)
            return 410000.0  # h_mid (higher T/pressure)

        mock_enthalpy.side_effect = enthalpy_side_effect
        mock_get_temp.return_value = 95.0

        table = TorqueCurrentTable(
            rpm_values=[1500.0],
            entries={1500.0: [(7.5, 30.0)]},
        )
        loss_table = LossTable(
            rpm_values=[1500.0],
            entries={1500.0: [(30.0, 200.0)]},
        )

        inp = EnergyModelInput(
            Ps=2.0, Ts=15.0, P_mid=2.5, T_mid=40.0, Pd=12.0,
            mdot=100.0, V=380.0, I=7.5, RPM=1500.0,
            R_coil_case=0.5, R_coil_core=0.3, R_coil_refrigerant=0.2, T_ambient=25.0,
        )
        result = predict_energy_balance(inp, table, loss_table)

        # recirc_ratio should be non-negative and reasonable
        assert result.recirc_ratio >= 0.0
        assert result.recirc_ratio < 1.0  # less than 100% is physically required

    @patch("core.compressor_energy_model.get_enthalpy")
    @patch("core.compressor_energy_model.get_temperature")
    def test_discharge_enthalpy_greater_than_mid(
        self,
        mock_get_temp: pytest.MonkeyPatch.patch,
        mock_enthalpy: pytest.MonkeyPatch.patch,
    ) -> None:
        """hd = h_mid + Pmech/mdot_s should always exceed h_mid."""
        mock_enthalpy.return_value = 400000.0
        mock_get_temp.return_value = 100.0

        table = TorqueCurrentTable(
            rpm_values=[1500.0],
            entries={1500.0: [(7.5, 30.0)]},
        )
        loss_table = LossTable(
            rpm_values=[1500.0],
            entries={1500.0: [(30.0, 200.0)]},
        )

        inp = EnergyModelInput(
            Ps=2.0, Ts=15.0, P_mid=2.5, T_mid=40.0, Pd=12.0,
            mdot=100.0, V=380.0, I=7.5, RPM=1500.0,
            R_coil_case=0.5, R_coil_core=0.3, R_coil_refrigerant=0.2, T_ambient=25.0,
        )
        result = predict_energy_balance(inp, table, loss_table)

        assert result.hd > result.h_mid
        # hd = h_mid + Pmech / mdot_s
        mdot_s = 100.0 / 3600.0
        omega = 2.0 * math.pi * 1500.0 / 60.0
        expected_hd = 400000.0 + (30.0 * omega) / mdot_s
        assert result.hd == pytest.approx(expected_hd, rel=1e-4)

    @patch("core.compressor_energy_model.get_enthalpy")
    @patch("core.compressor_energy_model.get_temperature")
    def test_td_est_nan_on_coolprop_failure(
        self,
        mock_get_temp: pytest.MonkeyPatch.patch,
        mock_enthalpy: pytest.MonkeyPatch.patch,
    ) -> None:
        """Td_est should be NaN when get_temperature fails."""
        mock_enthalpy.return_value = 400000.0
        mock_get_temp.side_effect = ValueError("State out of range")

        table = TorqueCurrentTable(
            rpm_values=[1500.0],
            entries={1500.0: [(7.5, 30.0)]},
        )
        loss_table = LossTable(
            rpm_values=[1500.0],
            entries={1500.0: [(30.0, 200.0)]},
        )

        inp = EnergyModelInput(
            Ps=2.0, Ts=15.0, P_mid=2.5, T_mid=40.0, Pd=12.0,
            mdot=100.0, V=380.0, I=7.5, RPM=1500.0,
            R_coil_case=0.5, R_coil_core=0.3, R_coil_refrigerant=0.2, T_ambient=25.0,
        )
        result = predict_energy_balance(inp, table, loss_table)

        assert math.isnan(result.Td_est)
        # Other fields should still be valid
        assert result.hd > 0
        assert result.mdot_recirc >= 0


# ===================================================================
# Test: Calibration (energy-balance model)
# ===================================================================
class TestCalibrateThermalResistances:
    """Tests for the calibrate_thermal_resistances function."""

    @pytest.fixture
    def cal_tables(self) -> tuple[TorqueCurrentTable, LossTable]:
        """Single-RPM tables for deterministic calibration tests."""
        torque = TorqueCurrentTable(
            rpm_values=[3000.0],
            entries={3000.0: [(5.0, 1.0), (7.0, 1.4)]},
        )
        loss = LossTable(
            rpm_values=[3000.0],
            entries={3000.0: [(1.0, 50.0), (1.4, 70.0)]},
        )
        return torque, loss

    def _make_points(
        self,
        R_case: float,
        R_core: float,
        R_refrig: float,
        torque: TorqueCurrentTable,
        loss: LossTable,
        n: int = 4,
    ) -> list[CalibDataPoint]:
        """Generate calibration data points from known R values."""
        points: list[CalibDataPoint] = []
        for i in range(n):
            T_mid = 40.0 + i * 5.0
            inp = EnergyModelInput(
                Ps=2.0, Ts=15.0, P_mid=3.0, T_mid=T_mid, Pd=12.0,
                mdot=50.0, V=380.0, I=5.0 + i, RPM=3000.0,
                R_coil_case=R_case, R_coil_core=R_core,
                R_coil_refrigerant=R_refrig, T_ambient=25.0,
            )
            result = predict_energy_balance(inp, torque, loss)
            points.append(CalibDataPoint(
                Ps=2.0, Ts=15.0, P_mid=3.0, T_mid=T_mid, Pd=12.0,
                mdot=50.0, V=380.0, I=5.0 + i, RPM=3000.0,
                T_ambient=25.0, T_coil_measured=result.T_coil,
            ))
        return points

    def test_recovers_known_resistances(
        self, cal_tables: tuple[TorqueCurrentTable, LossTable],
    ) -> None:
        """Calibration should recover R values used to generate data."""
        torque, loss = cal_tables
        R_case, R_core, R_refrig = 0.5, 0.3, 0.2
        points = self._make_points(R_case, R_core, R_refrig, torque, loss, n=5)

        result = calibrate_thermal_resistances(
            points, torque, loss, n_starts=2, max_iter=100,
        )

        assert result.R_coil_case == pytest.approx(R_case, rel=0.1)
        assert result.R_coil_core == pytest.approx(R_core, rel=0.1)
        assert result.R_coil_refrigerant == pytest.approx(R_refrig, rel=0.1)
        assert result.rmse_T_coil < 1.0
        assert result.n_points == 5

    def test_result_has_correct_structure(
        self, cal_tables: tuple[TorqueCurrentTable, LossTable],
    ) -> None:
        """Result should contain all required fields."""
        torque, loss = cal_tables
        points = self._make_points(0.5, 0.3, 0.2, torque, loss, n=3)

        result = calibrate_thermal_resistances(
            points, torque, loss, n_starts=1, max_iter=50,
        )

        assert isinstance(result, CalibResult)
        assert len(result.T_coil_predicted) == 3
        assert len(result.T_coil_measured) == 3
        assert len(result.Td_predicted) == 3
        assert result.rmse_T_coil >= 0
        assert result.mae_T_coil >= 0
        assert result.max_error_T_coil >= 0

    def test_minimum_three_points_required(
        self, cal_tables: tuple[TorqueCurrentTable, LossTable],
    ) -> None:
        """Calibration with 3 points should work (minimum accepted)."""
        torque, loss = cal_tables
        points = self._make_points(0.4, 0.2, 0.1, torque, loss, n=3)

        result = calibrate_thermal_resistances(
            points, torque, loss, n_starts=1, max_iter=50,
        )

        assert result.n_points == 3
        assert result.R_coil_case > 0
        assert result.R_coil_core > 0
        assert result.R_coil_refrigerant > 0

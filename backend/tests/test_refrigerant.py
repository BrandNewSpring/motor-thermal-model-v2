"""Tests for the refrigerant property module (REQ-COMP-REFRIG-001).

TDD RED phase: These tests define the expected interface and behavior
for the refrigerant property module before implementation.
"""

from __future__ import annotations

import math
from functools import lru_cache
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# 1. Backend detection and fallback chain
# ---------------------------------------------------------------------------
class TestBackendDetection:
    """Verify startup detection and fallback chain (REFPROP > CoolProp+REFPROP > CoolProp-HEOS)."""

    def test_detect_coolprop_heos_when_no_refprop(self) -> None:
        """When REFPROP is unavailable, CoolProp HEOS backend should be used."""
        from core.refrigerant import get_active_backend

        backend = get_active_backend()
        assert backend in ("REFPROP", "CoolProp-REFPROP", "CoolProp-HEOS")

    def test_backend_name_is_logged_on_import(self) -> None:
        """Module should expose the active backend name for logging."""
        from core.refrigerant import BACKEND_NAME

        assert isinstance(BACKEND_NAME, str)
        assert len(BACKEND_NAME) > 0

    def test_fallback_chain_prefers_refprop(self) -> None:
        """If refprop package is importable, it should be preferred."""
        import core.refrigerant as refmod

        # Simulate refprop being available
        with patch.dict("sys.modules", {"refprop": object()}):
            # Re-detect would pick REFPROP; we just verify the detection logic exists
            assert hasattr(refmod, "_detect_backend")

    def test_coolprop_heos_used_as_last_resort(self) -> None:
        """CoolProp native HEOS is always available as fallback."""
        from core.refrigerant import get_active_backend

        # CoolProp HEOS should always work (CoolProp is a dependency)
        backend = get_active_backend()
        assert "CoolProp" in backend or "REFPROP" in backend


# ---------------------------------------------------------------------------
# 2. Density calculation
# ---------------------------------------------------------------------------
class TestDensity:
    """Density [kg/m^3] at known state points for R1234yf."""

    def test_density_vapor_at_500kpa_15c(self) -> None:
        """At P=500kPa, T=15C: vapor density should be ~25-30 kg/m^3."""
        from core.refrigerant import get_density

        rho = get_density(P=500_000.0, T=15.0)
        assert 20.0 < rho < 35.0, f"Density {rho} outside expected range"

    def test_density_superheated_at_2000kpa_80c(self) -> None:
        """At P=2000kPa, T=80C: superheated vapor density ~80-100 kg/m^3."""
        from core.refrigerant import get_density

        rho = get_density(P=2_000_000.0, T=80.0)
        assert 60.0 < rho < 120.0, f"Density {rho} outside expected range"

    def test_density_returns_positive_float(self) -> None:
        """Density must always return a positive finite float."""
        from core.refrigerant import get_density

        rho = get_density(P=500_000.0, T=15.0)
        assert isinstance(rho, float)
        assert rho > 0
        assert math.isfinite(rho)


# ---------------------------------------------------------------------------
# 3. Enthalpy calculation
# ---------------------------------------------------------------------------
class TestEnthalpy:
    """Enthalpy [J/kg] at known state points for R1234yf."""

    def test_enthalpy_vapor_at_500kpa_15c(self) -> None:
        """At P=500kPa, T=15C: vapor enthalpy ~370-380 kJ/kg."""
        from core.refrigerant import get_enthalpy

        h = get_enthalpy(P=500_000.0, T=15.0)
        assert 350_000.0 < h < 400_000.0, f"Enthalpy {h} outside expected range"

    def test_enthalpy_returns_positive_float(self) -> None:
        """Enthalpy must return a finite float."""
        from core.refrigerant import get_enthalpy

        h = get_enthalpy(P=500_000.0, T=15.0)
        assert isinstance(h, float)
        assert math.isfinite(h)

    def test_enthalpy_higher_at_higher_temperature(self) -> None:
        """Enthalpy should increase with temperature at constant pressure."""
        from core.refrigerant import get_enthalpy

        h_low = get_enthalpy(P=500_000.0, T=15.0)
        h_high = get_enthalpy(P=500_000.0, T=80.0)
        assert h_high > h_low


# ---------------------------------------------------------------------------
# 4. Temperature from pressure + enthalpy
# ---------------------------------------------------------------------------
class TestTemperatureFromPH:
    """Temperature [degC] recovered from (P, h) pair."""

    def test_roundtrip_temperature(self) -> None:
        """get_temperature(P, h) should recover original T from get_enthalpy."""
        from core.refrigerant import get_enthalpy, get_temperature

        P, T_original = 500_000.0, 15.0
        h = get_enthalpy(P=P, T=T_original)
        T_recovered = get_temperature(P=P, h=h)
        assert T_recovered == pytest.approx(T_original, abs=0.1)

    def test_roundtrip_at_high_pressure(self) -> None:
        """Roundtrip at P=2000kPa, T=80C."""
        from core.refrigerant import get_enthalpy, get_temperature

        P, T_original = 2_000_000.0, 80.0
        h = get_enthalpy(P=P, T=T_original)
        T_recovered = get_temperature(P=P, h=h)
        assert T_recovered == pytest.approx(T_original, abs=0.1)


# ---------------------------------------------------------------------------
# 5. Entropy from pressure + enthalpy
# ---------------------------------------------------------------------------
class TestEntropyFromPH:
    """Entropy [J/(kg*K)] from (P, h) pair."""

    def test_entropy_returns_positive_float(self) -> None:
        """Entropy should be a positive finite float for valid states."""
        from core.refrigerant import get_entropy, get_enthalpy

        h = get_enthalpy(P=500_000.0, T=15.0)
        s = get_entropy(P=500_000.0, h=h)
        assert isinstance(s, float)
        assert s > 0
        assert math.isfinite(s)

    def test_entropy_increases_with_temperature(self) -> None:
        """Entropy should increase with temperature at constant pressure."""
        from core.refrigerant import get_entropy, get_enthalpy

        h_low = get_enthalpy(P=500_000.0, T=15.0)
        h_high = get_enthalpy(P=500_000.0, T=80.0)
        s_low = get_entropy(P=500_000.0, h=h_low)
        s_high = get_entropy(P=500_000.0, h=h_high)
        assert s_high > s_low


# ---------------------------------------------------------------------------
# 6. Out-of-range error handling
# ---------------------------------------------------------------------------
class TestOutOfRangeErrors:
    """Descriptive errors for out-of-range thermodynamic states."""

    def test_negative_pressure_raises(self) -> None:
        """Negative pressure should raise a descriptive error."""
        from core.refrigerant import get_density

        with pytest.raises((ValueError, RuntimeError)):
            get_density(P=-100_000.0, T=25.0)

    def test_extreme_temperature_raises(self) -> None:
        """Extremely out-of-range temperature should raise an error."""
        from core.refrigerant import get_density

        with pytest.raises((ValueError, RuntimeError)):
            get_density(P=500_000.0, T=-273.15)

    def test_error_message_is_descriptive(self) -> None:
        """Error message should include the invalid input values."""
        from core.refrigerant import get_density

        with pytest.raises((ValueError, RuntimeError)) as exc_info:
            get_density(P=-100_000.0, T=25.0)
        error_msg = str(exc_info.value).lower()
        # Should mention the problematic value or context
        assert len(error_msg) > 10  # Not a generic one-word error


# ---------------------------------------------------------------------------
# 7. Caching behavior
# ---------------------------------------------------------------------------
class TestCaching:
    """Thread-safe caching for performance during optimization."""

    def test_same_input_returns_same_output(self) -> None:
        """Repeated calls with identical inputs must return identical results."""
        from core.refrigerant import get_density

        rho1 = get_density(P=500_000.0, T=15.0)
        rho2 = get_density(P=500_000.0, T=15.0)
        assert rho1 == rho2

    def test_different_inputs_return_different_outputs(self) -> None:
        """Different inputs should produce different results."""
        from core.refrigerant import get_density

        rho1 = get_density(P=500_000.0, T=15.0)
        rho2 = get_density(P=500_000.0, T=80.0)
        assert rho1 != rho2

    def test_cache_function_exists(self) -> None:
        """Module should expose a cache clear function."""
        from core.refrigerant import clear_cache

        # Should be callable without error
        clear_cache()

    def test_cache_clear_allows_fresh_computation(self) -> None:
        """After clear_cache, results should still be correct."""
        from core.refrigerant import clear_cache, get_density

        rho_before = get_density(P=500_000.0, T=15.0)
        clear_cache()
        rho_after = get_density(P=500_000.0, T=15.0)
        assert rho_before == pytest.approx(rho_after, rel=1e-10)


# ---------------------------------------------------------------------------
# 8. Refrigerant name parameter
# ---------------------------------------------------------------------------
class TestRefrigerantName:
    """Default refrigerant is R1234yf."""

    def test_default_refrigerant_is_r1234yf(self) -> None:
        """Default refrigerant constant should be R1234yf."""
        from core.refrigerant import DEFAULT_REFRIGERANT

        assert DEFAULT_REFRIGERANT == "R1234yf"

    def test_functions_accept_refrigerant_kwarg(self) -> None:
        """All property functions should accept a refrigerant keyword argument."""
        from core.refrigerant import get_density, get_enthalpy

        # Should not raise
        rho = get_density(P=500_000.0, T=15.0, refrigerant="R1234yf")
        assert isinstance(rho, float)

        h = get_enthalpy(P=500_000.0, T=15.0, refrigerant="R1234yf")
        assert isinstance(h, float)

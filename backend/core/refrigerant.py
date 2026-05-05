"""Refrigerant property module for R1234yf (REQ-COMP-REFRIG-001).

Provides a uniform interface for refrigerant thermodynamic property
calculations with automatic backend detection and graceful fallback:

  1. REFPROP (NIST REFPROP 10.0+) via ``refprop`` Python package
  2. CoolProp with REFPROP backend
  3. CoolProp native HEOS backend (always available)

All functions accept pressures in Pa and temperatures in degC.
Enthalpy is returned in J/kg, entropy in J/(kg*K), density in kg/m^3.

Reference: SPEC-COMP-THERMAL-001 REQ-COMP-REFRIG-001
"""

from __future__ import annotations

import logging
import threading
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_REFRIGERANT: str = "R1234yf"

# CoolProp refrigerant name mapping
_COOLPROP_NAMES: dict[str, str] = {
    "R1234yf": "R1234yf",
}

# CoolProp REFPROP-name mapping (used with REFPROP backend)
_REFPROP_NAMES: dict[str, str] = {
    "R1234yf": "R1234YF",
}


# ---------------------------------------------------------------------------
# Backend detection (runs once at import time)
# ---------------------------------------------------------------------------
def _detect_backend() -> str:
    """Detect the best available thermodynamic backend.

    Priority: REFPROP > CoolProp+REFPROP > CoolProp-HEOS.

    Returns
    -------
    str
        One of "REFPROP", "CoolProp-REFPROP", "CoolProp-HEOS".
    """
    # Try REFPROP native package
    try:
        import refprop  # noqa: F401
        logger.info("REFPROP backend detected (native refprop package)")
        return "REFPROP"
    except ImportError:
        pass

    # Try CoolProp with REFPROP backend
    try:
        import CoolProp.CoolProp as CP
        refprop_name = _REFPROP_NAMES.get(DEFAULT_REFRIGERANT, DEFAULT_REFRIGERANT)
        CP.PropsSI("D", "P", 500000, "T", 288.15, f"REFPROP::{refprop_name}")
        logger.info("CoolProp REFPROP backend detected")
        return "CoolProp-REFPROP"
    except Exception:
        pass

    # Fallback: CoolProp HEOS
    try:
        import CoolProp.CoolProp as CP
        cp_name = _COOLPROP_NAMES.get(DEFAULT_REFRIGERANT, DEFAULT_REFRIGERANT)
        CP.PropsSI("D", "P", 500000, "T", 288.15, cp_name)
        logger.info("CoolProp HEOS backend detected (fallback)")
        return "CoolProp-HEOS"
    except Exception as exc:
        raise RuntimeError(
            f"No thermodynamic backend available. Install CoolProp. Error: {exc}"
        ) from exc


# Module-level backend name (computed once)
BACKEND_NAME: str = _detect_backend()


# ---------------------------------------------------------------------------
# Thread-safe LRU cache
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()
_property_cache: dict[tuple, float] = {}


def _cached_query(key: tuple) -> Optional[float]:
    """Thread-safe cache lookup."""
    with _cache_lock:
        return _property_cache.get(key)


def _cached_store(key: tuple, value: float) -> None:
    """Thread-safe cache store."""
    with _cache_lock:
        _property_cache[key] = value


def clear_cache() -> None:
    """Clear the property cache. Useful between optimization runs."""
    with _cache_lock:
        _property_cache.clear()


# ---------------------------------------------------------------------------
# Internal CoolProp query
# ---------------------------------------------------------------------------
def _coolprop_query(
    output: str,
    P: float,
    T: Optional[float] = None,
    h: Optional[float] = None,
    refrigerant: str = DEFAULT_REFRIGERANT,
) -> float:
    """Execute a CoolProp query with appropriate backend.

    Parameters
    ----------
    output : str
        CoolProp output key (e.g. "D", "H", "S", "T").
    P : float
        Pressure [Pa].
    T : float | None
        Temperature [degC]. Converted to K internally.
    h : float | None
        Enthalpy [J/kg].
    refrigerant : str
        Refrigerant identifier.

    Returns
    -------
    float
        Requested property value.
    """
    import CoolProp.CoolProp as CP

    cp_name = _COOLPROP_NAMES.get(refrigerant, refrigerant)
    refprop_name = _REFPROP_NAMES.get(refrigerant, refrigerant)

    # Build input pair
    if T is not None:
        T_K = T + 273.15
        input_pair = (output, "P", P, "T", T_K)
    elif h is not None:
        input_pair = (output, "P", P, "H", h)
    else:
        raise ValueError("Either T or h must be provided")

    # Try with detected backend
    errors = []
    for backend_name, fluid_name in [
        ("CoolProp-REFPROP", f"REFPROP::{refprop_name}"),
        ("CoolProp-HEOS", cp_name),
    ]:
        # Skip backends that don't match our detected one
        if backend_name != BACKEND_NAME and BACKEND_NAME != "REFPROP":
            # Only use detected backend; if it's REFPROP we don't use CoolProp
            if BACKEND_NAME == "REFPROP":
                continue
            # If detected backend matches, try only that one
            if BACKEND_NAME != backend_name and BACKEND_NAME in (
                "CoolProp-REFPROP",
                "CoolProp-HEOS",
            ):
                continue

        try:
            result = CP.PropsSI(input_pair[0], input_pair[1], input_pair[2],
                                input_pair[3], input_pair[4], fluid_name)
            return float(result)
        except Exception as exc:
            errors.append(f"{backend_name}({fluid_name}): {exc}")
            continue

    # Fallback: try all backends regardless of detection
    for backend_name, fluid_name in [
        ("CoolProp-REFPROP", f"REFPROP::{refprop_name}"),
        ("CoolProp-HEOS", cp_name),
    ]:
        try:
            result = CP.PropsSI(input_pair[0], input_pair[1], input_pair[2],
                                input_pair[3], input_pair[4], fluid_name)
            return float(result)
        except Exception:
            continue

    error_detail = "; ".join(errors) if errors else "All backends failed"
    raise ValueError(
        f"Failed to compute {output} for {refrigerant} at P={P} Pa, "
        f"T={T}, h={h}: {error_detail}"
    )


def _query_property(
    prop_name: str,
    P: float,
    T: Optional[float] = None,
    h: Optional[float] = None,
    refrigerant: str = DEFAULT_REFRIGERANT,
) -> float:
    """Query a refrigerant property with caching.

    Parameters
    ----------
    prop_name : str
        Property identifier (D, H, S, T).
    P : float
        Pressure [Pa].
    T : float | None
        Temperature [degC].
    h : float | None
        Enthalpy [J/kg].
    refrigerant : str
        Refrigerant name.

    Returns
    -------
    float
        Property value.
    """
    cache_key = (prop_name, P, T, h, refrigerant)

    cached = _cached_query(cache_key)
    if cached is not None:
        return cached

    value = _coolprop_query(prop_name, P, T=T, h=h, refrigerant=refrigerant)

    _cached_store(cache_key, value)
    return value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_active_backend() -> str:
    """Return the name of the currently active thermodynamic backend.

    Returns
    -------
    str
        One of "REFPROP", "CoolProp-REFPROP", "CoolProp-HEOS".
    """
    return BACKEND_NAME


def get_density(P: float, T: float, refrigerant: str = DEFAULT_REFRIGERANT) -> float:
    """Compute refrigerant density at given pressure and temperature.

    Parameters
    ----------
    P : float
        Pressure [Pa].
    T : float
        Temperature [degC].
    refrigerant : str
        Refrigerant identifier. Default "R1234yf".

    Returns
    -------
    float
        Density [kg/m^3].

    Raises
    ------
    ValueError
        If the thermodynamic state is out of range.
    """
    if P <= 0:
        raise ValueError(
            f"Pressure must be positive, got P={P} Pa. "
            "Provide a valid positive pressure value."
        )
    if T < -273.15:
        raise ValueError(
            f"Temperature {T} degC is below absolute zero. "
            "Provide a physically valid temperature."
        )
    return _query_property("D", P=P, T=T, refrigerant=refrigerant)


def get_enthalpy(P: float, T: float, refrigerant: str = DEFAULT_REFRIGERANT) -> float:
    """Compute refrigerant specific enthalpy at given pressure and temperature.

    Parameters
    ----------
    P : float
        Pressure [Pa].
    T : float
        Temperature [degC].
    refrigerant : str
        Refrigerant identifier. Default "R1234yf".

    Returns
    -------
    float
        Specific enthalpy [J/kg].

    Raises
    ------
    ValueError
        If the thermodynamic state is out of range.
    """
    if P <= 0:
        raise ValueError(
            f"Pressure must be positive, got P={P} Pa. "
            "Provide a valid positive pressure value."
        )
    if T < -273.15:
        raise ValueError(
            f"Temperature {T} degC is below absolute zero. "
            "Provide a physically valid temperature."
        )
    return _query_property("H", P=P, T=T, refrigerant=refrigerant)


def get_temperature(P: float, h: float, refrigerant: str = DEFAULT_REFRIGERANT) -> float:
    """Compute temperature from pressure and specific enthalpy.

    Parameters
    ----------
    P : float
        Pressure [Pa].
    h : float
        Specific enthalpy [J/kg].
    refrigerant : str
        Refrigerant identifier. Default "R1234yf".

    Returns
    -------
    float
        Temperature [degC].

    Raises
    ------
    ValueError
        If the thermodynamic state is out of range.
    """
    if P <= 0:
        raise ValueError(
            f"Pressure must be positive, got P={P} Pa. "
            "Provide a valid positive pressure value."
        )
    T_K = _query_property("T", P=P, h=h, refrigerant=refrigerant)
    return T_K - 273.15  # Convert K to degC


def get_entropy(P: float, h: float, refrigerant: str = DEFAULT_REFRIGERANT) -> float:
    """Compute specific entropy from pressure and enthalpy.

    Parameters
    ----------
    P : float
        Pressure [Pa].
    h : float
        Specific enthalpy [J/kg].
    refrigerant : str
        Refrigerant identifier. Default "R1234yf".

    Returns
    -------
    float
        Specific entropy [J/(kg*K)].

    Raises
    ------
    ValueError
        If the thermodynamic state is out of range.
    """
    if P <= 0:
        raise ValueError(
            f"Pressure must be positive, got P={P} Pa. "
            "Provide a valid positive pressure value."
        )
    return _query_property("S", P=P, h=h, refrigerant=refrigerant)

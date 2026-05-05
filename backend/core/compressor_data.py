"""Compressor test data extraction pipeline (REQ-COMP-DATA-001).

Parses multi-sheet Excel (.xlsx/.xlsm) compressor test files, normalizes
units, validates columns, and returns structured per-sheet results with
data points.

Reference: SPEC-COMP-THERMAL-001
"""

from __future__ import annotations

import math
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = {"rpm", "ps", "ts", "pd", "td", "tm", "p_loss"}

OPTIONAL_COLUMNS = {
    "mass_flow", "hs", "pm", "hm", "hd",
    "p1", "p2", "comppower", "torque", "i_peak",
    "ironloss", "motorloss", "deltaml",
}

# Alias mapping: canonical lowercase name -> set of acceptable aliases
COLUMN_ALIASES: dict[str, set[str]] = {
    "rpm": {"rpm"},
    "ps": {"ps"},
    "ts": {"ts"},
    "pd": {"pd"},
    "td": {"td"},
    "tm": {"tm"},
    "p_loss": {"p_loss"},
    "mass_flow": {"mass_flow", "mass flow", "massflow"},
    "hs": {"hs"},
    "pm": {"pm"},
    "hm": {"hm"},
    "hd": {"hd"},
    "p1": {"p1"},
    "p2": {"p2"},
    "comppower": {"comppower", "comp_power", "comp power"},
    "torque": {"torque"},
    "i_peak": {"i_peak", "i peak", "ipeak"},
    "ironloss": {"ironloss", "iron_loss", "iron loss"},
    "motorloss": {"motorloss", "motor_loss", "motor loss", "motorloss(af)"},
    "deltaml": {"deltaml", "delta_ml", "delta ml"},
}

# Unit hint patterns found in column headers
# Maps regex pattern -> (conversion_function, applicable_canonical_names)
_UNIT_PATTERN_KPA = re.compile(r"\[kpa\]", re.IGNORECASE)
_UNIT_PATTERN_MPA = re.compile(r"\[mpa\]", re.IGNORECASE)
_UNIT_PATTERN_KELVIN = re.compile(r"\[k\]", re.IGNORECASE)
_UNIT_PATTERN_GS = re.compile(r"\[g/s\]", re.IGNORECASE)
_UNIT_PATTERN_KGH = re.compile(r"\[kg/h\]", re.IGNORECASE)
_UNIT_PATTERN_KW = re.compile(r"\[kw\]", re.IGNORECASE)

# Pressure columns (canonical lowercase)
_PRESSURE_COLS = {"ps", "pd", "pm"}
# Temperature columns
_TEMP_COLS = {"ts", "td", "tm"}
# Power columns
_POWER_COLS = {"p_loss", "p1", "p2", "comppower", "ironloss", "motorloss", "deltaml"}
# Mass flow columns
_MASSFLOW_COLS = {"mass_flow"}


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompressorDataPoint:
    """A single data point from compressor test data."""

    RPM: float
    mass_flow: float
    Ps: float
    Ts: float
    hs: float
    Pm: float
    Tm: float
    hm: float
    Pd: float
    Td: float
    hd: float
    P_loss: float
    P1: float
    P2: float
    CompPower: float
    Torque: float
    I_peak: float
    IronLoss: float
    MotorLoss: float
    deltaML: float


@dataclass
class ColumnValidationResult:
    """Result of validating sheet columns."""

    is_valid: bool
    missing_required: list[str]
    missing_optional: list[str]
    columns_found: list[str]
    column_mapping: dict[str, str]  # raw_name -> canonical_name


@dataclass
class SheetParseResult:
    """Result of parsing a single sheet."""

    sheet_name: str
    variant_name: str
    n_points: int
    columns_found: list[str]
    columns_missing: list[str]
    data: list[CompressorDataPoint]
    errors: list[str]


@dataclass
class CompressorParseResult:
    """Result of parsing an entire Excel file."""

    filename: str
    sheets: list[SheetParseResult]
    total_points: int
    valid_sheets: int
    invalid_sheets: int


# ---------------------------------------------------------------------------
# Column matching
# ---------------------------------------------------------------------------

def _normalize_col_name(raw: str) -> str:
    """Normalize a column name: strip whitespace, lowercase, remove parens content for matching."""
    s = raw.strip().lower()
    # Remove content in parentheses for matching purposes, e.g. "MotorLoss(AF)" -> "motorloss"
    s = re.sub(r"\(.*?\)", "", s)
    s = s.strip()
    return s


def _resolve_canonical_name(raw: str) -> Optional[str]:
    """Resolve a raw column name to its canonical name, or None if unrecognized."""
    normalized = _normalize_col_name(raw)

    # Also try the raw name lowercased without brackets
    no_brackets = re.sub(r"\[.*?\]", "", normalized).strip()

    for canonical, aliases in COLUMN_ALIASES.items():
        if normalized in aliases or no_brackets in aliases:
            return canonical

    return None


# ---------------------------------------------------------------------------
# Column validation
# ---------------------------------------------------------------------------

# @MX:ANCHOR: [AUTO] validate_sheet_columns is the primary entry point for column
# validation, called once per sheet during parsing.
# @MX:REASON: Column validation determines whether a sheet is parseable; incorrect
# logic here silently accepts or rejects data, affecting downstream analysis.
def validate_sheet_columns(columns: list[str]) -> ColumnValidationResult:
    """Validate that a sheet has required columns.

    Performs case-insensitive, whitespace-tolerant matching with alias support.

    Parameters
    ----------
    columns : list[str]
        Raw column names from the Excel sheet header.

    Returns
    -------
    ColumnValidationResult
        Validation result with missing required/optional columns and mapping.
    """
    column_mapping: dict[str, str] = {}
    found_canonical: set[str] = set()

    for raw_col in columns:
        canonical = _resolve_canonical_name(raw_col)
        if canonical is not None:
            column_mapping[raw_col] = canonical
            found_canonical.add(canonical)

    missing_required = sorted(
        col for col in REQUIRED_COLUMNS if col not in found_canonical
    )
    missing_optional = sorted(
        col for col in OPTIONAL_COLUMNS if col not in found_canonical
    )
    columns_found = sorted(found_canonical)
    is_valid = len(missing_required) == 0

    return ColumnValidationResult(
        is_valid=is_valid,
        missing_required=missing_required,
        missing_optional=missing_optional,
        columns_found=columns_found,
        column_mapping=column_mapping,
    )


# ---------------------------------------------------------------------------
# Unit normalization
# ---------------------------------------------------------------------------

def _detect_unit_hint(raw_col_name: str) -> dict[str, str]:
    """Detect unit hints from column name brackets.

    Returns dict mapping canonical_name -> unit_hint for columns with hints.
    """
    hints: dict[str, str] = {}
    canonical = _resolve_canonical_name(raw_col_name)
    if canonical is None:
        return hints

    raw_lower = raw_col_name.lower()

    if _UNIT_PATTERN_KPA.search(raw_lower):
        hints[canonical] = "kPa"
    elif _UNIT_PATTERN_MPA.search(raw_lower):
        hints[canonical] = "MPa"

    if _UNIT_PATTERN_KELVIN.search(raw_lower):
        hints[canonical] = "K"

    if _UNIT_PATTERN_GS.search(raw_lower):
        hints[canonical] = "g/s"
    elif _UNIT_PATTERN_KGH.search(raw_lower):
        hints[canonical] = "kg/h"

    if _UNIT_PATTERN_KW.search(raw_lower):
        hints[canonical] = "kW"

    return hints


def normalize_units(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize pressure to Pa, temperature to degC, mass flow to kg/s.

    Detects unit hints from column name brackets (e.g. ``Ps[kPa]``) and
    applies conversions in-place on a copy.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with raw column names that may contain unit hints.

    Returns
    -------
    pd.DataFrame
        DataFrame with normalized values. Column names are preserved.
    """
    df = df.copy()

    for raw_col in df.columns:
        hints = _detect_unit_hint(raw_col)
        if not hints:
            continue

        canonical = _resolve_canonical_name(raw_col)
        if canonical is None:
            continue

        unit = hints[canonical]

        if unit == "kPa" and canonical in _PRESSURE_COLS:
            df[raw_col] = df[raw_col] * 1000.0
        elif unit == "MPa" and canonical in _PRESSURE_COLS:
            df[raw_col] = df[raw_col] * 1e6
        elif unit == "K" and canonical in _TEMP_COLS:
            df[raw_col] = df[raw_col] - 273.15
        elif unit == "g/s" and canonical in _MASSFLOW_COLS:
            df[raw_col] = df[raw_col] / 1000.0
        elif unit == "kg/h" and canonical in _MASSFLOW_COLS:
            df[raw_col] = df[raw_col] / 3600.0
        elif unit == "kW" and canonical in _POWER_COLS:
            df[raw_col] = df[raw_col] * 1000.0

    return df


# ---------------------------------------------------------------------------
# Data point construction
# ---------------------------------------------------------------------------

def _make_data_point(row: pd.Series, col_map: dict[str, str]) -> Optional[CompressorDataPoint]:
    """Build a CompressorDataPoint from a DataFrame row.

    Returns None if a required field is non-numeric.
    """
    # Reverse map: canonical -> raw column name
    rev_map: dict[str, str] = {}
    for raw, canonical in col_map.items():
        rev_map[canonical] = raw

    def _get_float(canonical: str) -> float:
        """Get a float value for a canonical column name. Returns NaN if missing or non-numeric."""
        if canonical not in rev_map:
            return float("nan")
        raw_col = rev_map[canonical]
        val = row.get(raw_col)
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return float("nan")
        try:
            return float(val)
        except (ValueError, TypeError):
            return float("nan")

    # Check required fields first
    for req in REQUIRED_COLUMNS:
        v = _get_float(req)
        if math.isnan(v):
            return None  # Required field is non-numeric or missing

    return CompressorDataPoint(
        RPM=_get_float("rpm"),
        mass_flow=_get_float("mass_flow"),
        Ps=_get_float("ps"),
        Ts=_get_float("ts"),
        hs=_get_float("hs"),
        Pm=_get_float("pm"),
        Tm=_get_float("tm"),
        hm=_get_float("hm"),
        Pd=_get_float("pd"),
        Td=_get_float("td"),
        hd=_get_float("hd"),
        P_loss=_get_float("p_loss"),
        P1=_get_float("p1"),
        P2=_get_float("p2"),
        CompPower=_get_float("comppower"),
        Torque=_get_float("torque"),
        I_peak=_get_float("i_peak"),
        IronLoss=_get_float("ironloss"),
        MotorLoss=_get_float("motorloss"),
        deltaML=_get_float("deltaml"),
    )


def _is_empty_row(row: pd.Series) -> bool:
    """Check if a row is entirely empty or all-NaN."""
    return row.isna().all()


# ---------------------------------------------------------------------------
# Main parsing entry point
# ---------------------------------------------------------------------------

# @MX:ANCHOR: [AUTO] parse_compressor_excel is the main public API for the
# compressor data pipeline, called from the router layer.
# @MX:REASON: This function is the single entry point for all compressor Excel
# parsing; incorrect behavior here corrupts all downstream thermal analysis.
def parse_compressor_excel(file_path: str) -> CompressorParseResult:
    """Parse a multi-sheet compressor test Excel file.

    Opens the file, iterates all sheets, validates columns, normalizes units,
    and returns structured results. Invalid sheets are included with error
    messages but no data points.

    Parameters
    ----------
    file_path : str
        Path to the .xlsx/.xlsm file.

    Returns
    -------
    CompressorParseResult
        Aggregated results across all sheets.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    filename = path.name
    xls = pd.ExcelFile(str(path), engine="openpyxl")

    sheet_results: list[SheetParseResult] = []

    for sheet_name in xls.sheet_names:
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name)
        except Exception as exc:
            sheet_results.append(SheetParseResult(
                sheet_name=sheet_name,
                variant_name=sheet_name,
                n_points=0,
                columns_found=[],
                columns_missing=list(REQUIRED_COLUMNS),
                data=[],
                errors=[f"Failed to read sheet: {exc}"],
            ))
            continue

        # Handle completely empty sheet (no columns or no rows)
        if df.empty and len(df.columns) == 0:
            sheet_results.append(SheetParseResult(
                sheet_name=sheet_name,
                variant_name=sheet_name,
                n_points=0,
                columns_found=[],
                columns_missing=list(REQUIRED_COLUMNS),
                data=[],
                errors=["Sheet is empty (no columns)"],
            ))
            continue

        raw_columns = [str(c) for c in df.columns]
        validation = validate_sheet_columns(raw_columns)

        if not validation.is_valid:
            missing_str = ", ".join(validation.missing_required)
            sheet_results.append(SheetParseResult(
                sheet_name=sheet_name,
                variant_name=sheet_name,
                n_points=0,
                columns_found=validation.columns_found,
                columns_missing=validation.missing_required + validation.missing_optional,
                data=[],
                errors=[f"Missing required columns: {missing_str}"],
            ))
            continue

        # Normalize units
        df = normalize_units(df)

        # Parse data rows
        data_points: list[CompressorDataPoint] = []
        errors: list[str] = []
        rpm_seen: dict[float, int] = {}

        for idx, row in df.iterrows():
            if _is_empty_row(row):
                continue

            dp = _make_data_point(row, validation.column_mapping)
            if dp is None:
                errors.append(f"Row {idx + 2}: non-numeric value in required column")
                continue

            # Track RPM duplicates
            rpm_key = round(dp.RPM, 6)
            rpm_seen[rpm_key] = rpm_seen.get(rpm_key, 0) + 1
            data_points.append(dp)

        # Warn about duplicate RPMs
        dup_rpms = [rpm for rpm, count in rpm_seen.items() if count > 1]
        if dup_rpms:
            dup_str = ", ".join(f"{r:.1f}" for r in dup_rpms)
            errors.append(f"Warning: duplicate RPM values found: {dup_str}")

        # Compute missing columns (optional only, since required passed validation)
        found_canonical = set(validation.columns_found)
        missing_optional = sorted(
            col for col in OPTIONAL_COLUMNS if col not in found_canonical
        )

        # A sheet with valid columns but zero data rows is still invalid
        if len(data_points) == 0 and len(errors) == 0:
            errors.append("Sheet has valid columns but contains no data rows")

        sheet_results.append(SheetParseResult(
            sheet_name=sheet_name,
            variant_name=sheet_name,
            n_points=len(data_points),
            columns_found=validation.columns_found,
            columns_missing=missing_optional,
            data=data_points,
            errors=errors,
        ))

    total_points = sum(s.n_points for s in sheet_results)
    # A sheet is valid if it has at least one data point and no rejection errors
    _REJECTION_PATTERNS = ("Missing required", "no data rows", "no columns", "Failed to read")
    valid_sheets = sum(
        1 for s in sheet_results
        if s.n_points > 0
        and not any(any(p in e for p in _REJECTION_PATTERNS) for e in s.errors)
    )
    invalid_sheets = len(sheet_results) - valid_sheets

    return CompressorParseResult(
        filename=filename,
        sheets=sheet_results,
        total_points=total_points,
        valid_sheets=valid_sheets,
        invalid_sheets=invalid_sheets,
    )

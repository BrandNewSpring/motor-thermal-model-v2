"""File upload/parse router."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from schemas.data import (
    ColumnMappingRequest,
    ColumnMappingResponse,
    FileColumnsResponse,
    FileUploadResponse,
)

router = APIRouter()

UPLOADS_DIR = Path.home() / ".mtm_v2" / "uploads"

# In-memory file metadata store (file_id -> metadata dict)
_file_store: dict[str, dict] = {}


def _ensure_uploads_dir() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _detect_numeric_columns(df: pd.DataFrame) -> list[str]:
    """Return column names that contain numeric data."""
    return [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]


def _parse_file(filepath: Path) -> pd.DataFrame:
    """Parse CSV or Excel file into a DataFrame."""
    suffix = filepath.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(filepath)
    elif suffix in (".xlsx", ".xls"):
        return pd.read_excel(filepath)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    type: str = Form("test_data"),
) -> FileUploadResponse:
    """Upload a CSV or Excel file and return parsed metadata."""
    _ensure_uploads_dir()

    filename = file.filename or "unknown"
    suffix = Path(filename).suffix.lower()
    if suffix not in (".csv", ".xlsx", ".xls"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Supported: .csv, .xlsx, .xls",
        )

    file_id = str(uuid.uuid4())
    dest_path = UPLOADS_DIR / f"{file_id}_{filename}"

    # Write file to disk
    content = await file.read()
    dest_path.write_bytes(content)

    # Parse and analyze
    try:
        df = _parse_file(dest_path)
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {exc}") from exc

    numeric_cols = _detect_numeric_columns(df)
    preview = df.head(5).to_dict(orient="records")

    # Store metadata
    _file_store[file_id] = {
        "file_id": file_id,
        "filename": filename,
        "filepath": str(dest_path),
        "rows": len(df),
        "columns": list(df.columns),
        "numeric_columns": numeric_cols,
        "type": type,
    }

    return FileUploadResponse(
        file_id=file_id,
        filename=filename,
        rows=len(df),
        columns=list(df.columns),
        preview=preview,
    )


@router.get("/{file_id}/columns", response_model=FileColumnsResponse)
async def get_file_columns(file_id: str) -> FileColumnsResponse:
    """Return column list and sample data for an uploaded file."""
    meta = _file_store.get(file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    filepath = Path(meta["filepath"])
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File data not found on disk")

    try:
        df = _parse_file(filepath)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse file: {exc}") from exc

    return FileColumnsResponse(
        columns=list(df.columns),
        sample=df.head(5).to_dict(orient="records"),
    )


@router.post("/{file_id}/map-columns", response_model=ColumnMappingResponse)
async def map_columns(file_id: str, mapping: ColumnMappingRequest) -> ColumnMappingResponse:
    """Validate a column mapping against an uploaded file."""
    meta = _file_store.get(file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    filepath = Path(meta["filepath"])
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File data not found on disk")

    try:
        df = _parse_file(filepath)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse file: {exc}") from exc

    # Validate required columns exist
    required_fields = {
        "I_phase": mapping.I_phase,
        "T_amb": mapping.T_amb,
        "T_coil": mapping.T_coil,
    }
    for field_name, col_name in required_fields.items():
        if col_name not in df.columns:
            raise HTTPException(
                status_code=422,
                detail=f"Column '{col_name}' for field '{field_name}' not found in file",
            )

    # Check optional columns
    optional_fields = {
        "time": mapping.time,
        "rpm": mapping.rpm,
        "torque": mapping.torque,
    }
    for field_name, col_name in optional_fields.items():
        if col_name is not None and col_name not in df.columns:
            raise HTTPException(
                status_code=422,
                detail=f"Column '{col_name}' for field '{field_name}' not found in file",
            )

    # Build summary stats for mapped columns
    summary: dict = {}
    all_mapped = {**required_fields, **{k: v for k, v in optional_fields.items() if v is not None}}
    for field_name, col_name in all_mapped.items():
        col_data = pd.to_numeric(df[col_name], errors="coerce")
        summary[field_name] = {
            "min": float(col_data.min()) if not col_data.isna().all() else None,
            "max": float(col_data.max()) if not col_data.isna().all() else None,
            "mean": float(col_data.mean()) if not col_data.isna().all() else None,
            "non_null": int(col_data.notna().sum()),
        }

    # Count rows where all required columns have valid numeric data
    valid_mask = pd.Series(True, index=df.index)
    for col_name in required_fields.values():
        valid_mask &= pd.to_numeric(df[col_name], errors="coerce").notna()

    return ColumnMappingResponse(
        mapped_rows=int(valid_mask.sum()),
        summary=summary,
    )


@router.delete("/{file_id}")
async def delete_file(file_id: str) -> dict:
    """Delete an uploaded file and its metadata."""
    meta = _file_store.pop(file_id, None)
    if meta is not None:
        filepath = Path(meta["filepath"])
        filepath.unlink(missing_ok=True)
        return {"status": "deleted", "file_id": file_id}

    # Check disk even if not in memory store
    for fp in UPLOADS_DIR.glob(f"{file_id}_*"):
        fp.unlink()
        return {"status": "deleted", "file_id": file_id}

    raise HTTPException(status_code=404, detail=f"File {file_id} not found")

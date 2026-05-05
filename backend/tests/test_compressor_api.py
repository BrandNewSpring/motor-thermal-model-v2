"""API integration tests for the Compressor Thermal Model endpoints.

Tests cover:
  1. POST /api/compressor/upload — upload and parse multi-sheet Excel
  2. GET  /api/compressor/datasets — list uploaded datasets
  3. POST /api/compressor/predict — single-point prediction
  4. POST /api/compressor/predict — input validation (eta_s > 1)
  5. POST /api/compressor/predict — convergence check
  6. POST /api/compressor/calibrate — SSE calibration with synthetic data
  7. POST /api/compressor/upload — error handling for invalid files

Run with:
    cd backend && python -m pytest tests/test_compressor_api.py -v
"""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_compressor_excel(
    sheet_data: dict[str, dict[str, list[float]]] | None = None,
    filename: str = "test_compressor.xlsm",
) -> tuple[bytes, str]:
    """Create a synthetic compressor test Excel file in memory.

    Returns (file_bytes, filename).
    """
    if sheet_data is None:
        # Default: one valid sheet with 3 rows of compressor test data.
        # Pressures in Pa, temperatures in degC.
        sheet_data = {
            "Gen5_33_EHV_MEB_heat_pickup": {
                "RPM": [2000.0, 3000.0, 4000.0],
                "Ps": [500000.0, 500000.0, 500000.0],
                "Ts": [15.0, 15.0, 15.0],
                "Pd": [2000000.0, 2000000.0, 2000000.0],
                "Td": [85.0, 90.0, 95.0],
                "Tm": [45.0, 50.0, 55.0],
                "P_loss": [10.0, 12.0, 15.0],
            },
        }

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for sheet_name, data in sheet_data.items():
            df = pd.DataFrame(data)
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    buffer.seek(0)
    return buffer.getvalue(), filename


def _reset_compressor_storage() -> None:
    """Clear the in-memory compressor dataset store."""
    import routers.compressor as comp_router
    comp_router._datasets.clear()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_storage():
    """Reset compressor router state before each test."""
    _reset_compressor_storage()
    yield
    _reset_compressor_storage()


# ---------------------------------------------------------------------------
# 1. Upload endpoint — valid multi-sheet Excel
# ---------------------------------------------------------------------------
class TestUploadEndpoint:
    """Tests for POST /api/compressor/upload."""

    def test_upload_valid_excel_returns_200(self):
        """Upload a valid Excel file and verify response structure."""
        content, filename = _make_compressor_excel()

        response = client.post(
            "/api/compressor/upload",
            files={"file": (filename, content, "application/vnd.ms-excel.sheet.macroEnabled.12")},
        )

        assert response.status_code == 200, f"Body: {response.text}"
        data = response.json()

        # Filename in response comes from the parse result (may differ from upload name)
        assert isinstance(data["filename"], str)
        assert len(data["filename"]) > 0
        assert isinstance(data["sheets"], list)
        assert len(data["sheets"]) == 1

        sheet = data["sheets"][0]
        assert sheet["sheet_name"] == "Gen5_33_EHV_MEB_heat_pickup"
        assert sheet["n_points"] == 3
        assert "RPM" in sheet["columns_found"] or "rpm" in sheet["columns_found"]
        assert sheet["errors"] == []

        assert data["total_points"] == 3
        assert data["valid_sheets"] == 1
        assert data["invalid_sheets"] == 0

    def test_upload_multi_sheet_excel(self):
        """Upload a file with multiple sheets (some valid, some invalid)."""
        sheet_data = {
            "Variant_A_heat_pickup": {
                "RPM": [3000.0],
                "Ps": [500000.0],
                "Ts": [15.0],
                "Pd": [2000000.0],
                "Td": [85.0],
                "Tm": [45.0],
                "P_loss": [10.0],
            },
            "Invalid_Sheet": {
                "RPM": [3000.0],
                # Missing Ps, Ts, Pd, Td, Tm, P_loss
            },
        }
        content, filename = _make_compressor_excel(sheet_data)

        response = client.post(
            "/api/compressor/upload",
            files={"file": (filename, content, "application/octet-stream")},
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["sheets"]) == 2
        assert data["valid_sheets"] >= 1
        assert data["invalid_sheets"] >= 1

    def test_upload_invalid_file_type_returns_400(self):
        """Upload a non-Excel file and verify 400 error."""
        response = client.post(
            "/api/compressor/upload",
            files={"file": ("test.txt", b"not an excel file", "text/plain")},
        )

        assert response.status_code == 400

    def test_upload_corrupt_excel_returns_400(self):
        """Upload a corrupt file with Excel extension and verify 400."""
        response = client.post(
            "/api/compressor/upload",
            files={"file": ("bad.xlsm", b"corrupt data", "application/octet-stream")},
        )

        assert response.status_code == 400


# ---------------------------------------------------------------------------
# 2. Datasets endpoint — list after upload
# ---------------------------------------------------------------------------
class TestDatasetsEndpoint:
    """Tests for GET /api/compressor/datasets."""

    def test_datasets_empty_initially(self):
        """GET datasets returns empty list before any upload."""
        response = client.get("/api/compressor/datasets")

        assert response.status_code == 200
        data = response.json()
        assert data["datasets"] == []

    def test_datasets_after_upload(self):
        """GET datasets returns uploaded file after upload."""
        content, filename = _make_compressor_excel()

        # Upload first
        upload_resp = client.post(
            "/api/compressor/upload",
            files={"file": (filename, content, "application/octet-stream")},
        )
        assert upload_resp.status_code == 200

        # Then list
        response = client.get("/api/compressor/datasets")

        assert response.status_code == 200
        data = response.json()
        assert len(data["datasets"]) == 1

        ds = data["datasets"][0]
        assert ds["filename"] == filename
        assert isinstance(ds["sheets"], list)
        assert len(ds["sheets"]) >= 1
        assert ds["total_points"] > 0


# ---------------------------------------------------------------------------
# 3. Predict endpoint — single-point prediction
# ---------------------------------------------------------------------------
class TestPredictEndpoint:
    """Tests for POST /api/compressor/predict."""

    def test_predict_with_defaults_returns_200(self):
        """Predict with reasonable operating point and default params."""
        payload = {
            "RPM": 3000.0,
            "Ps": 500000.0,
            "Ts": 15.0,
            "Pd": 2000000.0,
        }

        response = client.post("/api/compressor/predict", json=payload)

        assert response.status_code == 200, f"Body: {response.text}"
        data = response.json()

        # Verify response structure
        pred = data["prediction"]
        assert "Tm" in pred
        assert "Td" in pred
        assert "Torque" in pred
        assert "Q_recirc" in pred
        assert "MotorLoss" in pred
        assert "hm" in pred
        assert "hd" in pred
        assert "mdot" in pred

        # Physical sanity checks
        assert pred["mdot"] > 0, "Mass flow should be positive"
        assert pred["Td"] > pred["Tm"], "Discharge temp should exceed motor temp"
        assert pred["MotorLoss"] >= 0, "Motor loss should be non-negative"

    def test_predict_with_custom_params(self):
        """Predict with custom calibration and motor params."""
        payload = {
            "RPM": 3000.0,
            "Ps": 500000.0,
            "Ts": 15.0,
            "Pd": 2000000.0,
            "calibration_params": {
                "UA_0": 22.3,
                "UA_1": 1.30,
                "eta_vol": 0.85,
                "eta_s": 0.70,
                "R_coil_core": 0.05,
                "h_ref": 1.0,
            },
        }

        response = client.post("/api/compressor/predict", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["prediction"]["mdot"] > 0

    def test_predict_convergence_with_reasonable_inputs(self):
        """Verify converged=True for physically reasonable operating point."""
        payload = {
            "RPM": 3000.0,
            "Ps": 500000.0,
            "Ts": 15.0,
            "Pd": 2000000.0,
            "calibration_params": {
                "UA_0": 22.3,
                "UA_1": 1.30,
                "eta_vol": 0.85,
                "eta_s": 0.70,
                "R_coil_core": 0.05,
                "h_ref": 1.0,
            },
        }

        response = client.post("/api/compressor/predict", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["converged"] is True, (
            f"Solver should converge for reasonable inputs. "
            f"Iterations: {data.get('iterations')}"
        )

    def test_predict_validation_rejects_eta_s_above_1(self):
        """Predict with eta_s > 1.0 should return 422."""
        payload = {
            "RPM": 3000.0,
            "Ps": 500000.0,
            "Ts": 15.0,
            "Pd": 2000000.0,
            "calibration_params": {
                "UA_0": 22.3,
                "UA_1": 1.30,
                "eta_vol": 0.85,
                "eta_s": 1.5,  # Invalid: > 1.0
                "R_coil_core": 0.05,
                "h_ref": 1.0,
            },
        }

        response = client.post("/api/compressor/predict", json=payload)

        assert response.status_code == 422

    def test_predict_validation_rejects_negative_rpm(self):
        """Predict with negative RPM should return 422."""
        payload = {
            "RPM": -1000.0,
            "Ps": 500000.0,
            "Ts": 15.0,
            "Pd": 2000000.0,
        }

        response = client.post("/api/compressor/predict", json=payload)

        assert response.status_code == 422

    def test_predict_validation_rejects_negative_pressure(self):
        """Predict with negative pressure should return 422."""
        payload = {
            "RPM": 3000.0,
            "Ps": -500000.0,
            "Ts": 15.0,
            "Pd": 2000000.0,
        }

        response = client.post("/api/compressor/predict", json=payload)

        assert response.status_code == 422

    def test_predict_zero_rpm_handles_zero_flow(self):
        """Predict with RPM=0 produces zero flow; the solver handles this edge case."""
        payload = {
            "RPM": 0.0,
            "Ps": 500000.0,
            "Ts": 15.0,
            "Pd": 2000000.0,
        }

        response = client.post("/api/compressor/predict", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["prediction"]["mdot"] == 0.0
        assert data["converged"] is False


# ---------------------------------------------------------------------------
# 6. Calibrate endpoint — SSE with synthetic data
# ---------------------------------------------------------------------------
class TestCalibrateEndpoint:
    """Tests for POST /api/compressor/calibrate."""

    def test_calibrate_returns_sse_stream(self):
        """Calibrate with uploaded data should return SSE events."""
        # First upload a dataset
        content, filename = _make_compressor_excel()
        upload_resp = client.post(
            "/api/compressor/upload",
            files={"file": (filename, content, "application/octet-stream")},
        )
        assert upload_resp.status_code == 200
        file_id = upload_resp.json()["file_id"]

        # Start calibration
        payload = {
            "file_id": file_id,
        }

        response = client.post("/api/compressor/calibrate", json=payload)

        # SSE responses come as streaming, TestClient reads the full body
        assert response.status_code == 200, f"Body: {response.text}"
        assert "text/event-stream" in response.headers.get("content-type", "")

    def test_calibrate_missing_file_returns_404(self):
        """Calibrate with non-existent file_id returns 404."""
        payload = {"file_id": "nonexistent_id"}

        response = client.post("/api/compressor/calibrate", json=payload)

        assert response.status_code == 404

    def test_calibrate_with_sheet_name_filter(self):
        """Calibrate targeting a specific sheet name."""
        content, filename = _make_compressor_excel()
        upload_resp = client.post(
            "/api/compressor/upload",
            files={"file": (filename, content, "application/octet-stream")},
        )
        file_id = upload_resp.json()["file_id"]

        payload = {
            "file_id": file_id,
            "sheet_name": "Gen5_33_EHV_MEB_heat_pickup",
        }

        response = client.post("/api/compressor/calibrate", json=payload)

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 7. Error handling
# ---------------------------------------------------------------------------
class TestErrorHandling:
    """Edge case and error handling tests."""

    def test_upload_empty_excel_returns_200_with_zero_points(self):
        """Upload an Excel file with empty sheets."""
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df = pd.DataFrame({"RPM": [], "Ps": []})
            df.to_excel(writer, sheet_name="EmptySheet", index=False)
        buffer.seek(0)

        response = client.post(
            "/api/compressor/upload",
            files={"file": ("empty.xlsm", buffer.getvalue(), "application/octet-stream")},
        )

        assert response.status_code == 200
        data = response.json()
        # Empty sheet should be listed as invalid
        assert data["total_points"] == 0

    def test_predict_missing_required_field_returns_422(self):
        """Predict without required field (Pd) returns 422."""
        payload = {
            "RPM": 3000.0,
            "Ps": 500000.0,
            "Ts": 15.0,
            # Missing Pd
        }

        response = client.post("/api/compressor/predict", json=payload)

        assert response.status_code == 422

    def test_calibrate_empty_file_id_returns_422(self):
        """Calibrate without file_id returns 422."""
        payload = {}

        response = client.post("/api/compressor/calibrate", json=payload)

        assert response.status_code == 422

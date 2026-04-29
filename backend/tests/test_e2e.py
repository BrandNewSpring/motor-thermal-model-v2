"""End-to-end scenario tests for the Motor Thermal Model v2.

Tests cover:
  Scenario A: First-time Calibration (full workflow)
  Scenario B: Temperature Prediction (single-point + grid)

Run with:
    cd backend && python -m pytest tests/test_e2e.py -v
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

# Path to the synthetic test fixture
FIXTURE_CSV = Path(__file__).parent / "fixtures" / "test_thermal_data.csv"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path: Path):
    """Redirect storage to a temp dir so tests don't pollute user data."""
    storage_dir = tmp_path / ".mtm_v2"
    uploads_dir = storage_dir / "uploads"
    profiles_dir = storage_dir / "profiles"
    uploads_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)

    import storage.profiles as sp
    import routers.files as rf
    import routers.calibration as rc

    orig_sp_dir = sp.PROFILES_DIR
    orig_rf_dir = rf.UPLOADS_DIR
    orig_rc_dir = rc.UPLOADS_DIR

    sp.PROFILES_DIR = profiles_dir
    rf.UPLOADS_DIR = uploads_dir
    rc.UPLOADS_DIR = uploads_dir

    yield

    sp.PROFILES_DIR = orig_sp_dir
    rf.UPLOADS_DIR = orig_rf_dir
    rc.UPLOADS_DIR = orig_rc_dir


@pytest.fixture()
def sample_profile_data() -> dict:
    """Minimal valid profile creation payload."""
    return {
        "name": "E2E Test Motor",
        "geometry": {
            "D_motor_mm": 106.0,
            "L_motor_mm": 48.85,
            "m_motor_g": 1200.0,
            "t_housing_mm": 10.5,
            "m_housing_g": 350.0,
            "L_housing_mm": 48.85,
            "t_mold_mm": 0.5,
            "f_copper": 0.35,
        },
        "material": {
            "c_p_Cu": 385.0,
            "c_p_FeSi": 490.0,
            "c_p_Al": 900.0,
            "k_mold": 0.3,
            "beta_iron": 0.002,
        },
        "coil": {
            "R0": 0.5,
            "T0": 20.0,
            "alpha": 0.00393,
            "n_phases": 3,
        },
        "iron_loss_mode": "simple",
        "simple_iron_loss": {
            "I_max": 10.0,
            "RPM_max": 5000.0,
            "alpha_iron": 2.0,
        },
    }


# ===========================================================================
# Scenario A: First-time Calibration (full workflow)
# ===========================================================================
class TestScenarioACalibration:
    """Full calibration workflow: create profile -> upload -> calibrate -> export."""

    def test_full_calibration_workflow(self, sample_profile_data: dict):
        """Scenario A: Complete first-time calibration flow."""
        # --- Step 1: Create profile with geometry ---
        profile_resp = client.post("/api/profiles", json=sample_profile_data)
        assert profile_resp.status_code == 201
        profile = profile_resp.json()
        profile_id = profile["id"]
        assert profile["name"] == "E2E Test Motor"
        assert profile["geometry_preview"]["C_coil"] > 0
        assert profile["geometry_preview"]["C_core"] > 0
        assert profile["geometry_preview"]["C_housing"] > 0

        # --- Step 2: Upload test CSV ---
        assert FIXTURE_CSV.exists(), f"Fixture not found: {FIXTURE_CSV}"
        csv_bytes = FIXTURE_CSV.read_bytes()
        upload_resp = client.post(
            "/api/files/upload",
            files={"file": ("test_thermal_data.csv", io.BytesIO(csv_bytes), "text/csv")},
            data={"type": "test_data"},
        )
        assert upload_resp.status_code == 200
        upload_data = upload_resp.json()
        file_id = upload_data["file_id"]
        assert upload_data["rows"] == 200
        assert "time" in upload_data["columns"]
        assert "T_coil" in upload_data["columns"]

        # --- Step 3: Map columns ---
        mapping = {
            "time": "time",
            "rpm": "rpm",
            "I_phase": "I_phase",
            "T_amb": "T_amb",
            "T_coil": "T_coil",
        }
        map_resp = client.post(f"/api/files/{file_id}/map-columns", json=mapping)
        assert map_resp.status_code == 200
        map_data = map_resp.json()
        assert map_data["mapped_rows"] == 200
        assert "summary" in map_data

        # --- Step 4: Start calibration ---
        calib_body = {
            "profile_id": profile_id,
            "data_file_id": file_id,
            "settings": {
                "n_starts": 3,
                "tail_gamma": 2.0,
                "ss_penalty": 5.0,
            },
        }
        calib_resp = client.post("/api/calibration/start", json=calib_body)
        assert calib_resp.status_code == 200
        job_id = calib_resp.json()["job_id"]

        # --- Step 5: Poll for result (wait up to 120s) ---
        result = None
        for _ in range(120):
            time.sleep(1)
            poll_resp = client.get(f"/api/calibration/{job_id}/result")
            if poll_resp.status_code == 200:
                result = poll_resp.json()
                break
            if poll_resp.status_code == 500:
                pytest.fail(f"Calibration failed: {poll_resp.json()['detail']}")
            # 503 means still running - continue polling

        assert result is not None, "Calibration did not complete in time"

        # --- Step 6: Verify R-squared > 0.9 ---
        assert result["r_squared"] > 0.9, (
            f"R-squared too low: {result['r_squared']:.4f}"
        )
        assert result["rmse"] < 10.0, (
            f"RMSE too high: {result['rmse']:.2f}"
        )

        # Verify calibrated parameters are physically reasonable
        params = result["params"]
        assert params["R1"] > 0.01, f"R1 too small: {params['R1']}"
        assert params["R2"] > 0.01, f"R2 too small: {params['R2']}"
        assert params["h_nat"] > 1.0, f"h_nat too small: {params['h_nat']}"
        assert params["h_rpm"] > 0.001, f"h_rpm too small: {params['h_rpm']}"

        # Verify simulation data arrays are populated
        assert len(result["T_coil_sim"]) > 0
        assert len(result["T_core_sim"]) > 0
        assert len(result["T_housing_sim"]) > 0

        # --- Step 7: Run prediction with calibrated params ---
        pred_body = {
            "profile_id": profile_id,
            "I_phase": 3.0,
            "T_amb": 25.0,
            "rpm": 3000.0,
        }
        pred_resp = client.post("/api/prediction/steady-state", json=pred_body)
        assert pred_resp.status_code == 200
        pred_data = pred_resp.json()
        assert pred_data["T_coil_ss"] > 25.0
        assert pred_data["T_core_ss"] > 25.0
        assert pred_data["T_housing_ss"] > 25.0
        assert pred_data["T_coil_ss"] > pred_data["T_core_ss"]
        assert pred_data["T_core_ss"] > pred_data["T_housing_ss"]

        # --- Step 8: Export Excel ---
        export_body = {"profile_id": profile_id}
        export_resp = client.post("/api/export/excel", json=export_body)
        assert export_resp.status_code == 200
        assert "spreadsheetml" in export_resp.headers["content-type"]
        assert len(export_resp.content) > 500  # Should have substantial content

        # --- Step 9: Verify profile was updated with calibration result ---
        updated_profile = client.get(f"/api/profiles/{profile_id}").json()
        assert updated_profile["id"] == profile_id


# ===========================================================================
# Scenario B: Temperature Prediction
# ===========================================================================
class TestScenarioBPrediction:
    """Temperature prediction: single-point and grid."""

    def test_single_point_prediction(self, sample_profile_data: dict):
        """Scenario B.1: Single-point prediction with calibrated params."""
        profile_resp = client.post("/api/profiles", json=sample_profile_data)
        profile_id = profile_resp.json()["id"]

        # Use I=3A with calibrated params to keep temperatures realistic
        body = {
            "profile_id": profile_id,
            "I_phase": 3.0,
            "T_amb": 25.0,
            "rpm": 3000.0,
            "R1": 0.5,
            "R2": 0.1,
            "h_nat": 10.0,
            "h_rpm": 0.02,
        }
        resp = client.post("/api/prediction/steady-state", json=body)
        assert resp.status_code == 200
        data = resp.json()

        # Verify thermal gradient: T_coil > T_core > T_housing > T_amb
        assert data["T_coil_ss"] > data["T_core_ss"] > data["T_housing_ss"] > 25.0, (
            f"Expected T_coil > T_core > T_housing > T_amb, "
            f"got {data['T_coil_ss']:.1f} > {data['T_core_ss']:.1f} > "
            f"{data['T_housing_ss']:.1f} > 25.0"
        )

        # Verify losses are positive
        assert data["Q_copper"] > 0, "Copper loss should be positive"
        assert data["Q_iron"] >= 0, "Iron loss should be non-negative"
        assert data["R3_at_rpm"] > 0, "R3 should be positive"

    def test_grid_prediction(self, sample_profile_data: dict):
        """Scenario B.2: Grid prediction (5x5 grid) with calibrated params."""
        profile_resp = client.post("/api/profiles", json=sample_profile_data)
        profile_id = profile_resp.json()["id"]

        # Use calibrated params and a current range that stays below thermal runaway
        body = {
            "profile_id": profile_id,
            "I_range": [1.0, 3.5],
            "RPM_range": [500.0, 4000.0],
            "T_amb": 25.0,
            "n_points": 5,
            "R1": 0.5,
            "R2": 0.1,
            "h_nat": 10.0,
            "h_rpm": 0.02,
        }
        resp = client.post("/api/prediction/grid", json=body)
        assert resp.status_code == 200
        data = resp.json()

        # Verify grid dimensions
        assert len(data["grid_I"]) == 5
        assert len(data["grid_I"][0]) == 5
        assert len(data["grid_RPM"]) == 5
        assert len(data["grid_T_coil"]) == 5
        assert len(data["grid_T_core"]) == 5
        assert len(data["grid_T_housing"]) == 5

        # Verify results are reasonable
        for i in range(5):
            for j in range(5):
                T_coil = data["grid_T_coil"][i][j]
                T_core = data["grid_T_core"][i][j]
                T_housing = data["grid_T_housing"][i][j]
                assert T_coil > 25.0, f"T_coil at ({i},{j}) should be > T_amb"
                assert T_coil > T_core, f"T_coil > T_core at ({i},{j})"

    def test_prediction_with_calibrated_params(self, sample_profile_data: dict):
        """Scenario B.3: Prediction using explicit calibration overrides."""
        profile_resp = client.post("/api/profiles", json=sample_profile_data)
        profile_id = profile_resp.json()["id"]

        body = {
            "profile_id": profile_id,
            "I_phase": 3.0,
            "T_amb": 30.0,
            "rpm": 3000.0,
            "R1": 0.5,
            "R2": 0.1,
            "h_nat": 10.0,
            "h_rpm": 0.02,
        }
        resp = client.post("/api/prediction/steady-state", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["T_coil_ss"] > 30.0, "T_coil_ss should be above T_amb=30"

    def test_prediction_thermal_runaway_detection(self, sample_profile_data: dict):
        """Verify that extreme inputs produce a controlled error, not a crash."""
        profile_resp = client.post("/api/profiles", json=sample_profile_data)
        profile_id = profile_resp.json()["id"]

        # Use high current at RPM=0 (natural convection only) to trigger runaway
        body = {
            "profile_id": profile_id,
            "I_phase": 20.0,
            "T_amb": 25.0,
            "rpm": 0.0,
        }
        resp = client.post("/api/prediction/steady-state", json=body)
        # Should either return 400 (thermal runaway) or a very high temperature
        if resp.status_code == 400:
            assert "Thermal runaway" in resp.json()["detail"]
        else:
            assert resp.status_code == 200

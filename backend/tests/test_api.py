"""API smoke tests for the Motor Thermal Model v2 backend.

Tests cover:
  1. Health check
  2. Profile CRUD (list, create, get, update, delete, copy)
  3. Compute-geometry endpoint
  4. File upload (CSV)
  5. File columns and column mapping
  6. Calibration start (with synthetic data)
  7. Prediction steady-state
  8. Export Excel

Run with:
    cd backend && python -m pytest tests/test_api.py -v
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


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
        "name": "Test Motor",
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
# Tests
# ===========================================================================
class TestHealthCheck:
    def test_health(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestProfilesList:
    def test_list_profiles_empty(self):
        resp = client.get("/api/profiles")
        assert resp.status_code == 200
        assert resp.json() == []


class TestProfileCreate:
    def test_create_profile(self, sample_profile_data: dict):
        resp = client.post("/api/profiles", json=sample_profile_data)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Motor"
        assert "id" in data
        assert data["geometry_preview"] is not None
        assert data["geometry_preview"]["C_coil"] > 0
        assert data["geometry_preview"]["C_core"] > 0
        assert data["geometry_preview"]["C_housing"] > 0

    def test_create_profile_minimal(self):
        payload = {
            "name": "Minimal Motor",
            "geometry": {
                "D_motor_mm": 80.0,
                "L_motor_mm": 40.0,
                "m_motor_g": 800.0,
                "t_housing_mm": 8.0,
                "m_housing_g": 200.0,
            },
        }
        resp = client.post("/api/profiles", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Minimal Motor"
        assert data["material"]["c_p_Cu"] == 385.0
        assert data["coil"]["R0"] == 0.5


class TestProfileGet:
    def test_get_profile(self, sample_profile_data: dict):
        create_resp = client.post("/api/profiles", json=sample_profile_data)
        profile_id = create_resp.json()["id"]

        resp = client.get(f"/api/profiles/{profile_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == profile_id

    def test_get_profile_not_found(self):
        resp = client.get("/api/profiles/nonexistent-id")
        assert resp.status_code == 404


class TestProfileUpdate:
    def test_update_profile_name(self, sample_profile_data: dict):
        create_resp = client.post("/api/profiles", json=sample_profile_data)
        profile_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/profiles/{profile_id}",
            json={"name": "Updated Motor"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Motor"


class TestProfileDelete:
    def test_delete_profile(self, sample_profile_data: dict):
        create_resp = client.post("/api/profiles", json=sample_profile_data)
        profile_id = create_resp.json()["id"]

        resp = client.delete(f"/api/profiles/{profile_id}")
        assert resp.status_code == 204

        get_resp = client.get(f"/api/profiles/{profile_id}")
        assert get_resp.status_code == 404


class TestProfileCopy:
    def test_copy_profile(self, sample_profile_data: dict):
        create_resp = client.post("/api/profiles", json=sample_profile_data)
        profile_id = create_resp.json()["id"]

        resp = client.post(f"/api/profiles/{profile_id}/copy")
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] != profile_id
        assert "(copy)" in data["name"]


class TestComputeGeometry:
    def test_compute_geometry(self):
        resp = client.post(
            "/api/profiles/compute-geometry",
            json={
                "geometry": {
                    "D_motor_mm": 106.0,
                    "L_motor_mm": 48.85,
                    "m_motor_g": 1200.0,
                    "t_housing_mm": 10.5,
                    "m_housing_g": 350.0,
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["C_coil"] > 0
        assert data["C_core"] > 0
        assert data["C_housing"] > 0
        assert data["A_interface_m2"] > 0
        assert data["A_housing_m2"] > 0
        assert data["R2_mold_init"] > 0
        assert data["R3_nat_init"] > 0
        assert data["tau_coil_s"] > 0

    def test_compute_geometry_with_material(self):
        resp = client.post(
            "/api/profiles/compute-geometry",
            json={
                "geometry": {
                    "D_motor_mm": 106.0,
                    "L_motor_mm": 48.85,
                    "m_motor_g": 1200.0,
                    "t_housing_mm": 10.5,
                    "m_housing_g": 350.0,
                },
                "material": {
                    "c_p_Cu": 400.0,
                    "c_p_FeSi": 500.0,
                    "c_p_Al": 950.0,
                    "k_mold": 0.4,
                    "beta_iron": 0.003,
                },
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["C_coil"] > 0


class TestFileUpload:
    def test_file_upload_csv(self):
        csv_content = b"time,rpm,I_phase,T_amb,T_coil\n0,1000,5.0,25.0,30.0\n1,1500,6.0,25.0,35.0\n2,2000,7.0,25.0,40.0"
        resp = client.post(
            "/api/files/upload",
            files={"file": ("test_data.csv", io.BytesIO(csv_content), "text/csv")},
            data={"type": "test_data"},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert "file_id" in result
        assert result["filename"] == "test_data.csv"
        assert result["rows"] == 3
        assert "time" in result["columns"]
        assert len(result["preview"]) == 3

    def test_file_upload_json_body_rejected(self):
        resp = client.post(
            "/api/files/upload",
            json={"type": "test_data"},
        )
        assert resp.status_code == 422

    def test_file_upload_unsupported(self):
        resp = client.post(
            "/api/files/upload",
            files={"file": ("data.txt", io.BytesIO(b"hello"), "text/plain")},
            data={"type": "test_data"},
        )
        assert resp.status_code == 400


class TestFileColumns:
    def test_get_columns(self):
        csv_content = b"time,rpm,I_phase,T_amb,T_coil\n0,1000,5.0,25.0,30.0\n1,1500,6.0,25.0,35.0"
        upload_resp = client.post(
            "/api/files/upload",
            files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")},
            data={"type": "test_data"},
        )
        file_id = upload_resp.json()["file_id"]

        resp = client.get(f"/api/files/{file_id}/columns")
        assert resp.status_code == 200
        result = resp.json()
        assert "time" in result["columns"]
        assert len(result["sample"]) == 2


class TestColumnMapping:
    def test_map_columns(self):
        csv_content = b"time,rpm,I_phase,T_amb,T_coil\n0,1000,5.0,25.0,30.0\n1,1500,6.0,25.0,35.0"
        upload_resp = client.post(
            "/api/files/upload",
            files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")},
            data={"type": "test_data"},
        )
        file_id = upload_resp.json()["file_id"]

        mapping = {
            "time": "time",
            "rpm": "rpm",
            "I_phase": "I_phase",
            "T_amb": "T_amb",
            "T_coil": "T_coil",
        }
        resp = client.post(f"/api/files/{file_id}/map-columns", json=mapping)
        assert resp.status_code == 200
        result = resp.json()
        assert result["mapped_rows"] == 2
        assert "summary" in result

    def test_map_columns_invalid(self):
        csv_content = b"time,rpm,I_phase,T_amb,T_coil\n0,1000,5.0,25.0,30.0"
        upload_resp = client.post(
            "/api/files/upload",
            files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")},
            data={"type": "test_data"},
        )
        file_id = upload_resp.json()["file_id"]

        mapping = {
            "I_phase": "nonexistent_column",
            "T_amb": "T_amb",
            "T_coil": "T_coil",
        }
        resp = client.post(f"/api/files/{file_id}/map-columns", json=mapping)
        assert resp.status_code == 422


class TestFileDelete:
    def test_delete_file(self):
        csv_content = b"a,b\n1,2"
        upload_resp = client.post(
            "/api/files/upload",
            files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")},
            data={"type": "test_data"},
        )
        file_id = upload_resp.json()["file_id"]

        resp = client.delete(f"/api/files/{file_id}")
        assert resp.status_code == 200

        resp2 = client.delete(f"/api/files/{file_id}")
        assert resp2.status_code == 404


class TestCalibrationStart:
    def test_calibration_start(self, sample_profile_data: dict):
        # Create profile
        profile_resp = client.post("/api/profiles", json=sample_profile_data)
        profile_id = profile_resp.json()["id"]

        # Upload synthetic CSV
        N = 100
        t = np.linspace(0, 2000, N)
        I = np.full(N, 3.0)
        rpm = np.full(N, 3000.0)
        T_amb = np.full(N, 25.0)
        T_coil = 25.0 + (60.0 - 25.0) * (t / t[-1])

        lines = ["time,rpm,I_phase,T_amb,T_coil"]
        for i in range(N):
            lines.append(f"{t[i]:.2f},{rpm[i]:.0f},{I[i]:.1f},{T_amb[i]:.1f},{T_coil[i]:.2f}")
        csv_bytes = "\n".join(lines).encode("utf-8")

        upload_resp = client.post(
            "/api/files/upload",
            files={"file": ("synthetic.csv", io.BytesIO(csv_bytes), "text/csv")},
            data={"type": "test_data"},
        )
        assert upload_resp.status_code == 200
        file_id = upload_resp.json()["file_id"]

        # Start calibration
        calib_body = {
            "profile_id": profile_id,
            "data_file_id": file_id,
            "settings": {
                "n_starts": 1,
                "tail_gamma": 2.0,
                "ss_penalty": 5.0,
            },
        }
        resp = client.post("/api/calibration/start", json=calib_body)
        assert resp.status_code == 200
        result = resp.json()
        assert "job_id" in result


class TestPrediction:
    def test_steady_state_prediction(self, sample_profile_data: dict):
        profile_resp = client.post("/api/profiles", json=sample_profile_data)
        profile_id = profile_resp.json()["id"]

        body = {
            "profile_id": profile_id,
            "I_phase": 3.0,
            "T_amb": 25.0,
            "rpm": 3000.0,
        }
        resp = client.post("/api/prediction/steady-state", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["T_coil_ss"] > 25.0
        assert data["T_core_ss"] > 25.0
        assert data["T_housing_ss"] > 25.0
        assert data["T_coil_ss"] > data["T_core_ss"] > data["T_housing_ss"]
        assert data["Q_copper"] > 0
        assert data["R3_at_rpm"] > 0

    def test_prediction_profile_not_found(self):
        body = {
            "profile_id": "nonexistent",
            "I_phase": 3.0,
            "T_amb": 25.0,
            "rpm": 3000.0,
        }
        resp = client.post("/api/prediction/steady-state", json=body)
        assert resp.status_code == 404


class TestExport:
    def test_export_excel(self, sample_profile_data: dict):
        profile_resp = client.post("/api/profiles", json=sample_profile_data)
        profile_id = profile_resp.json()["id"]

        body = {"profile_id": profile_id}
        resp = client.post("/api/export/excel", json=body)
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers["content-type"]
        assert len(resp.content) > 0

    def test_export_profile_not_found(self):
        body = {"profile_id": "nonexistent"}
        resp = client.post("/api/export/excel", json=body)
        assert resp.status_code == 404


class TestFileUploadBatch:
    def test_upload_batch_multiple_files(self):
        csv1 = b"time,rpm,I_phase,T_amb,T_coil\n0,1000,5.0,25.0,30.0\n1,1500,6.0,25.0,35.0"
        csv2 = b"time,rpm,I_phase,T_amb,T_coil\n0,2000,4.0,26.0,28.0\n1,2500,5.5,26.0,33.0\n2,3000,7.0,26.0,40.0"

        resp = client.post(
            "/api/files/upload-batch",
            files=[
                ("files", ("data1.csv", io.BytesIO(csv1), "text/csv")),
                ("files", ("data2.csv", io.BytesIO(csv2), "text/csv")),
            ],
            data={"type": "test_data"},
        )
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 2
        assert results[0]["filename"] == "data1.csv"
        assert results[0]["rows"] == 2
        assert results[1]["filename"] == "data2.csv"
        assert results[1]["rows"] == 3
        assert results[0]["file_id"] != results[1]["file_id"]

    def test_upload_batch_invalid_type(self):
        csv_content = b"a,b\n1,2"
        resp = client.post(
            "/api/files/upload-batch",
            files=[
                ("files", ("data.csv", io.BytesIO(csv_content), "text/csv")),
            ],
            data={"type": "invalid_type"},
        )
        assert resp.status_code == 400

    def test_upload_batch_unsupported_file(self):
        resp = client.post(
            "/api/files/upload-batch",
            files=[
                ("files", ("data.txt", io.BytesIO(b"hello"), "text/plain")),
            ],
            data={"type": "test_data"},
        )
        assert resp.status_code == 400


class TestFileConditions:
    def test_extract_conditions(self):
        csv_content = (
            b"time,rpm,I_phase,T_amb,T_coil\n"
            b"0,1000,5.0,25.0,30.0\n"
            b"10,1500,6.0,25.5,35.0\n"
            b"20,2000,7.0,26.0,40.0"
        )
        upload_resp = client.post(
            "/api/files/upload",
            files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")},
            data={"type": "test_data"},
        )
        file_id = upload_resp.json()["file_id"]

        mapping = {
            "time": "time",
            "rpm": "rpm",
            "I_phase": "I_phase",
            "T_amb": "T_amb",
            "T_coil": "T_coil",
        }
        resp = client.post(f"/api/files/{file_id}/conditions", json=mapping)
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_id"] == file_id
        assert data["filename"] == "data.csv"
        assert data["rows"] == 3
        assert data["I_range"] == [5.0, 7.0]
        assert data["rpm_range"] == [1000.0, 2000.0]
        assert data["T_amb_mean"] is not None
        assert abs(data["T_amb_mean"] - 25.5) < 0.01
        assert data["T_coil_range"] == [30.0, 40.0]
        assert data["duration_s"] == 20.0

    def test_extract_conditions_missing_column(self):
        csv_content = b"time,rpm,I_phase,T_amb,T_coil\n0,1000,5.0,25.0,30.0"
        upload_resp = client.post(
            "/api/files/upload",
            files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")},
            data={"type": "test_data"},
        )
        file_id = upload_resp.json()["file_id"]

        mapping = {
            "I_phase": "nonexistent_column",
            "T_amb": "T_amb",
            "T_coil": "T_coil",
        }
        resp = client.post(f"/api/files/{file_id}/conditions", json=mapping)
        assert resp.status_code == 422

    def test_extract_conditions_file_not_found(self):
        mapping = {
            "I_phase": "I_phase",
            "T_amb": "T_amb",
            "T_coil": "T_coil",
        }
        resp = client.post("/api/files/nonexistent-id/conditions", json=mapping)
        assert resp.status_code == 404


class TestCalibrationMultiFile:
    def test_calibration_multi_file_ids(self, sample_profile_data: dict):
        # Create profile
        profile_resp = client.post("/api/profiles", json=sample_profile_data)
        profile_id = profile_resp.json()["id"]

        # Upload two synthetic CSV files
        N = 50
        t = np.linspace(0, 1000, N)
        I = np.full(N, 3.0)
        rpm = np.full(N, 3000.0)
        T_amb = np.full(N, 25.0)
        T_coil = 25.0 + (55.0 - 25.0) * (t / t[-1])

        file_ids = []
        for label in ["file1", "file2"]:
            lines = ["time,rpm,I_phase,T_amb,T_coil"]
            for i in range(N):
                lines.append(f"{t[i]:.2f},{rpm[i]:.0f},{I[i]:.1f},{T_amb[i]:.1f},{T_coil[i]:.2f}")
            csv_bytes = "\n".join(lines).encode("utf-8")

            upload_resp = client.post(
                "/api/files/upload",
                files={"file": (f"{label}.csv", io.BytesIO(csv_bytes), "text/csv")},
                data={"type": "test_data"},
            )
            assert upload_resp.status_code == 200
            file_ids.append(upload_resp.json()["file_id"])

        # Start calibration with data_file_ids
        calib_body = {
            "profile_id": profile_id,
            "data_file_ids": file_ids,
            "settings": {
                "n_starts": 1,
                "tail_gamma": 2.0,
                "ss_penalty": 5.0,
            },
        }
        resp = client.post("/api/calibration/start", json=calib_body)
        assert resp.status_code == 200
        result = resp.json()
        assert "job_id" in result

    def test_calibration_legacy_single_file_id(self, sample_profile_data: dict):
        """Backward compatibility: single data_file_id still works."""
        profile_resp = client.post("/api/profiles", json=sample_profile_data)
        profile_id = profile_resp.json()["id"]

        N = 50
        t = np.linspace(0, 1000, N)
        I = np.full(N, 3.0)
        rpm = np.full(N, 3000.0)
        T_amb = np.full(N, 25.0)
        T_coil = 25.0 + (55.0 - 25.0) * (t / t[-1])

        lines = ["time,rpm,I_phase,T_amb,T_coil"]
        for i in range(N):
            lines.append(f"{t[i]:.2f},{rpm[i]:.0f},{I[i]:.1f},{T_amb[i]:.1f},{T_coil[i]:.2f}")
        csv_bytes = "\n".join(lines).encode("utf-8")

        upload_resp = client.post(
            "/api/files/upload",
            files={"file": ("synthetic.csv", io.BytesIO(csv_bytes), "text/csv")},
            data={"type": "test_data"},
        )
        file_id = upload_resp.json()["file_id"]

        calib_body = {
            "profile_id": profile_id,
            "data_file_id": file_id,
            "settings": {"n_starts": 1},
        }
        resp = client.post("/api/calibration/start", json=calib_body)
        assert resp.status_code == 200
        assert "job_id" in resp.json()

    def test_calibration_no_file_id_error(self, sample_profile_data: dict):
        """Must reject request with neither data_file_id nor data_file_ids."""
        profile_resp = client.post("/api/profiles", json=sample_profile_data)
        profile_id = profile_resp.json()["id"]

        calib_body = {
            "profile_id": profile_id,
            "settings": {"n_starts": 1},
        }
        resp = client.post("/api/calibration/start", json=calib_body)
        assert resp.status_code == 422

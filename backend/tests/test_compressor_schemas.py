"""Tests for compressor Pydantic schemas (REQ-COMP-DATA-001).

TDD RED phase: Schema validation tests for all compressor-related
request and response models.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# 1. CompressorOperatingPoint
# ---------------------------------------------------------------------------
class TestCompressorOperatingPoint:
    """Input operating conditions for compressor prediction."""

    def test_valid_operating_point(self) -> None:
        from schemas.compressor import CompressorOperatingPoint

        op = CompressorOperatingPoint(RPM=3000, Ps=200_000, Ts=5.0, Pd=800_000)
        assert op.RPM == 3000
        assert op.Ps == 200_000
        assert op.Ts == 5.0
        assert op.Pd == 800_000

    def test_rpm_must_be_non_negative(self) -> None:
        from schemas.compressor import CompressorOperatingPoint

        with pytest.raises(ValidationError):
            CompressorOperatingPoint(RPM=-100, Ps=200_000, Ts=5.0, Pd=800_000)

    def test_pressures_must_be_positive(self) -> None:
        from schemas.compressor import CompressorOperatingPoint

        with pytest.raises(ValidationError):
            CompressorOperatingPoint(RPM=3000, Ps=0, Ts=5.0, Pd=800_000)
        with pytest.raises(ValidationError):
            CompressorOperatingPoint(RPM=3000, Ps=200_000, Ts=5.0, Pd=-1)


# ---------------------------------------------------------------------------
# 2. CompressorPrediction
# ---------------------------------------------------------------------------
class TestCompressorPrediction:
    """Prediction output from compressor thermal model."""

    def test_valid_prediction(self) -> None:
        from schemas.compressor import CompressorPrediction

        pred = CompressorPrediction(
            Tm=45.0, Td=85.0, Torque=12.5, Q_recirc=0.3,
            MotorLoss=150.0, hm=500.0, hd=200.0, mdot=0.05,
        )
        assert pred.Tm == 45.0
        assert pred.mdot == 0.05

    def test_prediction_has_all_fields(self) -> None:
        from schemas.compressor import CompressorPrediction

        pred = CompressorPrediction(
            Tm=45.0, Td=85.0, Torque=12.5, Q_recirc=0.3,
            MotorLoss=150.0, hm=500.0, hd=200.0, mdot=0.05,
        )
        field_names = set(pred.__class__.model_fields.keys())
        expected = {"Tm", "Td", "Torque", "Q_recirc", "MotorLoss", "hm", "hd", "mdot"}
        assert expected.issubset(field_names)


# ---------------------------------------------------------------------------
# 3. CompressorPredictionRequest
# ---------------------------------------------------------------------------
class TestCompressorPredictionRequest:
    """Request body for compressor prediction."""

    def test_minimal_request(self) -> None:
        from schemas.compressor import CompressorPredictionRequest

        req = CompressorPredictionRequest(
            RPM=3000, Ps=200_000, Ts=5.0, Pd=800_000,
        )
        assert req.RPM == 3000
        assert req.calibration_params is None

    def test_request_with_optional_calibration(self) -> None:
        from schemas.compressor import (
            CompressorCalibrationParams,
            CompressorPredictionRequest,
        )

        params = CompressorCalibrationParams()
        req = CompressorPredictionRequest(
            RPM=3000, Ps=200_000, Ts=5.0, Pd=800_000,
            calibration_params=params,
        )
        assert req.calibration_params is not None
        assert req.calibration_params.UA_0 is not None


# ---------------------------------------------------------------------------
# 4. CompressorPredictionResponse
# ---------------------------------------------------------------------------
class TestCompressorPredictionResponse:
    """Response with prediction results and convergence info."""

    def test_valid_response(self) -> None:
        from schemas.compressor import CompressorPrediction, CompressorPredictionResponse

        pred = CompressorPrediction(
            Tm=45.0, Td=85.0, Torque=12.5, Q_recirc=0.3,
            MotorLoss=150.0, hm=500.0, hd=200.0, mdot=0.05,
        )
        resp = CompressorPredictionResponse(
            prediction=pred,
            converged=True,
            iterations=12,
        )
        assert resp.converged is True
        assert resp.iterations == 12

    def test_response_defaults(self) -> None:
        from schemas.compressor import CompressorPrediction, CompressorPredictionResponse

        pred = CompressorPrediction(
            Tm=45.0, Td=85.0, Torque=12.5, Q_recirc=0.3,
            MotorLoss=150.0, hm=500.0, hd=200.0, mdot=0.05,
        )
        resp = CompressorPredictionResponse(prediction=pred)
        assert resp.converged is True  # default
        assert resp.iterations == 0  # default


# ---------------------------------------------------------------------------
# 5. CompressorDataPoint
# ---------------------------------------------------------------------------
class TestCompressorDataPoint:
    """Single test data point with all measured columns."""

    def test_valid_data_point(self) -> None:
        from schemas.compressor import CompressorDataPoint

        dp = CompressorDataPoint(
            RPM=3000, Ps=200_000, Ts=5.0, Pd=800_000,
            Td=85.0, Tm=45.0, I_motor=10.0, mdot=0.05,
        )
        assert dp.RPM == 3000
        assert dp.mdot == 0.05

    def test_optional_fields_default_none(self) -> None:
        from schemas.compressor import CompressorDataPoint

        dp = CompressorDataPoint(
            RPM=3000, Ps=200_000, Ts=5.0, Pd=800_000,
        )
        assert dp.Td is None
        assert dp.Tm is None
        assert dp.torque is None


# ---------------------------------------------------------------------------
# 6. CompressorDataset and CompressorUploadResponse
# ---------------------------------------------------------------------------
class TestCompressorDataset:
    """Named dataset (sheet) with list of data points."""

    def test_valid_dataset(self) -> None:
        from schemas.compressor import CompressorDataPoint, CompressorDataset

        points = [
            CompressorDataPoint(RPM=3000, Ps=200_000, Ts=5.0, Pd=800_000),
            CompressorDataPoint(RPM=3500, Ps=250_000, Ts=10.0, Pd=900_000),
        ]
        ds = CompressorDataset(name="Sheet1", data_points=points)
        assert ds.name == "Sheet1"
        assert len(ds.data_points) == 2


class TestCompressorUploadResponse:
    """Upload metadata with sheet names and point counts."""

    def test_valid_upload_response(self) -> None:
        from schemas.compressor import CompressorUploadResponse

        resp = CompressorUploadResponse(
            file_id="abc-123",
            filename="test.xlsx",
            sheets=["Sheet1", "Sheet2"],
            point_counts={"Sheet1": 50, "Sheet2": 30},
        )
        assert resp.file_id == "abc-123"
        assert resp.point_counts["Sheet1"] == 50


# ---------------------------------------------------------------------------
# 7. CompressorCalibrationRequest
# ---------------------------------------------------------------------------
class TestCompressorCalibrationRequest:
    """Dataset selection + optimization settings for calibration."""

    def test_minimal_calibration_request(self) -> None:
        from schemas.compressor import CompressorCalibrationRequest

        req = CompressorCalibrationRequest(file_id="abc-123")
        assert req.file_id == "abc-123"
        assert req.sheet_name is None

    def test_calibration_request_with_sheet(self) -> None:
        from schemas.compressor import CompressorCalibrationRequest

        req = CompressorCalibrationRequest(
            file_id="abc-123", sheet_name="Sheet1",
        )
        assert req.sheet_name == "Sheet1"


# ---------------------------------------------------------------------------
# 8. CompressorCalibrationResult
# ---------------------------------------------------------------------------
class TestCompressorCalibrationResult:
    """Calibrated parameters + RMSE, R^2, residuals."""

    def test_valid_calibration_result(self) -> None:
        from schemas.compressor import CompressorCalibrationParams, CompressorCalibrationResult

        params = CompressorCalibrationParams()
        result = CompressorCalibrationResult(
            params=params,
            rmse=1.5,
            r_squared=0.95,
            residuals=[0.1, -0.2, 0.15],
        )
        assert result.rmse == 1.5
        assert result.r_squared == 0.95

    def test_result_contains_calibrated_params(self) -> None:
        from schemas.compressor import CompressorCalibrationParams, CompressorCalibrationResult

        params = CompressorCalibrationParams(
            UA_0=100.0, UA_1=0.5, eta_vol=0.85, eta_s=0.75,
            R_coil_core=0.01, h_ref=500.0,
        )
        result = CompressorCalibrationResult(
            params=params, rmse=1.0, r_squared=0.9, residuals=[],
        )
        assert result.params.UA_0 == 100.0
        assert result.params.eta_vol == 0.85


# ---------------------------------------------------------------------------
# 9. CompressorCalibrationParams
# ---------------------------------------------------------------------------
class TestCompressorCalibrationParams:
    """Calibration parameters: UA_0, UA_1, eta_vol, eta_s, R_coil_core, h_ref."""

    def test_default_params_exist(self) -> None:
        from schemas.compressor import CompressorCalibrationParams

        params = CompressorCalibrationParams()
        assert params.UA_0 is not None
        assert params.UA_1 is not None
        assert params.eta_vol is not None
        assert params.eta_s is not None
        assert params.R_coil_core is not None
        assert params.h_ref is not None

    def test_custom_params(self) -> None:
        from schemas.compressor import CompressorCalibrationParams

        params = CompressorCalibrationParams(
            UA_0=200.0, UA_1=1.0, eta_vol=0.9, eta_s=0.8,
            R_coil_core=0.02, h_ref=600.0,
        )
        assert params.UA_0 == 200.0
        assert params.eta_s == 0.8


# ---------------------------------------------------------------------------
# 10. CompressorProgressEvent
# ---------------------------------------------------------------------------
class TestCompressorProgressEvent:
    """SSE progress event for compressor calibration."""

    def test_progress_event(self) -> None:
        from schemas.compressor import CompressorProgressEvent

        evt = CompressorProgressEvent(
            type="progress",
            iteration=5,
            rmse=2.3,
            message="Optimizing...",
        )
        assert evt.type == "progress"
        assert evt.iteration == 5

    def test_done_event(self) -> None:
        from schemas.compressor import CompressorCalibrationParams, CompressorCalibrationResult
        from schemas.compressor import CompressorProgressEvent

        params = CompressorCalibrationParams()
        result = CompressorCalibrationResult(
            params=params, rmse=0.5, r_squared=0.98, residuals=[],
        )
        evt = CompressorProgressEvent(
            type="done",
            result=result,
        )
        assert evt.type == "done"
        assert evt.result is not None
        assert evt.result.r_squared == 0.98

    def test_error_event(self) -> None:
        from schemas.compressor import CompressorProgressEvent

        evt = CompressorProgressEvent(
            type="error",
            message="Optimization failed to converge",
        )
        assert evt.type == "error"
        assert "failed" in evt.message.lower()

"""Pydantic schemas for the Motor Thermal Model v2 API."""

from .calibration import (
    CalibProgressEvent,
    CalibRequest,
    CalibResult,
    CalibSettings,
    ColumnMapping,
    ThermalParams,
)
from .data import (
    ColumnMappingRequest,
    ColumnMappingResponse,
    ExportRequest,
    FileColumnsResponse,
    FileUploadResponse,
    GridPredictionRequest,
    GridPredictionResult,
    SteadyStateRequest,
    SteadyStateResult,
)
from .motor import (
    CoilParams,
    GeometryPreview,
    MaterialProps,
    MotorGeometry,
    MotorProfile,
    MotorProfileBase,
    MotorProfileCreate,
    MotorProfileSummary,
    MotorProfileUpdate,
    SimpleIronLoss,
)

__all__ = [
    # motor
    "CoilParams",
    "GeometryPreview",
    "MaterialProps",
    "MotorGeometry",
    "MotorProfile",
    "MotorProfileBase",
    "MotorProfileCreate",
    "MotorProfileSummary",
    "MotorProfileUpdate",
    "SimpleIronLoss",
    # calibration
    "CalibProgressEvent",
    "CalibRequest",
    "CalibResult",
    "CalibSettings",
    "ColumnMapping",
    "ThermalParams",
    # data
    "ColumnMappingRequest",
    "ColumnMappingResponse",
    "ExportRequest",
    "FileColumnsResponse",
    "FileUploadResponse",
    "GridPredictionRequest",
    "GridPredictionResult",
    "SteadyStateRequest",
    "SteadyStateResult",
]

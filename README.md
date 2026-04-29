# Motor Thermal Model v2

A physics-based 3-node lumped-parameter thermal model for electric motors, built with **FastAPI** (backend) and **React + TypeScript** (frontend).

## Overview

This tool predicts internal motor temperatures (coil, core, housing) from operating conditions (current, RPM, ambient temperature) using a calibrated thermal resistance network. It supports:

- Multi-start L-BFGS-B calibration from test data (CSV/Excel)
- Real-time calibration progress via Server-Sent Events (SSE)
- Steady-state temperature prediction (single-point and grid)
- Multiple motor profile management (JSON-based local storage)
- Excel export of calibration results

## Thermal Model

The 3-node thermal network represents heat flow from coil to ambient:

```
  Q_gen = Q_copper + Q_iron
         |
     [T_coil]  --R1--  [T_core]  --R2--  [T_housing]  --R3(RPM)--  T_amb
      C_coil             C_core              C_housing
```

**Calibrated parameters** (4 free parameters):
- R1: Coil-to-core thermal resistance [degC/W]
- R2: Core-to-housing thermal resistance [degC/W]
- h_nat: Natural convection coefficient [W/(m^2*K)]
- h_rpm: Forced convection coefficient [W/(m^2*K)/sqrt(RPM)]

**Fixed parameters** (computed from motor geometry):
- C_coil, C_core, C_housing: Thermal capacitances [J/degC]

## Prerequisites

- **Python 3.12+** (backend)
- **Node.js 18+** (frontend)
- npm or yarn

## Quick Start

### 1. Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v

# Start development server
uvicorn main:app --port 8000 --reload
```

The API is available at `http://localhost:8000`.

### 2. Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start development server (proxies /api to backend)
npm run dev
```

The app is available at `http://localhost:5173`.

### 3. Production Build

```bash
# Build frontend
cd frontend && npm run build

# Serve from FastAPI (copy dist/ to backend/static/)
cd ../backend && uvicorn main:app --port 8000
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/profiles` | List all profiles |
| POST | `/api/profiles` | Create a profile |
| GET | `/api/profiles/{id}` | Get a profile |
| PUT | `/api/profiles/{id}` | Update a profile |
| DELETE | `/api/profiles/{id}` | Delete a profile |
| POST | `/api/profiles/{id}/copy` | Copy a profile |
| POST | `/api/profiles/compute-geometry` | Preview computed geometry |
| POST | `/api/files/upload` | Upload CSV/Excel file |
| GET | `/api/files/{id}/columns` | Get file column info |
| POST | `/api/files/{id}/map-columns` | Validate column mapping |
| DELETE | `/api/files/{id}` | Delete uploaded file |
| POST | `/api/calibration/start` | Start calibration run |
| GET | `/api/calibration/{job_id}/stream` | SSE calibration progress |
| GET | `/api/calibration/{job_id}/result` | Get calibration result |
| POST | `/api/prediction/steady-state` | Single-point prediction |
| POST | `/api/prediction/grid` | Grid prediction (heatmap) |
| POST | `/api/export/excel` | Export to Excel |

## Motor Geometry Parameters

| Parameter | Default | Unit | Description |
|-----------|---------|------|-------------|
| D_motor_mm | 106.0 | mm | Stator outer diameter |
| L_motor_mm | 48.85 | mm | Stator axial length |
| t_housing_mm | 10.5 | mm | Housing wall thickness |
| m_motor_g | required | g | Total motor mass (incl. housing) |
| m_housing_g | required | g | Housing mass |
| t_mold_mm | 0.5 | mm | Mold interface thickness |
| f_copper | 0.35 | - | Copper fill fraction of stator mass |

## Test Data Format (CSV/Excel)

| Column | Required | Unit | Description |
|--------|----------|------|-------------|
| time | optional | s | Time (row index if missing) |
| rpm | optional | RPM | Rotor speed |
| I_phase | **required** | A | Phase current |
| T_amb | **required** | degC | Ambient temperature |
| T_coil | **required** | degC | Measured coil temperature |
| torque | optional | Nm | Torque (for loss map mode) |

## Loss Map Format (CSV/Excel)

| Column | Required | Unit |
|--------|----------|------|
| rpm | **required** | RPM |
| torque_nm | **required** | Nm |
| p_copper_w | optional | W |
| p_iron_w | **required** | W |

## Project Structure

```
motor-thermal-model-v2/
  backend/
    main.py              # FastAPI app entry point
    core/
      motor_geometry.py  # Thermal mass & resistance computation
      thermal_model.py   # 3-node ODE solver
      loss_model.py      # Copper & iron loss models
      calibration.py     # Multi-start L-BFGS-B optimizer
    routers/
      profiles.py        # Profile CRUD endpoints
      files.py           # File upload & parsing
      calibration.py     # Calibration with SSE streaming
      prediction.py      # Temperature prediction
      export.py          # Excel export
    schemas/             # Pydantic models
    storage/             # JSON-based profile persistence
    tests/               # pytest test suite
  frontend/
    src/
      components/        # React components
      pages/             # Page-level views
      stores/            # Zustand state management
      hooks/             # Custom React hooks
      lib/               # API client & utilities
      types/             # TypeScript type definitions
```

## Testing

```bash
# Backend tests (unit + API + E2E)
cd backend && source .venv/bin/activate
python -m pytest tests/ -v

# Frontend build check
cd frontend && npm run build
```

## License

Internal engineering tool. All rights reserved.

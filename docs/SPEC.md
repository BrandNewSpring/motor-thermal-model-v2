# Motor Thermal Model v2 — Technical Specification

**버전**: 1.0  
**작성일**: 2026-04-09

---

## 1. 데이터 모델 (Pydantic Schemas)

### 1.1 모터 형상 & 물성

```python
class MotorGeometry(BaseModel):
    # 모터 기본 치수
    D_motor_mm: float = 106.0       # 고정자 외경 [mm]
    L_motor_mm: float = 48.85       # 고정자 축방향 길이 [mm]
    m_motor_g:  float               # 모터 총 질량 (하우징 포함) [g]

    # 하우징
    t_housing_mm: float = 10.5      # 하우징 벽 두께 [mm]
    L_housing_mm: float             # 하우징 축방향 길이 [mm] (≈ L_motor)
    m_housing_g:  float             # 하우징 질량 [g]

    # 몰딩
    t_mold_mm: float = 0.5          # 코어-하우징 간 플라스틱 몰딩 두께 [mm]

    # 구리 충전율
    f_copper: float = 0.35          # 고정자 질량 중 구리 비율 (0–1)

class MaterialProps(BaseModel):
    # 재질별 비열 [J/kg·K]
    c_p_Cu:   float = 385.0
    c_p_FeSi: float = 490.0
    c_p_Al:   float = 900.0
    # 몰딩 열전도율 [W/m·K]
    k_mold:   float = 0.3
    # 철손 온도 보정 계수
    beta_iron: float = 0.002        # [1/K]

class CoilParams(BaseModel):
    R0:       float = 0.5           # 기준 저항 @ T₀ [Ω, 1상]
    T0:       float = 20.0          # 기준 온도 [°C]
    alpha:    float = 0.00393       # 저항 온도계수 [1/°C]
    n_phases: int   = 3
```

### 1.2 발열원 모델

```python
class IronLossMode(str, Enum):
    SIMPLE = "simple"       # 간편 모델
    MAP    = "map"          # FEA 손실 맵

class SimpleIronLoss(BaseModel):
    I_max:     float        # 기준 최대 전류 [A]
    RPM_max:   float        # 기준 최대 RPM
    alpha_iron: float = 2.0 # RPM 지수 (Q_iron ∝ RPM^alpha_iron)
    # Q_iron_max = 0.3 × n_phases × I_max² × R(T_ref)

class LossMapEntry(BaseModel):
    rpm:        float
    torque_nm:  float
    p_copper_w: float
    p_iron_w:   float
```

### 1.3 모터 프로필 (저장 단위)

```python
class MotorProfile(BaseModel):
    id:        str                          # UUID
    name:      str                          # 사용자 지정 이름
    created_at: datetime
    updated_at: datetime
    geometry:  MotorGeometry
    material:  MaterialProps
    coil:      CoilParams
    iron_loss_mode: IronLossMode = IronLossMode.SIMPLE
    simple_iron_loss: Optional[SimpleIronLoss] = None
    # 캘리브레이션 결과 (저장된 경우)
    calib_result: Optional[CalibResult] = None
```

### 1.4 캘리브레이션 요청 & 결과

```python
class CalibSettings(BaseModel):
    # 최적화 파라미터
    n_starts:         int   = 3
    tail_gamma:       float = 2.0
    ss_penalty:       float = 5.0
    normalize_per_file: bool = True
    # 자유 파라미터 초기값 (None이면 물리 추정값 사용)
    R1_init:   Optional[float] = None
    R2_init:   Optional[float] = None
    h_nat_init: float = 10.0
    h_rpm_init: float = 0.02
    # 탐색 범위 (None이면 자동)
    R1_bounds:  Optional[Tuple[float,float]] = None
    R2_bounds:  Optional[Tuple[float,float]] = None

class CalibRequest(BaseModel):
    profile_id:   str
    data_file_id: str              # 업로드된 파일 ID
    loss_map_file_id: Optional[str] = None
    settings:     CalibSettings

class ThermalParams(BaseModel):
    R1: float          # 코일↔코어 [°C/W]
    R2: float          # 코어↔하우징 [°C/W]
    h_nat: float       # 자연대류 [W/m²·K]
    h_rpm: float       # RPM 강제대류 계수 [W/m²·K/√RPM]
    # 계산된 파생값
    C_coil:    float   # 열용량 [J/°C]
    C_core:    float
    C_housing: float
    R2_mold:   float   # 몰딩만의 R₂ 이론값

class CalibResult(BaseModel):
    params:     ThermalParams
    rmse:       float
    r_squared:  float
    T_coil_sim: List[float]
    T_core_sim: List[float]      # 추정값
    T_housing_sim: List[float]   # 추정값
    residuals:  List[float]
    time_s:     float            # 최적화 소요 시간
```

---

## 2. API 엔드포인트

### 2.1 파일 업로드

```
POST /api/files/upload
Content-Type: multipart/form-data
Body: { file: File, type: "test_data" | "loss_map" }

Response 200:
{
  "file_id": "uuid",
  "filename": "test_data.csv",
  "rows": 1200,
  "columns": ["time", "rpm", "I_phase", "T_amb", "T_coil", "torque"],
  "preview": [...]   // 첫 5행
}
```

```
GET /api/files/{file_id}/columns
Response: { "columns": [...], "sample": [...] }

POST /api/files/{file_id}/map-columns
Body: { "time": "col_name", "rpm": "col_name", ... }
Response: { "mapped_rows": 1200, "summary": {...} }
```

### 2.2 모터 프로필 CRUD

```
GET    /api/profiles               → List[MotorProfile]
POST   /api/profiles               → MotorProfile  (신규 생성)
GET    /api/profiles/{id}          → MotorProfile
PUT    /api/profiles/{id}          → MotorProfile  (수정)
DELETE /api/profiles/{id}          → 204
POST   /api/profiles/{id}/copy     → MotorProfile  (복사)
```

### 2.3 형상 계산 (실시간 미리보기)

```
POST /api/profiles/compute-geometry
Body: MotorGeometry + MaterialProps
Response:
{
  "C_coil":    float,    // J/°C
  "C_core":    float,
  "C_housing": float,
  "A_interface_m2": float,
  "A_housing_m2":   float,
  "R2_mold_init":   float,   // °C/W
  "R3_nat_init":    float,   // °C/W (RPM=0)
  "tau_coil_s":     float,   // 추정 시정수 [s]
}
```

### 2.4 캘리브레이션

```
POST /api/calibration/start
Body: CalibRequest
Response: { "job_id": "uuid" }

GET /api/calibration/{job_id}/stream     ← SSE
Event stream:
  data: {"type":"progress", "start":1, "n_starts":3, "iter":45, "rmse":2.31, "elapsed":12.3}
  data: {"type":"phase", "message":"Phase 1: 파일별 독립 캘리브레이션..."}
  data: {"type":"done", "result": CalibResult}
  data: {"type":"error", "message":"..."}

GET /api/calibration/{job_id}/result     ← 완료 후 폴링 용
Response: CalibResult
```

### 2.5 온도 예측

```
POST /api/prediction/steady-state
Body:
{
  "profile_id": "uuid",
  "I_phase": float,
  "T_amb": float,
  "RPM": float
}
Response:
{
  "T_coil_ss": float,
  "T_core_ss": float,
  "T_housing_ss": float,
  "Q_copper": float,
  "Q_iron": float,
  "R3_at_rpm": float
}

POST /api/prediction/grid
Body:
{
  "profile_id": "uuid",
  "I_range": [float, float],
  "RPM_range": [float, float],
  "T_amb": float,
  "n_points": int
}
Response:
{
  "grid_I":       [[...]],   // 2D array
  "grid_RPM":     [[...]],
  "grid_T_coil":  [[...]],
  "grid_T_core":  [[...]],
  "grid_T_housing": [[...]]
}
```

### 2.6 결과 내보내기

```
GET /api/export/{job_id}/excel
Response: Excel 파일 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
시트: 모델 요약 / Calibration 상세 / 예측 격자
```

---

## 3. 프론트엔드 컴포넌트 트리

```
App
├── Layout
│   ├── Sidebar
│   │   ├── ProfileSelector       # 프로필 드롭다운 + 관리 버튼
│   │   └── NavMenu               # 캘리브레이션 / 예측 / 프로필
│   └── MainContent
│       ├── CalibrationPage
│       │   ├── StepWizard        # 4단계 마법사 UI
│       │   │   ├── Step1_FileUpload
│       │   │   │   ├── FileDropZone
│       │   │   │   └── ColumnMapper
│       │   │   ├── Step2_MotorProfile
│       │   │   │   ├── GeometryForm      # 형상 입력
│       │   │   │   ├── MaterialForm      # 물성 입력
│       │   │   │   └── GeometryPreview   # 계산된 C, R 미리보기
│       │   │   ├── Step3_LossModel
│       │   │   │   ├── SimpleLossForm    # 간편 모델
│       │   │   │   └── LossMapUpload     # FEA 손실 맵 업로드
│       │   │   └── Step4_CalibSettings
│       │   │       └── CalibSettingsForm
│       │   ├── CalibProgress         # SSE 진행바 + 로그
│       │   └── CalibResults
│       │       ├── ParamMetrics      # R₁, R₂, h_nat, h_rpm 카드
│       │       ├── ThermalNetworkDiagram  # SVG 다이어그램
│       │       ├── TemperatureChart      # 측정 vs 시뮬 (Plotly)
│       │       ├── ThreeNodeChart        # T_coil, T_core, T_housing
│       │       ├── HeatSourceChart       # Q_copper vs Q_iron
│       │       └── DetailTable          # 상세 데이터 테이블
│       ├── PredictionPage
│       │   ├── SinglePointForm
│       │   ├── SinglePointResult
│       │   └── HeatmapChart          # (I, RPM) → T_coil 격자
│       └── ProfilesPage
│           ├── ProfileList
│           ├── ProfileCard
│           └── ProfileEditModal
```

---

## 4. 전역 상태 (Zustand Store)

```typescript
interface AppStore {
  // 현재 선택된 프로필
  currentProfileId: string | null
  setCurrentProfile: (id: string) => void

  // 업로드된 파일
  testFileId: string | null
  lossMapFileId: string | null

  // 캘리브레이션 진행 상황
  calibJobId: string | null
  calibStatus: 'idle' | 'running' | 'done' | 'error'
  calibProgress: ProgressEvent[]

  // 캘리브레이션 결과
  calibResult: CalibResult | null
}
```

---

## 5. 물리 엔진 코어 함수 시그니처 (Python)

```python
# motor_geometry.py
def compute_thermal_masses(geo: MotorGeometry, mat: MaterialProps) -> ThermalMasses:
    """
    Returns C_coil, C_core, C_housing [J/°C]
    and A_interface, A_housing [m²]
    """

def compute_initial_resistances(geo: MotorGeometry, mat: MaterialProps) -> InitialResistances:
    """
    Returns R2_mold [°C/W], R3_nat_init [°C/W] (at RPM=0)
    """

# thermal_model.py
def simulate_3node(
    t:       np.ndarray,       # 시간 [s]
    I:       np.ndarray,       # 상전류 [A]
    RPM:     np.ndarray,       # RPM
    T_amb:   np.ndarray,       # 분위기온도 [°C]
    torque:  Optional[np.ndarray],  # 토크 [Nm] (손실 맵 모드)
    masses:  ThermalMasses,
    R1: float, R2: float,
    h_nat: float, h_rpm: float,
    A_housing: float,
    coil: CoilParams,
    loss_fn: Callable,          # loss_model.get_heat_sources
    T_init: float = None,
    rtol=1e-3, atol=1e-2,
) -> SimResult:
    """
    3-노드 ODE 적분.
    Returns T_coil, T_core, T_housing arrays.
    """

# loss_model.py
def get_heat_sources_simple(
    I: float, T_coil: float, RPM: float,
    coil: CoilParams,
    iron: SimpleIronLoss,
) -> Tuple[float, float]:          # Q_copper, Q_iron

def get_heat_sources_map(
    I: float, T_coil: float, RPM: float, torque: float,
    coil: CoilParams,
    loss_map: pd.DataFrame,
    beta_iron: float = 0.002,
) -> Tuple[float, float]:          # Q_copper, Q_iron

# calibration.py
def calibrate_3node(
    df: pd.DataFrame,
    profile: MotorProfile,
    loss_map: Optional[pd.DataFrame],
    settings: CalibSettings,
    progress_callback: Optional[Callable] = None,
) -> CalibResult:
    """
    Multi-start L-BFGS-B in log-space.
    Free params: [R1, R2, h_nat, h_rpm]
    Fixed: C_coil, C_core, C_housing (from geometry)
    """
```

---

## 6. SSE 이벤트 스키마

```typescript
type SSEEvent =
  | { type: 'phase';    message: string }
  | { type: 'progress'; start: number; n_starts: number;
      iter: number; rmse: number; elapsed: number }
  | { type: 'done';     result: CalibResult }
  | { type: 'error';    message: string }
```

---

## 7. 파일 저장 구조 (로컬)

```
~/.mtm_v2/                          # (또는 앱 실행 디렉토리)
├── profiles/
│   ├── {uuid}.json                 # MotorProfile JSON
│   └── ...
├── uploads/
│   ├── {file_id}_{filename}
│   └── ...
└── results/
    └── {job_id}_result.json
```

---

## 8. 에러 코드

| 코드 | 의미 |
|------|------|
| 400 | 잘못된 입력 (Pydantic validation) |
| 404 | 프로필 / 파일 없음 |
| 422 | 컬럼 매핑 오류 (필수 컬럼 없음) |
| 500 | ODE 적분 실패 / 최적화 수렴 실패 |
| 503 | 최적화 중복 실행 방지 |

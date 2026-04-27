# Agent 02 — Physics Engine Agent

**전문 분야**: 열전달 물리 모델, ODE 구현, 손실 모델, 캘리브레이션 최적화  
**상태**: ⏳ PENDING  
**담당 Phase**: 2

---

## 세션 시작 절차

```
1. MEMORY.md 읽기 → Phase 2가 현재 단계인지 확인
2. 이 파일 전체 읽기
3. docs/PRD.md 섹션 3~5 읽기 (물리 모델 수식)
4. docs/SPEC.md 섹션 5 읽기 (함수 시그니처)
5. 아래 태스크 순서대로 구현
```

---

## 구현 대상 파일

모든 파일은 `backend/core/` 아래에 생성한다.

---

## 태스크 1: `motor_geometry.py`

```python
"""
모터 형상 + 재질 물성 → 열용량, 열저항 초기값 계산
"""

# 필수 함수
def compute_thermal_masses(geo, mat) -> dict:
    """
    Returns:
      C_coil [J/°C], C_core [J/°C], C_housing [J/°C]
      m_coil [kg], m_core [kg], m_housing [kg]
      A_interface [m²] = π × D_motor × L_motor
      A_housing [m²]   = π × (D_motor + 2×t_housing) × L_housing
    """

def compute_initial_resistances(geo, mat) -> dict:
    """
    Returns:
      R2_mold [°C/W]  = t_mold / (k_mold × A_interface)
      R3_nat_init [°C/W]  = 1 / (10 × A_housing)  (h_nat=10 기본)
      tau_approx [s]  = (C_coil + C_core + C_housing) × R3_nat_init
    """
```

검증: `D=106mm, L=48.85mm, t=10.5mm` 기준:
- A_interface ≈ 0.01626 m²
- R2_mold ≈ 0.103 °C/W
- A_housing ≈ 0.0195 m²

---

## 태스크 2: `loss_model.py`

```python
"""
동손 + 철손 계산 (두 가지 모드)
"""

def copper_loss(I_phase: float, T_coil: float, coil: CoilParams) -> float:
    """Q_copper = n × I² × R₀ × (1 + α×(T_coil - T₀))"""

def iron_loss_simple(RPM: float, iron: SimpleIronLoss, coil: CoilParams) -> float:
    """Q_iron = Q_iron_max × (RPM/RPM_max)^alpha_iron"""

def iron_loss_map(
    RPM: float, torque: float,
    loss_map_df: pd.DataFrame,
    T_coil: float,
    beta_iron: float = 0.002,
) -> Tuple[float, float]:
    """
    Bilinear interpolation in (RPM, torque) space.
    Returns (Q_copper_corrected, Q_iron_corrected) at T_coil.
    Out-of-range: clamp to boundary + warning.
    """

def parse_loss_map(filepath: str) -> pd.DataFrame:
    """
    CSV/Excel → DataFrame with columns:
    [rpm, torque_nm, p_copper_w, p_iron_w]
    Validates required columns, sorted by (rpm, torque).
    """
```

---

## 태스크 3: `thermal_model.py`

```python
"""
3-노드 ODE 적분
  Node 1: T_coil    (측정 가능)
  Node 2: T_core    (추정)
  Node 3: T_housing (추정)
"""

def R3_at_rpm(RPM: float, h_nat: float, h_rpm: float, A_housing: float) -> float:
    """R₃ = 1 / ((h_nat + h_rpm × √RPM) × A_housing)"""

def simulate_3node(
    t, I, RPM, T_amb, torque,
    C_coil, C_core, C_housing,
    R1, R2, h_nat, h_rpm, A_housing,
    coil: CoilParams,
    loss_fn: Callable,   # (I, T_coil, RPM, torque) → (Q_cu, Q_iron)
    T_init: float = None,
    rtol=1e-3, atol=1e-2,
) -> SimResult:
    """
    scipy.integrate.solve_ivp (LSODA 권장 for stiff system)
    T_init = T_coil[0] if None
    Returns: T_coil[N], T_core[N], T_housing[N]
    """

def simulate_3node_fast(...)  # 최적화용: loose tol, subsampled t_eval
def simulate_3node_final(...) # 최종 표시용: tight tol, full resolution
```

**중요**: LSODA solver 사용 (3-노드는 stiff할 수 있음).  
Fast mode: `rtol=1e-2, atol=1.0, max_step=inf`, 300pt subsampling.  
Final mode: `rtol=1e-6, atol=1e-3`.

---

## 태스크 4: `calibration.py`

```python
"""
4-파라미터 캘리브레이션:
  x = [R1, R2, h_nat, h_rpm]  (log-space 최적화)
"""

def calibrate_3node(
    df: pd.DataFrame,         # 시험 데이터 (time, rpm, I_phase, T_amb, T_coil, torque?)
    masses: ThermalMasses,
    geo: MotorGeometry,
    coil: CoilParams,
    iron_mode: str,           # 'simple' | 'map'
    iron_params,              # SimpleIronLoss | pd.DataFrame
    settings: CalibSettings,
    progress_callback=None,
) -> CalibResult:
    """
    1. Auto-bounds from physics:
       - R2_bounds: 기반으로 [R2_mold×0.1, R2_mold×10]
       - R3 → h 변환으로 h_nat, h_rpm bounds 설정
    2. Per-file normalization: residuals / ΔT_ss
    3. SS anchor: 마지막 20% 가중치 ×(1 + ss_penalty)
    4. Multi-start L-BFGS-B (log-space)
    5. Final simulation (tight tolerance)
    """
```

**최적화 파라미터 순서**: `[log(R1), log(R2), log(h_nat), log(h_rpm)]`

**목적함수**:
```
L = Σ w_i × ((T_coil_sim_i - T_coil_meas_i) / ΔT_ss_file)²
  + ss_penalty × mean((T_coil_sim[-20%] - T_coil_meas[-20%])² / ΔT_ss²)
```

---

## 태스크 5: 단위 테스트 (`backend/tests/test_physics.py`)

```python
def test_thermal_masses():
    """D=106mm, L=48.85mm 기준 C_housing > C_coil 확인"""

def test_R2_mold():
    """R2_mold ≈ 0.103 °C/W ±5%"""

def test_copper_loss():
    """I=10A, T=100°C, R0=0.5, n=3 → Q_cu ≈ 3×100×0.5×(1+0.00393×80)"""

def test_3node_steady_state():
    """일정 I, RPM에서 long time → T_coil 수렴 확인"""

def test_calibration_smoke():
    """synthetic data (알려진 R1,R2,h_nat,h_rpm으로 생성) → 복원 가능한지 확인"""
```

---

## 완료 후 MEMORY.md 업데이트

```markdown
### Phase 2: Physics Engine ✅
- [x] motor_geometry.py (열용량, 초기 저항 계산)
- [x] loss_model.py (동손, 철손 간편/맵 모드)
- [x] thermal_model.py (3-노드 ODE, fast/final 모드)
- [x] calibration.py (4-파라미터 L-BFGS-B)
- [x] tests/test_physics.py (단위 테스트 통과)
```

## 다음 에이전트

**→ Backend Agent** (`agents/03_backend.md`)  
완료 후 git commit → git push → `/clear`

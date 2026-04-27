# Motor Thermal Model v2 — Product Requirements Document

**버전**: 1.0  
**작성일**: 2026-04-09  
**상태**: 승인 대기

---

## 1. 배경 및 목적

현재 Motor Thermal Model v1(Streamlit 기반 lumped-1mass 모델)은 다음 한계가 있다:
- 단일 열용량으로 모터 내부 온도 분포를 표현 불가
- RPM-R_th 파라미터가 실제 형상과 무관하여 물리적 해석 불가
- Streamlit의 상태관리 한계로 다중 모터 프로필 관리 불가
- 최적화 발산(R_th 과대 추정) 문제

v2는 **물리 기반 3-노드 열전달 모델**로 완전히 재설계하고, **FastAPI + React** 기반의 전문 엔지니어링 웹 앱으로 구축한다.

---

## 2. 목표 (Goals)

| ID | 목표 |
|----|------|
| G1 | 코일→코어→몰딩→하우징→대기의 직렬 3-노드 ODE 모델 구현 |
| G2 | 모터/하우징 형상 + 재질 물성으로 열용량(C) 자동 계산 |
| G3 | 4개 열저항 파라미터(R₁, R₂, h_nat, h_rpm) 캘리브레이션 |
| G4 | 동손: I²R(T) 직접 계산 / 철손: 간편 모델 + FEA 손실 맵 |
| G5 | 손실 맵 20°C → 동작 온도 자동 보정 |
| G6 | 다중 모터 프로필 관리 (저장/불러오기/비교) |
| G7 | 실시간 최적화 진행 상황 스트리밍 (SSE) |
| G8 | 토크 측정값 기반 손실 맵 bilinear 보간 |

## 비목표 (Non-Goals)

- 로터/회전자 열 노드 (측정 불가)
- 액냉(수냉/오일냉각)
- 2D/3D FEM 해석
- 사용자 인증/권한 관리 (향후 과제)

---

## 3. 대상 모터 사양 (기준 치수)

| 항목 | 값 | 단위 |
|-----|-----|------|
| 모터 타입 | IPM/SPM BLDC, Inner Rotor | — |
| 모터 외경 (D_motor) | 106 | mm |
| 모터 길이 (L_motor) | 48.85 | mm |
| 하우징 벽 두께 (t_housing) | 10.5 | mm |
| 하우징 소재 | 알루미늄 합금 | — |
| 냉각 방식 | 자연대류 + RPM 강제대류 | — |

---

## 4. 물리 모델

### 4.1 열 네트워크 토폴로지

```
  Q_gen = Q_copper + Q_iron
         ↓
     [T_coil]  ──R₁──  [T_core]  ──R₂──  [T_housing]  ──R₃(RPM)──  T_amb(t)
      C_coil               C_core              C_housing
```

**참고**: T_coil만 측정 가능. T_core, T_housing은 ODE 내부 상태.

### 4.2 지배 방정식

```
C_coil    · dT_coil/dt    = Q_gen(t)
                            - (T_coil   - T_core   ) / R₁

C_core    · dT_core/dt    = (T_coil   - T_core   ) / R₁
                            - (T_core   - T_housing) / R₂

C_housing · dT_housing/dt = (T_core   - T_housing) / R₂
                            - (T_housing - T_amb(t)) / R₃(RPM(t))
```

초기 조건: `T_coil(0) = T_core(0) = T_housing(0) = T_coil_measured[0]`

### 4.3 열용량 계산 (형상 + 물성 기반)

```
m_housing  = 사용자 입력 [g]
m_stator   = m_motor_total - m_housing
m_coil     = m_stator × f_copper     (기본 f_copper = 0.35)
m_core     = m_stator × (1 - f_copper)

C_coil    = m_coil    × c_p_Cu    (c_p_Cu  = 385  J/kg·K)
C_core    = m_core    × c_p_FeSi  (c_p_Fe  = 490  J/kg·K)
C_housing = m_housing × c_p_Al    (c_p_Al  = 900  J/kg·K)
```

### 4.4 열저항 모델

#### R₁: 코일 ↔ 코어 (자유 파라미터, 캘리브레이션)
등가 접촉 저항. 슬롯 내부 코일 배치, 와니스 함침 품질 등 포함.

#### R₂: 코어 ↔ 하우징 (몰딩 포함, 자유 파라미터)
물리 기반 초기값:
```
A_if   = π × D_motor × L_motor            [m²]   ≈ 0.01626 m²
R_mold = t_mold / (k_mold × A_if)         [°C/W] ≈ 0.103 °C/W
R₂_init = R_mold  (캘리브레이션 seed)
```

#### R₃(RPM): 하우징 ↔ 대기 (자유 파라미터 2개)
```
D_out  = D_motor + 2 × t_housing          [m]
A_out  = π × D_out × L_housing            [m²]   ≈ 0.0195 m²
h(RPM) = h_nat + h_rpm × √RPM             [W/m²·K]
R₃     = 1 / (h(RPM) × A_out)            [°C/W]
```

초기값: h_nat = 10, h_rpm = 0.02

### 4.5 발열원 모델

#### 동손 (항상 직접 계산)
```
R_coil(T) = R₀ × [1 + α × (T_coil - T₀)]
Q_copper  = n_phases × I_phase² × R_coil(T_coil)
```

#### 철손 — 모드 A: 간편 모델 (기본)
```
Q_iron_max = 0.3 × n_phases × I_max² × R₀ × [1 + α × (T_ref - T₀)]
Q_iron(t)  = Q_iron_max × (RPM(t) / RPM_max)^α_iron
```
사용자 입력: `I_max [A]`, `RPM_max [RPM]`, `α_iron` (기본 2.0)

#### 철손 — 모드 B: FEA 손실 맵
```
입력: CSV/Excel with columns [RPM, Torque_Nm, P_copper_ref_W, P_iron_ref_W]
기준 온도: 20°C

조회: bilinear interpolation (RPM(t), Torque_meas(t)) → P_cu_ref, P_iron_ref
보정:
  Q_copper(T) = P_cu_ref   × [1 + α × (T_coil - 20)]
  Q_iron(T)   = P_iron_ref × [1 - β × (T_coil - 20)]   (β = 0.002 기본값)
```

---

## 5. 캘리브레이션 방법

### 5.1 자유 파라미터 (4개)

| # | 파라미터 | 단위 | 초기값 | 탐색 범위 |
|---|---------|------|--------|-----------|
| 1 | R₁ | °C/W | 0.5 | 0.01 ~ 10 |
| 2 | R₂ | °C/W | R_mold (물리 추정) | 0.01 ~ 5 |
| 3 | h_nat | W/m²·K | 10 | 2 ~ 100 |
| 4 | h_rpm | W/m²·K/√RPM | 0.02 | 1e-4 ~ 2.0 |

### 5.2 최적화 전략

- 방법: log-space multi-start L-BFGS-B
- 목적: `Σ w_i × (T_coil_sim_i - T_coil_meas_i)²`
- 가중치: tail-biased (꼬리 강조) + SS anchor (마지막 20% ×6배)
- 물리 bounds: 에너지 평형에서 R₂ 초기 범위 자동 추정
- 진행 상황: Server-Sent Events로 실시간 스트리밍

---

## 6. 모터 프로필 관리 (Q3)

- 모터 기종별 형상/물성/캘리브레이션 파라미터 저장
- JSON 기반 로컬 저장 (서버 DB 없음, 향후 확장 가능)
- 프로필 CRUD: 생성/수정/삭제/복사
- 비교 모드: 2개 프로필 나란히 온도 예측 비교

---

## 7. 입력 데이터 사양

### 시험 데이터 (CSV / Excel)

| 컬럼 | 필수 | 단위 | 비고 |
|------|------|------|------|
| 시간 | 선택 | s | 없으면 row index 사용 |
| RPM | 권장 | RPM | |
| 상전류 I_phase | **필수** | A | |
| 분위기온도 T_amb | **필수** | °C | |
| 코일온도 T_coil | **필수** | °C | |
| 토크 | 선택 | Nm | 손실 맵 모드 시 필수 |

### 손실 맵 (CSV / Excel)

| 컬럼 | 필수 | 단위 |
|------|------|------|
| RPM | **필수** | RPM |
| Torque_Nm | **필수** | Nm |
| P_copper_ref_W | 선택 | W |
| P_iron_ref_W | **필수** (맵 모드) | W |

---

## 8. 출력

| 출력 항목 | 설명 |
|-----------|------|
| T_coil 비교 | 측정 vs 시뮬레이션 |
| T_core 예측 | 추정값 (측정 없음 명시) |
| T_housing 예측 | 추정값 (측정 없음 명시) |
| R₁, R₂, R₃(RPM) | 캘리브레이션 결과 + 불확실도 |
| Q_copper / Q_iron 분해 | 시계열 발열 차트 |
| 열저항 네트워크 다이어그램 | 수치 포함 |
| 정상 상태 예측 격자 | (I, RPM, T_amb) → T_coil_ss |
| Excel 내보내기 | 파라미터 + 시뮬레이션 상세 |

---

## 9. 미결 사항 (구현 전 결정 완료)

| # | 질문 | 답변 |
|---|------|------|
| Q1 | 토크 측정 여부 | **있음** → 손실 맵 직접 bilinear 보간 가능 |
| Q2 | 기준 치수 | **외경 106mm / 길이 48.85mm / 하우징 두께 10.5mm** |
| Q3 | 모터 프로필 관리 | **필요** → JSON 저장, CRUD UI |
| Q4 | 프레임워크 | **FastAPI + React** (STACK.md 참조) |

---

*다음 문서: STACK.md, SPEC.md*

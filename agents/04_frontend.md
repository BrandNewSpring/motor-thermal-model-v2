# Agent 04 — Frontend Agent

**전문 분야**: React 18 + TypeScript UI, 컴포넌트 구현, Plotly 차트  
**상태**: ⏳ PENDING  
**담당 Phase**: 4

---

## 세션 시작 절차

```
1. MEMORY.md 읽기 → Phase 4인지 확인, Phase 3 완료 여부 확인
2. 이 파일 전체 읽기
3. docs/SPEC.md 섹션 3~4 읽기 (컴포넌트 트리, Zustand 스토어)
4. 백엔드 API가 동작 중인지 확인: curl http://localhost:8000/api/profiles
5. 아래 태스크 순서대로 구현
```

---

## 구현 순서 (의존성 순서)

```
Types → API Client → Store → Layout → 
Pages (Calibration 우선) → Charts → Prediction → Profiles
```

---

## 태스크 1: TypeScript 타입 정의 (`src/types/`)

```typescript
// SPEC.md 스키마를 TypeScript로 변환
// src/types/motor.ts, calibration.ts, api.ts
interface MotorGeometry { D_motor_mm: number; ... }
interface CalibResult { params: ThermalParams; rmse: number; ... }
type SSEEvent = ProgressEvent | PhaseEvent | DoneEvent | ErrorEvent
```

---

## 태스크 2: API 클라이언트 (`src/lib/api.ts`)

```typescript
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })  // Vite proxy

export const profilesApi = {
  list:   () => api.get<MotorProfile[]>('/profiles'),
  get:    (id) => api.get<MotorProfile>(`/profiles/${id}`),
  create: (data) => api.post<MotorProfile>('/profiles', data),
  update: (id, data) => api.put<MotorProfile>(`/profiles/${id}`, data),
  delete: (id) => api.delete(`/profiles/${id}`),
  computeGeometry: (data) => api.post('/profiles/compute-geometry', data),
}

export const calibrationApi = {
  start:  (req) => api.post<{job_id: string}>('/calibration/start', req),
  result: (jobId) => api.get<CalibResult>(`/calibration/${jobId}/result`),
  // SSE는 별도 hook에서 EventSource 사용
}
// ... filesApi, predictionApi
```

---

## 태스크 3: Zustand 스토어 (`src/stores/appStore.ts`)

```typescript
interface AppStore {
  currentProfileId: string | null
  testFileId: string | null
  lossMapFileId: string | null
  calibJobId: string | null
  calibStatus: 'idle' | 'running' | 'done' | 'error'
  calibProgress: SSEEvent[]
  calibResult: CalibResult | null
  // actions
  setCurrentProfile, setTestFile, startCalib, updateProgress, finishCalib
}
```

---

## 태스크 4: 레이아웃 (`src/app/layout.tsx`)

```
┌──────────────┬─────────────────────────────────┐
│  Sidebar     │  Main Content                   │
│  - Logo      │  (페이지별 라우팅)                │
│  - Profile   │                                 │
│    Selector  │                                 │
│  - Nav Menu  │                                 │
│    ├ Calib   │                                 │
│    ├ Predict │                                 │
│    └ Profiles│                                 │
└──────────────┴─────────────────────────────────┘
```

React Router v6 사용. 3개 라우트: `/`, `/prediction`, `/profiles`

---

## 태스크 5: 캘리브레이션 페이지 (핵심) (`src/pages/Calibration.tsx`)

### 5a. StepWizard 컴포넌트

4단계 탭 + Stepper UI:

**Step 1 — 데이터 파일**
- `FileDropZone`: CSV/Excel 드래그&드롭
- `ColumnMapper`: 컬럼명 선택 (time, rpm, I_phase, T_amb, T_coil, torque)
- 데이터 미리보기 테이블 (5행)

**Step 2 — 모터 프로필**
- `GeometryForm`: 수치 입력 (shadcn Input + 단위 라벨)
  - D_motor, L_motor, m_motor, t_housing, L_housing, m_housing, t_mold, f_copper
- `MaterialForm`: c_p 값, k_mold (고급 설정 아코디언)
- `GeometryPreviewCard`: compute-geometry API 호출 → C_coil, C_core, C_housing 실시간 표시
- 기존 프로필 선택 또는 신규 생성 토글

**Step 3 — 발열 모델**
- 모드 선택: 간편 / FEA 손실 맵 (RadioGroup)
- 간편 모드: I_max, RPM_max, alpha_iron 입력
- 맵 모드: 손실 맵 파일 업로드 + 데이터 미리보기

**Step 4 — 캘리브레이션 설정**
- n_starts 슬라이더
- tail_gamma 슬라이더
- ss_penalty 슬라이더
- 초기값 입력 (R1, R2, h_nat, h_rpm) - 고급 아코디언

### 5b. CalibProgress 컴포넌트

```typescript
function useCalibSSE(jobId: string) {
  // EventSource('/api/calibration/{jobId}/stream')
  // → store에 progress 업데이트
}
```
- `Progress` 바 (shadcn)
- 현재 Start / 반복 수 / RMSE / 경과 시간 텍스트
- Phase 메시지 (Phase 1: 파일별 독립...)

### 5c. CalibResults 컴포넌트

결과가 있을 때 표시:

1. **파라미터 카드** (4개): R₁, R₂, h_nat, h_rpm + RMSE, R²
2. **열저항 네트워크 다이어그램** (SVG inline)  
   ```
   [Coil] ─R₁─ [Core] ─R₂─ [Housing] ─R₃(RPM)─ [Amb]
    C_coil       C_core       C_housing
   ```
3. **온도 비교 차트** (Plotly): T_coil 측정 vs 시뮬 + T_core(점선) + T_housing(점선)
4. **발열 분해 차트** (Plotly): Q_copper vs Q_iron 시계열 영역 차트
5. **R₃(RPM) 곡선** (Plotly): 0~RPM_max 범위

---

## 태스크 6: 예측 페이지 (`src/pages/Prediction.tsx`)

- 단일 조건 예측 폼 + 결과 카드 (T_coil_ss, T_core_ss, T_housing_ss)
- 격자 예측: I 범위, RPM 범위 입력 → Plotly Heatmap

---

## 태스크 7: 프로필 관리 페이지 (`src/pages/Profiles.tsx`)

- 프로필 카드 그리드 (모터 이름, RMSE, 파라미터 요약)
- 신규 생성 버튼 → 프로필 편집 모달 (shadcn Dialog)
- 삭제 확인 다이얼로그
- 비교 모드: 2개 프로필 선택 → T_coil 예측 오버레이 차트

---

## UI 디자인 가이드

- 컬러: 엔지니어링 다크 테마 또는 라이트 (tailwind slate 계열)
- 측정값: 파란색 (`hsl(217, 91%, 60%)`)
- 시뮬레이션: 빨간색 dashed
- T_core 추정: 초록색 dashed
- T_housing 추정: 주황색 dashed
- 에러 상태: `Alert` 컴포넌트 (shadcn)

---

## 완료 후 MEMORY.md 업데이트

```markdown
### Phase 4: Frontend ✅
- [x] TypeScript 타입 정의
- [x] API 클라이언트 (axios)
- [x] Zustand 스토어
- [x] 레이아웃 + 라우팅
- [x] 캘리브레이션 페이지 (4단계 마법사 + 진행바 + 결과)
- [x] 예측 페이지
- [x] 프로필 관리 페이지
- [x] 차트 (온도 비교, 발열 분해, R₃(RPM), 히트맵)
```

## 다음 에이전트

**→ Integration Agent** (`agents/05_integration.md`)  
완료 후 git commit → git push → `/clear`

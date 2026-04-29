# MEMORY.md — Motor Thermal Model v2 작업 추적

> **규칙**: 각 에이전트는 작업 시작 시 이 파일을 읽어 현재 상태를 파악하고,
> 작업 종료 시 "완료된 작업" 및 "다음 단계"를 업데이트한 후 세션을 종료한다.

---

## 현재 단계

**PHASE: 5 — Integration**
**현재 담당 에이전트**: Integration Agent (`agents/05_integration.md`)
**상태**: Phase 5 완료

---

## 완료된 작업

### Phase 0: Planning
- [x] 사용자 요구사항 수집 (Q1~Q4 답변 포함)
- [x] `docs/PRD.md` 작성 (물리 모델, 입출력 사양, 프로필 관리 포함)
- [x] `docs/STACK.md` 작성 (FastAPI + React, 이유 포함)
- [x] `docs/SPEC.md` 작성 (Pydantic 스키마, API 엔드포인트, 컴포넌트 트리)
- [x] `MEMORY.md` 초기화
- [x] `AGENTS.md` 작성
- [x] `agents/` 각 에이전트 지침 파일 작성

### Phase 1: Setup
- [x] backend/ 스캐폴딩 완료 (FastAPI + CORS + placeholder routers/core/schemas/storage)
- [x] backend/.venv 생성 (Python 3.12 via Homebrew) + requirements.txt 설치 성공
- [x] frontend/ Vite + React + TypeScript 초기화
- [x] Tailwind CSS v4 + shadcn/ui 초기화
- [x] 추가 패키지 설치: zustand, @tanstack/react-query, react-hook-form, zod, react-plotly.js, plotly.js, @tanstack/react-table, lucide-react, axios, @hookform/resolvers
- [x] src/ 디렉토리 구조 생성
- [x] vite.config.ts proxy 설정 (/api -> localhost:8000)

### Phase 2: Physics Engine
- [x] motor_geometry.py: thermal mass & resistance computation
- [x] thermal_model.py: 3-node ODE solver (LSODA)
- [x] loss_model.py: copper & iron loss models (simple + FEA map)
- [x] calibration.py: multi-start L-BFGS-B optimizer

### Phase 3: Backend API
- [x] profiles router: CRUD + compute-geometry
- [x] files router: upload, columns, map-columns, delete
- [x] calibration router: start, SSE stream, result polling
- [x] prediction router: steady-state + grid prediction
- [x] export router: Excel export
- [x] Pydantic schemas for all endpoints

### Phase 4: Frontend
- [x] React components: calibration wizard, prediction, profile management
- [x] Zustand store for app state
- [x] API client with axios
- [x] Chart components (Plotly)

### Phase 5: Integration
- [x] Backend test suite: 46 tests (22 API + 19 physics + 5 E2E) — all passing
- [x] Frontend production build: succeeds with zero errors
- [x] Test CSV fixture: `backend/tests/fixtures/test_thermal_data.csv` (200 rows, physics-generated)
- [x] E2E scenario tests: full calibration workflow + prediction scenarios
- [x] Grid prediction limit enforced: max 20x20 (performance optimization)
- [x] Thermal runaway detection at 500 degC threshold
- [x] README.md created with setup, API, and architecture documentation
- [x] CORS configured for Vite dev server (localhost:5173)
- [x] SSE calibration stream with proper close on done/error

---

## 프로젝트 상태: COMPLETE

---

## 핵심 결정사항 (Key Decisions)

| 항목 | 결정 | 근거 |
|------|------|------|
| 열 모델 | 3-노드 (코일, 코어, 하우징) | 내부 온도 분포 표현 필요 |
| 자유 파라미터 | R1, R2, h_nat, h_rpm (4개) | 열용량은 형상에서 계산 |
| 프레임워크 | FastAPI + React | 프로필 관리, SSE, 인터랙티브 UI |
| 철손 모드 | 간편 + FEA 손실 맵 (선택) | 토크 측정값 있음 -> bilinear 보간 |
| 프로필 저장 | 로컬 JSON | DB 없이 간단하게, 향후 DB 확장 가능 |
| 기준 치수 | D=106mm, L=48.85mm, t_wall=10.5mm | 사용자 확인 |
| 격자 예측 한계 | 20x20 max | 성능 최적화 (각 점마다 ODE 풀이) |
| 열 폭주 임계값 | 500 degC | 예측 에러 방지 |

---

## 참조 문서

- `docs/PRD.md` — 요구사항 전체
- `docs/STACK.md` — 기술 스택 결정
- `docs/SPEC.md` — API/스키마/컴포넌트 상세
- `AGENTS.md` — 에이전트 역할 및 핸드오프 프로토콜
- `README.md` — 프로젝트 설정 및 사용 가이드

---

## 다음 단계 (선택적)

- 사용자 인증 추가 (FastAPI + JWT)
- Docker 이미지 빌드
- 다중 측정 채널 (T_housing 직접 측정 지원)
- 2D 방사형 온도 분포 시각화

---

## 변경 이력

| 날짜 | 에이전트 | 변경 내용 |
|------|---------|-----------|
| 2026-04-28 | Setup Agent | Phase 1 완료: backend/frontend 스캐폴딩, 의존성 설치, 실행 확인 |
| 2026-04-28 | Integration Agent | Phase 5 완료: 46 테스트 통과, E2E 시나리오, 성능 최적화, README 작성 |

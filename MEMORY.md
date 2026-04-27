# MEMORY.md — Motor Thermal Model v2 작업 추적

> **규칙**: 각 에이전트는 작업 시작 시 이 파일을 읽어 현재 상태를 파악하고,  
> 작업 종료 시 "완료된 작업" 및 "다음 단계"를 업데이트한 후 세션을 종료한다.

---

## 현재 단계

**PHASE: 0 — Planning (문서화)**  
**현재 담당 에이전트**: Planning Agent (`agents/00_planning.md`)  
**상태**: ✅ PRD/STACK/SPEC 작성 완료, 사용자 승인 대기 중

---

## 완료된 작업

### Phase 0: Planning ✅
- [x] 사용자 요구사항 수집 (Q1~Q4 답변 포함)
- [x] `docs/PRD.md` 작성 (물리 모델, 입출력 사양, 프로필 관리 포함)
- [x] `docs/STACK.md` 작성 (FastAPI + React, 이유 포함)
- [x] `docs/SPEC.md` 작성 (Pydantic 스키마, API 엔드포인트, 컴포넌트 트리)
- [x] `MEMORY.md` 초기화
- [x] `AGENTS.md` 작성
- [x] `agents/` 각 에이전트 지침 파일 작성

---

## 진행 중인 작업

없음 (사용자 승인 대기)

---

## 다음 단계 (사용자 승인 후 순서대로 진행)

| # | Phase | 담당 에이전트 | 파일 |
|---|-------|--------------|------|
| 1 | Setup | Setup Agent | `agents/01_setup.md` |
| 2 | Physics Engine | Physics Agent | `agents/02_physics.md` |
| 3 | Backend API | Backend Agent | `agents/03_backend.md` |
| 4 | Frontend | Frontend Agent | `agents/04_frontend.md` |
| 5 | Integration | Integration Agent | `agents/05_integration.md` |

---

## 핵심 결정사항 (Key Decisions)

| 항목 | 결정 | 근거 |
|------|------|------|
| 열 모델 | 3-노드 (코일, 코어, 하우징) | 내부 온도 분포 표현 필요 |
| 자유 파라미터 | R₁, R₂, h_nat, h_rpm (4개) | 열용량은 형상에서 계산 |
| 프레임워크 | FastAPI + React | 프로필 관리, SSE, 인터랙티브 UI |
| 철손 모드 | 간편 + FEA 손실 맵 (선택) | 토크 측정값 있음 → bilinear 보간 |
| 프로필 저장 | 로컬 JSON | DB 없이 간단하게, 향후 DB 확장 가능 |
| 기준 치수 | D=106mm, L=48.85mm, t_wall=10.5mm | 사용자 확인 |

---

## 참조 문서

- `docs/PRD.md` — 요구사항 전체
- `docs/STACK.md` — 기술 스택 결정
- `docs/SPEC.md` — API/스키마/컴포넌트 상세
- `AGENTS.md` — 에이전트 역할 및 핸드오프 프로토콜

---

## 블로커 / 오픈 이슈

없음

---

## 변경 이력

| 날짜 | 에이전트 | 변경 내용 |
|------|---------|-----------|
| 2026-04-09 | Planning Agent | 초기 문서 작성 완료, 사용자 승인 대기 |
